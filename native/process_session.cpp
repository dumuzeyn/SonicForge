#include "core.h"
#include <cmath>
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
WavWriter::WavWriter(const QString& path, int sampleRate, int channelCount)
    : file(path), rate(sampleRate), channels(channelCount) {
    if (!file.open(QIODevice::WriteOnly))
        throw Error(file.errorString());
    file.write(QByteArray(80, 0));
}
void WavWriter::append(const float* samples, qsizetype count) {
    QByteArray block;
    block.resize(65536);
    for (qsizetype offset = 0; offset < count;) {
        qsizetype size = qMin(qsizetype(32768), count - offset);
        for (qsizetype i = 0; i < size; ++i) {
            double value = samples[offset + i];
            if (!std::isfinite(value))
                value = 0;
            qToLittleEndian<qint16>(qint16(qBound(-1., value, 1.) * 32767), block.data() + i * 2);
        }
        if (file.write(block.constData(), size * 2) != size * 2)
            throw Error(file.errorString());
        offset += size;
        bytes += size * 2;
    }
}
void WavWriter::finish() {
    file.seek(0);
    QDataStream stream(&file);
    stream.setByteOrder(QDataStream::LittleEndian);
    const bool large = bytes + 72 > 0xffffffffLL;
    file.write(large ? "RF64" : "RIFF", 4);
    stream << (large ? quint32(0xffffffff) : quint32(bytes + 72));
    file.write("WAVE", 4);
    file.write(large ? "ds64" : "JUNK", 4);
    stream << quint32(28) << quint64(bytes + 72) << quint64(bytes)
           << quint64(bytes / (channels * 2)) << quint32(0);
    file.write("fmt ", 4);
    stream << quint32(16) << quint16(1) << quint16(channels) << quint32(rate)
           << quint32(rate * channels * 2) << quint16(channels * 2) << quint16(16);
    file.write("data", 4);
    stream << (large ? quint32(0xffffffff) : quint32(bytes));
    if (!file.commit())
        throw Error(file.errorString());
}
} // namespace sf
