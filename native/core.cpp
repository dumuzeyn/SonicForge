#include "core.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <numbers>

namespace sf {
static QString n(double value) {
    return QString::number(value, 'f', 9);
}
void checkpoint(const Cancel& c) {
    if (c && c->load())
        throw Error(QStringLiteral("Операция отменена"));
}
QString executable(const QString& name) {
    const QString base = QCoreApplication::applicationDirPath();
    for (const auto& file :
         {base + "/tools/" + name + ".exe", base + "/_internal/ffmpeg/" + name + ".exe",
          QStringLiteral("C:/ffmpeg/bin/") + name + ".exe"})
        if (QFile::exists(file))
            return file;
    auto path = QStandardPaths::findExecutable(name);
    if (path.isEmpty())
        throw Error("Не найден " + name);
    return path;
}
QString cacheDirectory() {
    struct Cache {
        QString path;
        std::unique_ptr<QLockFile> lease;
        Cache() {
            path = QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + "/edits/session-" + QUuid::createUuid().toString(QUuid::Id128);
            if (!QDir().mkpath(path)) throw Error("Не удалось создать папку кэша: " + path);
            lease = std::make_unique<QLockFile>(path + "/session.lock");
            lease->setStaleLockTime(0);
            if (!lease->tryLock()) throw Error("Папка кэша занята");
        }
    };
    static Cache cache;
    return cache.path;
}
QString uniqueFile(const QString& suffix) {
    const auto result = cacheDirectory() + "/" + QUuid::createUuid().toString(QUuid::Id128) + suffix;
    checkCacheCapacity(result); return result;
}
QByteArray process(const QString& program, const QStringList& args, const Cancel& cancel,
                   Progress progress, bool capture, bool mergeError) {
    checkpoint(cancel);
    QProcess p;
    p.setProgram(program);
    auto safeArgs = args;
    if (QFileInfo(program).completeBaseName().compare("ffmpeg", Qt::CaseInsensitive) == 0) {
        for (int i = 0; i < safeArgs.size(); ++i)
            if (safeArgs[i] == "-i") { safeArgs.insert(i++, "-protocol_whitelist"); safeArgs.insert(i++, "file,pipe"); }
    } else if (QFileInfo(program).completeBaseName().compare("ffprobe", Qt::CaseInsensitive) == 0)
        safeArgs = QStringList{"-protocol_whitelist", "file,pipe"} + safeArgs;
    p.setArguments(safeArgs);
    if (mergeError)
        p.setProcessChannelMode(QProcess::MergedChannels);
#ifdef Q_OS_WIN
    p.setCreateProcessArgumentsModifier(
        [](QProcess::CreateProcessArguments* a) { a->flags |= 0x08000000; });
#endif
    p.start();
    if (!p.waitForStarted(15000))
        throw Error("Не удалось запустить: " + program + "\n" + p.errorString());
    adoptChild(p);
    QByteArray output, errors;
    QElapsedTimer timer;
    timer.start();
    QElapsedTimer totalTime; totalTime.start();
    QElapsedTimer storageTime; storageTime.start();
    const qint64 timeout = qMax(1000, qEnvironmentVariableIntValue("SF_PROCESS_TIMEOUT_MS") > 0 ?
                                      qEnvironmentVariableIntValue("SF_PROCESS_TIMEOUT_MS") : 21600000);
    while (p.state() != QProcess::NotRunning) {
        p.waitForFinished(50);
        if (capture)
            output += p.readAllStandardOutput();
        else
            p.readAllStandardOutput();
        if (!mergeError)
            errors += p.readAllStandardError();
        if (errors.size() > 32768)
            errors = errors.right(32768);
        if (mergeError && output.size() > 1024 * 1024) output = output.right(1024 * 1024);
        if (storageTime.elapsed() > 2000 && !args.isEmpty()) {
            try { checkCacheCapacity(args.last()); }
            catch (...) { p.kill(); p.waitForFinished(5000); throw; }
            storageTime.restart();
        }
        if (totalTime.elapsed() > timeout || (!mergeError && output.size() > 512LL * 1024 * 1024)) {
            p.kill(); p.waitForFinished(5000);
            throw Error(totalTime.elapsed() > timeout ? "Превышено время выполнения задачи: " + QFileInfo(program).fileName() + "\n" + QString::fromUtf8(errors.right(4000)) : "Слишком большой результат декодирования; обрабатывайте звук блоками");
        }
        if (cancel && cancel->load()) {
            p.kill();
            p.waitForFinished(5000);
            throw Error(QStringLiteral("Операция отменена"));
        }
        if (progress && timer.elapsed() > 300) {
            static const QRegularExpression fraction("progress=([0-9.]+)");
            auto matches = fraction.globalMatch(QString::fromUtf8(errors.right(2000)));
            double completed = -1;
            while (matches.hasNext())
                completed = matches.next().captured(1).toDouble();
            static const QRegularExpression stage("stage=([^\\r\\n]+)");
            auto stages = stage.globalMatch(QString::fromUtf8(errors.right(2000)));
            QString label;
            while (stages.hasNext()) label = stages.next().captured(1);
            progress(label, completed);
            timer.restart();
        }
    }
    output += p.readAllStandardOutput();
    if (!mergeError)
        errors += p.readAllStandardError();
    else
        errors = output.right(4000);
    if (p.exitStatus() != QProcess::NormalExit || p.exitCode() != 0)
        throw Error(QFileInfo(program).fileName() + ": " + QString::fromUtf8(errors.right(3000)));
    return output;
}
QByteArray ffmpeg(const QStringList& args, const Cancel& c, Progress p) {
    return process(executable("ffmpeg"),
                   QStringList{"-hide_banner", "-nostdin", "-v", "error"} + args, c, p);
}
QVector<float> decode(const QString& file, int rate, int channels, double start, double length,
                      const Cancel& c) {
    QStringList args;
    if (start > 0)
        args << "-ss" << n(start);
    args << "-i" << file << "-map" << "0:a:0" << "-vn";
    if (length > 0)
        args << "-t" << n(length);
    args << "-ac" << QString::number(channels) << "-ar" << QString::number(rate) << "-f" << "f32le"
         << "pipe:1";
    QByteArray data = ffmpeg(args, c);
    QVector<float> values(data.size() / 4);
    std::memcpy(values.data(), data.constData(), values.size() * 4);
    return values;
}
void writeWav(const QString& path, const QVector<float>& samples, int rate, int channels) {
    WavWriter writer(path, rate, channels);
    writer.append(samples.constData(), samples.size());
    writer.finish();
}
double Project::duration() const {
    double value = 0;
    for (const auto& c : clips)
        value = qMax(value, c.position + c.duration());
    return value;
}
int Project::lanes() const {
    int value = 1;
    for (const auto& c : clips)
        value = qMax(value, c.lane + 1);
    return value;
}
Clip& Project::get(const QString& id) {
    for (auto& c : clips)
        if (c.id == id)
            return c;
    throw Error("Фрагмент не найден");
}
const Clip& Project::get(const QString& id) const {
    for (const auto& c : clips)
        if (c.id == id)
            return c;
    throw Error("Фрагмент не найден");
}
double Project::freePosition(int lane, double position, double length,
                             const QString& exclude) const {
    QList<Clip> ordered = clips;
    std::sort(ordered.begin(), ordered.end(),
              [](auto& a, auto& b) { return a.position < b.position; });
    for (auto& c : ordered)
        if (c.lane == lane && c.id != exclude) {
            if (position + length <= c.position + 1e-8)
                break;
            if (position < c.position + c.duration() - 1e-8)
                position = c.position + c.duration();
        }
    return position;
}
QString Project::add(const Source& source, int lane, double position) {
    sources[source.path] = source;
    if (position < 0) {
        position = 0;
        for (const auto& c : clips)
            if (c.lane == lane)
                position = qMax(position, c.position + c.duration());
    }
    Clip c;
    c.id = QUuid::createUuid().toString(QUuid::Id128);
    c.source = source.path;
    c.lane = lane;
    c.end = source.duration;
    c.position = freePosition(lane, position, source.duration);
    clips << c;
    validate();
    return c.id;
}
QString Project::split(const QString& id, double at) {
    Clip old = get(id);
    double offset = at - old.position;
    if (offset < .01 || offset > old.duration() - .01)
        throw Error("Поставьте курсор внутри фрагмента");
    Clip right = old;
    right.id = QUuid::createUuid().toString(QUuid::Id128);
    right.start += offset * (old.speed > 0 ? old.speed : 1);
    right.position = at;
    right.fadeIn = 0;
    right.fadeOut = qMin(right.fadeOut, right.duration());
    auto& left = get(id);
    left.end = old.start + offset * (old.speed > 0 ? old.speed : 1);
    left.fadeOut = 0;
    left.fadeIn = qMin(left.fadeIn, left.duration());
    clips << right;
    return right.id;
}
void Project::validate() const {
    QSet<QString> ids;
    for (int lane : muted) if (lane < 0 || lane > 10000) throw Error("Неверная дорожка");
    for (const auto& c : clips) {
        if (c.id.isEmpty() || ids.contains(c.id)) throw Error("Повторяющийся идентификатор фрагмента");
        ids.insert(c.id);
        if (!sources.contains(c.source) || !std::isfinite(c.position) || !std::isfinite(c.gain) ||
            !std::isfinite(c.start) || !std::isfinite(c.end) || !std::isfinite(c.fadeIn) ||
            !std::isfinite(c.fadeOut) || c.start < 0 || c.end > sources[c.source].duration + .002 ||
            !std::isfinite(c.volume) || !std::isfinite(c.speed) || c.volume < 0 || c.volume > 4 ||
            c.speed < 0 || c.speed > 4 || !std::isfinite(c.bass) || !std::isfinite(c.mid) ||
            !std::isfinite(c.treble) || std::abs(c.bass) > 18 || std::abs(c.mid) > 18 ||
            std::abs(c.treble) > 18 || c.duration() < .01 || c.position < 0 || c.lane < 0 ||
            c.lane > 10000 || c.gain < -60 || c.gain > 18 || c.fadeIn < 0 || c.fadeOut < 0 ||
            c.fadeIn + c.fadeOut > c.duration() + 1e-7 || c.position + c.duration() > 604800)
            throw Error("Недопустимые параметры фрагмента");
        for (const auto& b : clips)
            if (b.id != c.id && b.lane == c.lane && c.position < b.position + b.duration() - 1e-8 &&
                b.position < c.position + c.duration() - 1e-8)
                throw Error("Фрагменты одной дорожки пересекаются");
    }
}
QJsonObject Project::json() const {
    QJsonArray list;
    for (auto& c : clips)
        list << QJsonObject{{"id", c.id},         {"source", c.source}, {"lane", c.lane},
                            {"start", c.start},   {"end", c.end},       {"position", c.position},
                            {"gain", c.gain},     {"fadeIn", c.fadeIn}, {"fadeOut", c.fadeOut},
                            {"volume", c.volume}, {"speed", c.speed},   {"bass", c.bass},
                            {"mid", c.mid},       {"treble", c.treble}, {"originalSource", c.originalSource}};
    QJsonArray m;
    for (int lane : muted)
        m << lane;
    QJsonArray sourceList;
    for (const auto& s : sources) {
        QJsonArray peaks; for (float value : s.peaks) peaks << double(value);
        sourceList << QJsonObject{{"path", s.path}, {"duration", s.duration}, {"size", s.size},
            {"modified", s.modified}, {"fingerprint", QString::fromLatin1(s.fingerprint.toHex())},
            {"sampleRate", s.sampleRate}, {"channels", s.channels}, {"bits", s.bits}, {"peaks", peaks}};
    }
    return {{"clips", list}, {"muted", m}, {"sources", sourceList}};
}
Source readSource(const QString& file, const Cancel& c, bool withWaveform) {
    QFileInfo info(file);
    if (!info.isFile())
        throw Error("Аудиофайл не найден: " + file);
    auto doc = QJsonDocument::fromJson(process(
        executable("ffprobe"),
        {"-v", "error", "-show_format", "-show_streams", "-of", "json", info.absoluteFilePath()},
        c));
    QJsonObject audioStream;
    for (const auto& stream : doc.object()["streams"].toArray())
        if (stream.toObject()["codec_type"] == "audio") { audioStream = stream.toObject(); break; }
    if (audioStream.isEmpty()) throw Error("В файле нет аудиодорожки");
    double duration = audioStream["duration"].toString().toDouble();
    if (duration <= 0) duration = doc.object()["format"].toObject()["duration"].toString().toDouble();
    if (duration <= 0 || duration >= 86400)
        throw Error("Нужен аудиофайл с длительностью от нуля до 24 часов");
    const int sampleRate = audioStream["sample_rate"].toString().toInt();
    const int channels = audioStream["channels"].toInt(2);
    const int bits = audioStream["bits_per_raw_sample"].toString().isEmpty() ? audioStream["bits_per_sample"].toInt(16) : audioStream["bits_per_raw_sample"].toString().toInt();
    if (!withWaveform) return {info.absoluteFilePath(), duration, {}, info.size(), info.lastModified().toMSecsSinceEpoch(), {}, sampleRate, channels, bits};
    // Aggregate waveform bins while decoding, independent of song length.
    QProcess decoder;
    decoder.setProgram(executable("ffmpeg"));
    decoder.setArguments({"-hide_banner", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", file, "-map", "0:a:0", "-vn", "-ac", "1",
                          "-ar", "8000", "-f", "f32le", "pipe:1"});
#ifdef Q_OS_WIN
    decoder.setCreateProcessArgumentsModifier(
        [](QProcess::CreateProcessArguments* a) { a->flags |= 0x08000000; });
#endif
    decoder.start();
    if (!decoder.waitForStarted(15000))
        throw Error(decoder.errorString());
    adoptChild(decoder);
    int step = qMax(1, int(std::ceil(duration * 8000 / 2400)));
    QVector<float> peaks;
    QByteArray pending, errors;
    float peak = 0;
    int count = 0;
    QElapsedTimer idle, elapsed; idle.start(); elapsed.start();
    do {
        decoder.waitForReadyRead(50);
        if (idle.elapsed() > 60000 || elapsed.elapsed() > 6 * 60 * 60 * 1000) { decoder.kill(); decoder.waitForFinished(5000); throw Error("Превышено время чтения звука"); }
        if (c && c->load()) {
            decoder.kill();
            decoder.waitForFinished(5000);
            checkpoint(c);
        }
        const auto bytes = decoder.readAllStandardOutput(); if (!bytes.isEmpty()) idle.restart(); pending += bytes;
        errors += decoder.readAllStandardError();
        if (errors.size() > 4000)
            errors = errors.right(4000);
        qsizetype consumed = pending.size() / 4 * 4;
        for (qsizetype at = 0; at < consumed; at += 4) {
            float sample;
            std::memcpy(&sample, pending.constData() + at, 4);
            peak = qMax(peak, std::abs(sample));
            if (++count == step) {
                peaks << peak;
                peak = 0;
                count = 0;
            }
        }
        pending.remove(0, consumed);
    } while (decoder.state() != QProcess::NotRunning || decoder.bytesAvailable() > 0);
    if (count)
        peaks << peak;
    if (decoder.exitCode() != 0)
        throw Error(QString::fromUtf8(errors));
    if (peaks.isEmpty()) {
        throw Error("Не удалось прочитать звук");
    }
    QFileInfo after(file);
    if (after.size() != info.size() || after.lastModified() != info.lastModified())
        throw Error("Исходник изменился во время чтения");
    return {info.absoluteFilePath(), duration, peaks, info.size(),
            info.lastModified().toMSecsSinceEpoch(), fileFingerprint(file, c),
            sampleRate, channels, bits};
}
QString render(const Project& project, const QString& target, const Cancel& c, double start,
               double length, Progress p, RenderOptions options) {
    project.validate();
    if (QFile::exists(target))
        throw Error("Выберите новое имя выходного файла");
    double end = length > 0 ? qMin(project.duration(), start + length) : project.duration();
    if (end <= start)
        throw Error("Нет звука для экспорта");
    int rate = options.sampleRate, channels = options.channels;
    QSet<QString> verified;
    for (const auto& clip : project.clips) {
        const auto source = project.sources.value(clip.source);
        if (!options.sampleRate) rate = qMax(rate, source.sampleRate);
        if (!options.channels) channels = qMax(channels, source.channels);
        if (!verified.contains(clip.source) && !source.fingerprint.isEmpty() && fileFingerprint(clip.source, c) != source.fingerprint)
            throw Error("Содержимое исходного файла изменилось: " + clip.source);
        verified.insert(clip.source);
    }
    rate = qBound(8000, rate, 384000); channels = qBound(1, channels, 8);
    const QString ext = QFileInfo(target).suffix().toLower();
    if (ext == "mp3" || ext == "m4a") channels = qMin(2, channels);
    if (ext == "opus") rate = 48000;
    const QStringList layouts{"", "mono", "stereo", "3.0", "quad", "5.0", "5.1", "6.1", "7.1"};
    // Bound both the Windows input argument list and FFmpeg's open-input count.
    constexpr int groupSize = 8;
    if (project.clips.size() > groupSize) {
        QTemporaryDir parts(cacheDirectory() + "/render-XXXXXX");
        if (!parts.isValid()) throw Error("Не удалось создать временную папку монтажа");
        Project mixed;
        for (int i = 0; i < project.clips.size(); i += groupSize) {
            Project batch = project; batch.clips = project.clips.mid(i, groupSize);
            bool audible = false;
            for (const auto& clip : batch.clips) audible |= !batch.muted.contains(clip.lane) && clip.position < end && clip.position + clip.duration() > start;
            if (!audible) continue;
            const auto part = parts.filePath(QString::number(i) + ".wav");
            render(batch, part, c, start, length, p, {rate, channels, 32, false});
            mixed.add(readSource(part, c), mixed.lanes(), 0);
        }
        if (mixed.clips.isEmpty()) throw Error("Нет включённых дорожек");
        return render(mixed, target, c, 0, end - start, p, {rate, channels, options.bits, options.limiter, options.quality});
    }
    // Keep decoder/graph threading bounded independently of host CPU count.
    QStringList args{"-filter_complex_threads", "1", "-v", qEnvironmentVariable("SF_RENDER_LOGLEVEL", "error")}, filters, labels;
    int index = 0;
    for (auto& clip : project.clips) {
        if (project.muted.contains(clip.lane) || clip.position >= end ||
            clip.position + clip.duration() <= start)
            continue;
        QFileInfo info(clip.source);
        const auto& source = project.sources[clip.source];
        if (source.size && (info.size() != source.size ||
                            info.lastModified().toMSecsSinceEpoch() != source.modified))
            throw Error("Исходный файл изменился: " + clip.source);
        double offset = qMax(0., start - clip.position),
               duration = qMin(clip.duration() - offset, end - qMax(start, clip.position));
        const double playbackRate = clip.speed > 0 ? clip.speed : 1;
        args << "-threads" << "1" << "-ss" << n(clip.start + offset * playbackRate) << "-t" << n(duration * playbackRate) << "-i"
             << clip.source;
        QStringList chain{"asetpts=N/SR/TB", "aresample=" + QString::number(rate),
                          "aformat=sample_fmts=fltp:channel_layouts=" + layouts[channels], "volume=" + n(clip.gain) + "dB"};
        if (clip.speed > 0) {
            double tempo = clip.speed;
            while (tempo > 2) {
                chain << "atempo=2";
                tempo /= 2;
            }
            while (tempo < .5) {
                chain << "atempo=0.5";
                tempo *= 2;
            }
            if (std::abs(tempo - 1) > .00001)
                chain << "atempo=" + n(tempo);
        }
        chain << "volume=" + n(clip.speed > 0 ? clip.volume : 0);
        if (clip.bass)
            chain << "bass=g=" + n(clip.bass) + ":f=100:w=0.8";
        if (clip.mid)
            chain << "equalizer=f=1000:t=q:w=1:g=" + n(clip.mid);
        if (clip.treble)
            chain << "treble=g=" + n(clip.treble) + ":f=6000:w=0.8";
        if (clip.fadeIn > 0 || clip.fadeOut > 0) {
            chain << "asetpts=PTS-STARTPTS+" + n(offset) + "/TB";
            if (clip.fadeIn > 0)
                chain << "afade=t=in:st=0:d=" + n(clip.fadeIn);
            if (clip.fadeOut > 0)
                chain << "afade=t=out:st=" + n(clip.duration() - clip.fadeOut) +
                             ":d=" + n(clip.fadeOut);
            chain << "asetpts=N/SR/TB";
        }
        chain << "adelay=" + QString::number(qRound64(qMax(0., clip.position - start) * 1000)) +
                     ":all=1";
        QString tag = "c" + QString::number(index);
        filters << "[" + QString::number(index) + ":a]" + chain.join(',') + "[" + tag + "]";
        labels << "[" + tag + "]";
        ++index;
    }
    if (!index)
        throw Error("Нет включённых дорожек");
    const auto samples = QString::number(qMax(qint64(1), qRound64((end - start) * rate)));
    filters << labels.join("") + "amix=inputs=" + QString::number(index) +
                   ":normalize=0:duration=longest,asetpts=N/SR/TB,apad=whole_len=" + samples + ",atrim=end_sample=" + samples + ",asetpts=N/SR/TB" +
                   (options.limiter ? ",alimiter=limit=0.95:level=0:latency=1[out]" : "[out]");
    QTemporaryFile graph(cacheDirectory() + "/graph-XXXXXX.txt");
    if (!graph.open() || graph.write(filters.join(';').toUtf8()) < 0) throw Error("Не удалось сохранить сценарий фильтров");
    graph.close();
    args << "-filter_complex_script" << graph.fileName() << "-map" << "[out]" << "-vn" << "-t" << n(end - start) << "-ar" << QString::number(rate) << "-ac" << QString::number(channels);
    if (ext == "mp3")
        args << "-c:a" << "libmp3lame" << "-q:a" << QString::number(options.quality);
    else if (ext == "m4a")
        args << "-c:a" << "aac" << "-b:a" << "256k";
    else if (ext == "wav")
        args << "-c:a" << (options.bits == 16 ? "pcm_s16le" : options.bits == 24 ? "pcm_s24le" : "pcm_f32le") << "-rf64" << "auto";
    else if (ext == "flac") args << "-c:a" << "flac";
    else if (ext == "opus") args << "-c:a" << "libopus" << "-b:a" << "192k";
    else throw Error("Поддерживаются WAV, MP3, M4A, FLAC и Opus");
    QString temporary = QFileInfo(target).absolutePath() + "/.sonicforge-" +
                        QUuid::createUuid().toString(QUuid::Id128) + "." + ext;
    QDir().mkpath(QFileInfo(target).absolutePath());
    try {
        ffmpeg(args + QStringList{temporary}, c, p);
        checkpoint(c);
        if (!QFile::rename(temporary, target))
            throw Error("Не удалось сохранить результат без перезаписи");
    } catch (...) {
        QFile::remove(temporary);
        throw;
    }
    return target;
}
Source cutAudio(const Project& project, const Clip& clip, double a, double b, const Cancel& c) {
    a = qBound(0., a - clip.position, clip.duration());
    b = qBound(0., b - clip.position, clip.duration());
    if (b - a < .01 || clip.duration() - (b - a) < .01)
        throw Error("Недопустимое выделение");
    double right = clip.duration() - b;
    QStringList args, filters;
    QString input = clip.source;
    double sourceStart = clip.start;
    QString baked;
    auto cleanupBaked = qScopeGuard([&] { if (!baked.isEmpty()) QFile::remove(baked); });
    if (clip.speed != 1) {
        Project one = project;
        auto plain = clip;
        plain.position = 0;
        plain.gain = plain.fadeIn = plain.fadeOut = plain.bass = plain.mid = plain.treble = 0;
        plain.volume = 1;
        one.clips = {plain};
        one.muted.clear();
        baked = uniqueFile();
        render(one, baked, c);
        input = baked;
        sourceStart = 0;
    }
    int count = 0;
    for (auto bounds : {QPair<double, double>{0, a}, {b, right}})
        if (bounds.second > 1e-8) {
            args << "-ss" << n(sourceStart + bounds.first) << "-t" << n(bounds.second) << "-i"
                 << input;
            filters
                << "[" + QString::number(count) +
                       ":a]asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[p" +
                       QString::number(count) + "]";
            ++count;
        }
    if (count == 2)
        filters << "[p0][p1]acrossfade=d=" + n(qMin(.04, qMin(a / 2, right / 2))) +
                       ":c1=tri:c2=tri[out]";
    else
        filters << "[p0]anull[out]";
    QString output = uniqueFile();
    bool complete = false;
    auto cleanupOutput = qScopeGuard([&] { if (!complete) QFile::remove(output); });
    ffmpeg(args + QStringList{"-filter_complex", filters.join(';'), "-map", "[out]", "-c:a",
                              "pcm_f32le", output},
           c);
    auto result = readSource(output, c);
    if (!baked.isEmpty())
        QFile::remove(baked);
    complete = true;
    return result;
}
Source crossfade(const Project& p, const Clip& first, const Clip& next, const Cancel& c,
                 double seconds) {
    if (first.lane != next.lane || next.position < first.position + first.duration() - 1e-8)
        throw Error("Нужны соседние песни одной дорожки");
    double overlap = qMin(seconds, qMin(first.duration() / 2, next.duration() / 2));
    if (overlap <= 0)
        throw Error("Недопустимая длина перехода");
    QString a = uniqueFile(), b = uniqueFile();
    auto cleanupInputs = qScopeGuard([&] { QFile::remove(a); QFile::remove(b); });
    Project one = p;
    one.muted.clear();
    Clip left = first;
    left.position = 0;
    left.fadeOut = 0;
    one.clips = {left};
    render(one, a, c);
    Clip right = next;
    right.position = 0;
    right.fadeIn = 0;
    one.clips = {right};
    render(one, b, c);
    auto rms = [](const QVector<float>& s) {
        double sum = 0;
        for (float x : s)
            sum += x * x;
        return std::sqrt(sum / qMax(qsizetype(1), s.size()));
    };
    double x = rms(decode(a, 16000, 1, first.duration() - overlap, overlap, c)),
           y = rms(decode(b, 16000, 1, 0, overlap, c));
    double ga = 1, gb = 1;
    if (qMin(x, y) > .001) {
        ga = qMax(.2511886432, qMin(x, y) / x);
        gb = qMax(.2511886432, qMin(x, y) / y);
    }
    QString filter =
        "[0:a]volume='1-(1-" + n(ga) + ")*clip((t-" + n(first.duration() - 2 * overlap) + ")/" +
        n(overlap) + ",0,1)':eval=frame[a];[1:a]volume='" + n(gb) + "+(1-" + n(gb) + ")*clip((t-" +
        n(overlap) + ")/" + n(overlap) + ",0,1)':eval=frame[b];[a][b]acrossfade=d=" + n(overlap) +
        ":c1=qsin:c2=qsin,alimiter=limit=0.95:level=0:latency=1[out]";
    QString out = uniqueFile();
    bool complete = false;
    auto cleanupOutput = qScopeGuard([&] { if (!complete) QFile::remove(out); });
    try {
        ffmpeg({"-i", a, "-i", b, "-filter_complex", filter, "-map", "[out]", "-c:a", "pcm_f32le",
                out},
               c);
    } catch (...) {
        QFile::remove(a);
        QFile::remove(b);
        throw;
    }
    QFile::remove(a);
    QFile::remove(b);
    auto result = readSource(out, c); complete = true; return result;
}
QString timestamp(double value, int decimals) {
    if (!std::isfinite(value) || value < 0)
        throw Error("Неверное время");
    decimals = decimals == 3 ? 3 : 2;
    const qint64 factor = decimals == 3 ? 1000 : 100;
    qint64 cents = qRound64(value * factor);
    return QString("%1:%2.%3")
        .arg(cents / (60 * factor), 2, 10, QChar('0'))
        .arg((cents / factor) % 60, 2, 10, QChar('0'))
        .arg(cents % factor, decimals, 10, QChar('0'));
}
double parseTime(const QString& text) {
    static QRegularExpression re("^\\[?(\\d{1,6}):(\\d{2})(?:[.:](\\d{1,3}))?\\]?$");
    auto m = re.match(text.trimmed());
    if (!m.hasMatch() || m.captured(2).toInt() > 59)
        throw Error("Введите время mm:ss.xx");
    return m.captured(1).toDouble() * 60 + m.captured(2).toDouble() +
           (m.captured(3).isEmpty()
                ? 0
                : m.captured(3).toDouble() / std::pow(10, m.captured(3).size()));
}
QList<Lyric> parseLyrics(const QString& text, bool strict) {
    static QRegularExpression re("^\\[(\\d{1,6}:\\d{2}(?:[.:]\\d{1,3})?)\\]");
    static QRegularExpression header("^\\[(ar|al|ti|au|by|re|ve|length|offset):([^]]*)\\]$",
                                     QRegularExpression::CaseInsensitiveOption);
    QList<Lyric> lines;
    double offset = 0;
    for (auto raw : text.split('\n')) {
        QString line = raw.trimmed();
        line.remove(QChar(0xfeff));
        if (line.isEmpty())
            continue;
        auto h = header.match(line);
        if (h.hasMatch()) {
            if (h.captured(1).compare("offset", Qt::CaseInsensitive) == 0) {
                bool ok = false;
                offset = h.captured(2).toDouble(&ok) / 1000.;
                if (!ok || !std::isfinite(offset))
                    throw Error("Неверное смещение LRC");
            }
            continue;
        }
        auto m = re.match(line);
        if (!m.hasMatch()) {
            if (strict)
                throw Error("У каждой строки должна быть метка [mm:ss.xx]");
            continue;
        }
        QList<double> times;
        do {
            times << parseTime(m.captured(1));
            line = line.mid(m.capturedLength()).trimmed();
            m = re.match(line);
        } while (m.hasMatch());
        if (!line.isEmpty())
            for (double time : times)
                lines << Lyric{time, 0, line};
    }
    for (auto& line : lines)
        line.start = qMax(0., line.start + offset);
    std::stable_sort(lines.begin(), lines.end(),
                     [](const Lyric& a, const Lyric& b) { return a.start < b.start; });
    for (int i = 0; i < lines.size(); ++i)
        lines[i].end = i + 1 < lines.size() ? lines[i + 1].start : lines[i].start;
    return lines;
}
QString lrc(const QList<Lyric>& lines) {
    QStringList result;
    for (auto& line : lines)
        if (!line.text.trimmed().isEmpty())
            result << "[" + timestamp(line.start, 3) + "]" + line.text.trimmed();
    return result.join('\n');
}
QString plainLyrics(const QString& text) {
    QString result = text;
    result.remove(QRegularExpression("\\[\\d{1,6}:\\d{2}(?:[.:]\\d{1,3})?\\]"));
    result.remove(QRegularExpression("^\\s*\\[(?:ar|al|ti|au|by|re|ve|length|offset):[^\\]]*\\]\\s*$", QRegularExpression::MultilineOption | QRegularExpression::CaseInsensitiveOption));
    return result.trimmed();
}
QList<std::complex<double>> fft(QList<std::complex<double>> a) {
    int n = a.size();
    if (n <= 1)
        return a;
    if (n & (n - 1))
        throw Error("FFT requires a power of two");
    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1)
            j ^= bit;
        j ^= bit;
        if (i < j)
            std::swap(a[i], a[j]);
    }
    for (int width = 2; width <= n; width <<= 1) {
        auto root = std::polar(1., -2 * std::numbers::pi / width);
        for (int at = 0; at < n; at += width) {
            std::complex<double> w = 1;
            for (int j = 0; j < width / 2; ++j) {
                auto even = a[at + j], odd = a[at + j + width / 2] * w;
                a[at + j] = even + odd;
                a[at + j + width / 2] = even - odd;
                w *= root;
            }
        }
    }
    return a;
}
QStringList AudioOptions::filters(double duration) const {
    QStringList f;
    if (highpass)
        f << "highpass=f=" + n(highpassHz);
    if (lowpass)
        f << "lowpass=f=" + n(lowpassHz);
    if (denoise)
        f << "afftdn=nf=-30:nt=w:tn=1:nr=" + n(noiseStrength);
    if (bass)
        f << "bass=g=" + n(bass) + ":f=100:w=0.8";
    if (mid)
        f << "equalizer=f=1000:t=q:w=1:g=" + n(mid);
    if (treble)
        f << "treble=g=" + n(treble) + ":f=6000:w=0.8";
    if (width != 1)
        f << "stereotools=mlev=1:slev=" + n(width);
    if (compressor)
        f << "acompressor=threshold=" + n(std::pow(10, threshold / 20)) + ":ratio=" + n(ratio) +
                 ":attack=" + n(attack) + ":release=" + n(release) +
                 ":makeup=" + n(std::pow(10, makeup / 20));
    double factor = std::pow(2, pitch / 12);
    if (pitch)
        f << "aresample=44100,asetrate=" + n(44100 * factor) + ",aresample=44100";
    double tempo = speed / factor;
    while (tempo > 2) {
        f << "atempo=2";
        tempo /= 2;
    }
    while (tempo < .5) {
        f << "atempo=0.5";
        tempo *= 2;
    }
    if (std::abs(tempo - 1) > .00001)
        f << "atempo=" + n(tempo);
    if (reverb > 0)
        f << "aecho=0.8:0.88:60|110:" + n(reverb * .45) + "|" + n(reverb * .22);
    if (fadeIn > 0)
        f << "afade=t=in:st=0:d=" + n(qMin(fadeIn, duration / speed));
    if (fadeOut > 0)
        f << "afade=t=out:st=" + n(qMax(0., duration / speed - fadeOut)) + ":d=" + n(fadeOut);
    return f;
}
QJsonObject analyze(const QString& audio, const Cancel& cancel) {
    const auto source = readSource(audio, cancel, false);
    double sum = 0, peak = 0, quiet = 0;
    qint64 sampleCount = 0;
    auto stats = process(executable("ffmpeg"),
                         {"-hide_banner", "-nostdin", "-i", audio, "-af",
                          "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"},
                         cancel, {}, true, true);
    QJsonObject loudness;
    int begin = stats.lastIndexOf('{'), end = stats.lastIndexOf('}');
    if (begin >= 0 && end > begin)
        loudness = QJsonDocument::fromJson(stats.mid(begin, end - begin + 1)).object();
    double bass = 0, mid = 0, treble = 0, weighted = 0, total = 0, flatness = 0;
    int frames = 0;
    for (double begin = 0; begin < source.duration; begin += 30) {
      checkpoint(cancel);
      const auto samples = decode(audio, 48000, 2, begin, qMin(30., source.duration - begin), cancel);
      for (float x : samples) {
        if (!std::isfinite(x)) continue;
        sum += double(x) * x; peak = qMax(peak, std::abs(double(x))); quiet += std::abs(x) < .01; ++sampleCount;
      }
      for (qsizetype at = 0; at + 4096 <= samples.size(); at += 24000) for (int channel = 0; channel < 2; ++channel) {
        QList<std::complex<double>> window(2048);
        for (int i = 0; i < 2048; ++i)
            window[i] = samples[at + i * 2 + channel] * (.5 - .5 * std::cos(2 * std::numbers::pi * i / 2048));
        auto bins = fft(window);
        double logarithm = 0, sumPower = 0;
        for (int k = 1; k <= 1024; ++k) {
            double energy = std::norm(bins[k]), hz = k * 48000. / 2048;
            total += energy;
            weighted += energy * hz;
            if (hz < 250)
                bass += energy;
            else if (hz < 4000)
                mid += energy;
            else
                treble += energy;
            logarithm += std::log(qMax(1e-20, energy));
            sumPower += energy;
        }
        flatness += std::exp(logarithm / 1024) / qMax(1e-20, sumPower / 1024);
        ++frames;
      }
    }
    const double rms = std::sqrt(sum / qMax(qint64(1), sampleCount));
    return {{"rmsDb", 20 * std::log10(qMax(1e-12, rms))},
            {"peakDb", 20 * std::log10(qMax(1e-12, peak))},
            {"quietFraction", quiet / qMax(qint64(1), sampleCount)}, {"analyzedSeconds", source.duration}, {"spectralSampleRate", 48000},
            {"integratedLufs", loudness["input_i"].toString()},
            {"truePeak", loudness["input_tp"].toString()},
            {"lra", loudness["input_lra"].toString()},
            {"centroid", weighted / qMax(1e-20, total)},
            {"bassFraction", bass / qMax(1e-20, total)},
            {"midFraction", mid / qMax(1e-20, total)},
            {"trebleFraction", treble / qMax(1e-20, total)},
            {"flatness", flatness / qMax(1, frames)},
            {"suggestedLufs", -14},
            {"suggestedTruePeak", -1.5}};
}
QString normalize(const QString& source, const QString& target, const AudioOptions& options,
                  const Cancel& c, Progress p) {
    auto info = readSource(source, c, false);
    auto effective = options;
    if (options.autoDenoise && !options.denoise) {
        auto measurements = analyze(source, c);
        effective.denoise = measurements["flatness"].toDouble() > .35 &&
                            measurements["rmsDb"].toDouble() < -25 &&
                            measurements["rmsDb"].toDouble() > -65;
    }
    QStringList filters = effective.filters(info.duration);
    QString normalization =
        "loudnorm=I=" + n(options.lufs) + ":TP=" + n(options.truePeak) + ":LRA=" + n(options.lra);
    auto measured = process(
        executable("ffmpeg"),
        QStringList{"-hide_banner", "-nostdin", "-i", source, "-vn", "-af"} +
            QStringList{(filters + QStringList{normalization + ":print_format=json"}).join(','),
                        "-f", "null", "-"},
        c, p, true, true);
    int begin = measured.lastIndexOf('{'), end = measured.lastIndexOf('}');
    auto stats = begin >= 0 && end > begin
                     ? QJsonDocument::fromJson(measured.mid(begin, end - begin + 1)).object()
                     : QJsonObject();
    bool finite = true;
    for (const auto& key : {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}) {
        bool ok = false;
        double value = stats[key].toString().toDouble(&ok);
        finite &= ok && std::isfinite(value);
    }
    // FFmpeg can measure positive LUFS on high-frequency/square signals, but its
    // two-pass measured_I parameter accepts only [-99, 0]. Use the dynamic pass
    // whenever a measurement is outside the filter's accepted parameter range.
    finite &= stats["input_i"].toString().toDouble() >= -99 && stats["input_i"].toString().toDouble() <= 0;
    finite &= stats["input_lra"].toString().toDouble() >= 0 && stats["input_lra"].toString().toDouble() <= 99;
    finite &= stats["input_tp"].toString().toDouble() >= -99 && stats["input_tp"].toString().toDouble() <= 99;
    finite &= stats["input_thresh"].toString().toDouble() >= -99 && stats["input_thresh"].toString().toDouble() <= 0;
    finite &= std::abs(stats["target_offset"].toString().toDouble()) <= 99;
    if (finite)
        normalization += ":measured_I=" + stats["input_i"].toString() +
                         ":measured_TP=" + stats["input_tp"].toString() +
                         ":measured_LRA=" + stats["input_lra"].toString() +
                         ":measured_thresh=" + stats["input_thresh"].toString() +
                         ":offset=" + stats["target_offset"].toString() + ":linear=true";
    filters << normalization;
    if (options.gain != 1)
        filters << "volume=" + n(options.gain);
    if (options.limiter)
        filters << "alimiter=limit=" + n(std::pow(10, options.truePeak / 20)) +
                       ":level=0:latency=1";
    QStringList args{"-i", source, "-map", "0:a:0", "-vn", "-af", filters.join(',')};
    if (options.sampleRate)
        args << "-ar" << QString::number(options.sampleRate);
    if (options.channels)
        args << "-ac" << QString::number(options.channels);
    QString suffix = QFileInfo(target).suffix().toLower();
    if (suffix == "mp3")
        args << "-c:a" << "libmp3lame" << "-q:a" << QString::number(options.quality);
    else if (suffix == "wav")
        args << "-c:a" << "pcm_f32le" << "-rf64" << "auto";
    else if (suffix == "flac") args << "-c:a" << "flac";
    else if (suffix == "opus") args << "-c:a" << "libopus" << "-b:a" << "192k";
    else if (suffix == "ogg") args << "-c:a" << "libvorbis" << "-q:a" << "6";
    else if (suffix == "m4a")
        args << "-c:a" << "aac" << "-b:a" << "256k";
    else throw Error("Неподдерживаемый формат результата: " + suffix);
    if (QFile::exists(target))
        throw Error("Результат уже существует: " + target);
    QDir().mkpath(QFileInfo(target).absolutePath());
    const QString temporary = QFileInfo(target).absolutePath() + "/.sonicforge-" + QUuid::createUuid().toString(QUuid::Id128) + "." + suffix;
    auto cleanup = qScopeGuard([&] { QFile::remove(temporary); });
    ffmpeg(args + QStringList{temporary}, c, p);
    if (options.limiter && (suffix == "mp3" || suffix == "m4a" || suffix == "opus" || suffix == "ogg")) {
        double correction = 0;
        for (int attempt = 0; attempt < 4; ++attempt) {
            const auto measured = process(executable("ffmpeg"), {"-hide_banner", "-nostdin", "-i", temporary, "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"}, c, {}, true, true);
            const auto begin = measured.lastIndexOf('{'), end = measured.lastIndexOf('}');
            bool ok = false; const auto value = QJsonDocument::fromJson(measured.mid(begin, end - begin + 1)).object()["input_tp"].toString(); const double peak = value.toDouble(&ok);
            if (value == "-inf" || (ok && peak <= options.truePeak + .05)) break;
            if (!ok || attempt == 3) throw Error("Не удалось подтвердить true peak закодированного результата");
            correction -= peak - options.truePeak + .15;
            auto adjusted = args; adjusted[adjusted.indexOf("-af") + 1] = filters.join(',') + ",volume=" + n(correction) + "dB";
            ffmpeg(adjusted + QStringList{"-y", temporary}, c, p);
        }
    }
    transferLyrics(source, temporary, options.speed, c);
    checkpoint(c);
    publishFiles({{temporary, target}});
    return target;
}
} // namespace sf
