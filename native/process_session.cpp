#include "core.h"
#include <cmath>
#include <cstring>
#ifdef Q_OS_WIN
#include <windows.h>
#endif
namespace sf {
namespace {
struct Session {
    QMutex mutex;
    bool closing = false;
#ifdef Q_OS_WIN
    HANDLE job = nullptr;
    ~Session() {
        if (job)
            CloseHandle(job);
    }
#endif
};
Session& session() {
    static Session value;
    return value;
}
} // namespace
void adoptChild(QProcess& process) {
    auto& state = session();
    QMutexLocker lock(&state.mutex);
    if (state.closing) {
        process.kill();
        throw Error("Приложение закрывается");
    }
#ifdef Q_OS_WIN
    if (!state.job) {
        state.job = CreateJobObjectW(nullptr, nullptr);
        if (!state.job) {
            process.kill();
            throw Error("Не удалось создать группу фоновых процессов");
        }
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if (!SetInformationJobObject(state.job, JobObjectExtendedLimitInformation, &info,
                                     sizeof(info))) {
            process.kill();
            throw Error("Не удалось настроить остановку фоновых процессов");
        }
    }
    HANDLE child =
        OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, FALSE, DWORD(process.processId()));
    if (child) {
        BOOL assigned = AssignProcessToJobObject(state.job, child);
        CloseHandle(child);
        if (!assigned && process.state() != QProcess::NotRunning) {
            process.kill();
            throw Error("Не удалось привязать фоновую задачу к приложению");
        }
    } else if (process.state() != QProcess::NotRunning) {
        process.kill();
        throw Error("Фоновая задача недоступна");
    }
#endif
}
void shutdownWorkers() {
    auto& state = session();
    QMutexLocker lock(&state.mutex);
    state.closing = true;
#ifdef Q_OS_WIN
    if (state.job)
        TerminateJobObject(state.job, 0);
#endif
}
WavWriter::WavWriter(const QString& path, int sampleRate, int channelCount, bool useFloat)
    : file(path), rate(sampleRate), channels(channelCount), floating(useFloat) {
    if (!file.open(QIODevice::WriteOnly))
        throw Error(file.errorString());
    file.write(QByteArray(floating ? 92 : 80, 0));
}
void WavWriter::append(const float* samples, qsizetype count) {
    const int width = floating ? 4 : 2;
    checkCacheCapacity(file.fileName(), count * width);
    QByteArray block;
    block.resize(131072);
    for (qsizetype offset = 0; offset < count;) {
        qsizetype size = qMin(qsizetype(32768), count - offset);
        for (qsizetype i = 0; i < size; ++i) {
            double value = samples[offset + i];
            if (!std::isfinite(value))
                value = 0;
            if (floating) {
                const float sample = float(value); quint32 bits; std::memcpy(&bits, &sample, 4);
                qToLittleEndian<quint32>(bits, block.data() + i * 4);
            } else qToLittleEndian<qint16>(qint16(qBound(-1., value, 1.) * 32767), block.data() + i * 2);
        }
        if (file.write(block.constData(), size * width) != size * width)
            throw Error(file.errorString());
        offset += size;
        bytes += size * width;
    }
}
void WavWriter::finish() {
    file.seek(0);
    QDataStream stream(&file);
    stream.setByteOrder(QDataStream::LittleEndian);
    const int width = floating ? 4 : 2;
    const qint64 overhead = floating ? 84 : 72;
    const bool large = bytes + overhead > 0xffffffffLL;
    file.write(large ? "RF64" : "RIFF", 4);
    stream << (large ? quint32(0xffffffff) : quint32(bytes + overhead));
    file.write("WAVE", 4);
    file.write(large ? "ds64" : "JUNK", 4);
    stream << quint32(28) << quint64(bytes + overhead) << quint64(bytes)
           << quint64(bytes / (channels * width)) << quint32(0);
    file.write("fmt ", 4);
    stream << quint32(16) << quint16(floating ? 3 : 1) << quint16(channels) << quint32(rate)
           << quint32(rate * channels * width) << quint16(channels * width) << quint16(width * 8);
    if (floating) { file.write("fact", 4); stream << quint32(4) << quint32(qMin(qint64(0xffffffff), bytes / (channels * width))); }
    file.write("data", 4);
    stream << (large ? quint32(0xffffffff) : quint32(bytes));
    if (!file.commit())
        throw Error(file.errorString());
}
} // namespace sf
