#include "core.h"
#include <algorithm>
#include <cmath>
#ifdef Q_OS_WIN
#include <windows.h>
#endif
namespace sf {
void checkCacheCapacity(const QString& path, qint64 additional) {
    const QString prefix = QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + "/edits/";
    const auto full = QFileInfo(path).absoluteFilePath();
    if (!full.startsWith(prefix, Qt::CaseInsensitive)) return;
    const auto rest = full.mid(prefix.size());
    const auto session = rest.section('/', 0, 0);
    if (!session.startsWith("session-")) return;
    const auto root = prefix + session;
    const qint64 limit = qBound(1, QSettings().value("cache/maxGiB", 8).toInt(), 128) * 1024LL * 1024 * 1024;
    qint64 total = additional;
    QDirIterator files(root, QDir::Files, QDirIterator::Subdirectories);
    while (files.hasNext()) { files.next(); total += files.fileInfo().size(); }
    if (total > limit) throw Error("Квота кэша исчерпана. Сохраните проект, очистите историю отмены или увеличьте квоту в настройках.");
}
QByteArray fileFingerprint(const QString& path, const Cancel& cancel) {
    QFile input(path);
    if (!input.open(QIODevice::ReadOnly)) throw Error(input.errorString());
    QCryptographicHash hash(QCryptographicHash::Sha256);
    while (!input.atEnd()) {
        checkpoint(cancel);
        const auto bytes = input.read(1024 * 1024);
        if (bytes.isEmpty() && input.error() != QFileDevice::NoError) throw Error(input.errorString());
        hash.addData(bytes);
    }
    return hash.result();
}
QString readTextFile(const QString& path) {
    QFile input(path);
    if (!input.open(QIODevice::ReadOnly)) throw Error(input.errorString());
    if (input.size() > 16 * 1024 * 1024) throw Error("Слишком большой текстовый файл");
    const auto bytes = input.readAll();
    auto encoding = QStringConverter::encodingForData(bytes).value_or(QStringConverter::Utf8);
    QStringDecoder decoder(encoding);
    QString result = decoder(bytes);
    if (decoder.hasError()) {
#ifdef Q_OS_WIN
        const int count = MultiByteToWideChar(1251, 0, bytes.constData(), int(bytes.size()), nullptr, 0);
        result.resize(count);
        MultiByteToWideChar(1251, 0, bytes.constData(), int(bytes.size()), reinterpret_cast<wchar_t*>(result.data()), count);
#else
        throw Error("Неизвестная кодировка текста. Сохраните файл в UTF-8.");
#endif
    }
    result.remove(QChar(0xfeff));
    return result;
}
QString backupFile(const QString& path) {
    if (!QFileInfo::exists(path)) return {};
    const QString directory = QFileInfo(path).absolutePath() + "/.sonicforge-backups";
    if (!QDir().mkpath(directory)) throw Error("Не удалось создать резервную копию: " + directory);
    const QString copy = directory + "/" + QFileInfo(path).completeBaseName() + "-" +
        QDateTime::currentDateTimeUtc().toString("yyyyMMdd-HHmmss-zzz") + "-" +
        QUuid::createUuid().toString(QUuid::Id128).left(8) + "." + QFileInfo(path).suffix();
    if (!QFile::copy(path, copy)) throw Error("Не удалось сохранить резервную копию: " + path);
    return copy;
}
void publishFiles(const QList<QPair<QString, QString>>& files) {
    QSet<QString> names;
    for (const auto& pair : files) {
        const auto name = QFileInfo(pair.second).absoluteFilePath().toCaseFolded();
        if (names.contains(name) || QFileInfo::exists(pair.second)) throw Error("Результат уже существует: " + pair.second);
        names.insert(name);
        if (!QDir().mkpath(QFileInfo(pair.second).absolutePath())) throw Error("Не удалось создать папку результата");
    }
    QList<QPair<QString, QString>> completed;
    for (const auto& pair : files) {
        if (!QFile::rename(pair.first, pair.second)) {
            QStringList retained;
            for (auto it = completed.crbegin(); it != completed.crend(); ++it)
                if (!QFile::rename(it->second, it->first)) retained << it->second;
            throw Error("Не удалось опубликовать: " + pair.second +
                        (retained.isEmpty() ? "\nИзменения отменены." : "\nСохранённые файлы: " + retained.join('\n')));
        }
        completed << pair;
    }
}
qint64 cleanCache(const QSet<QString>& protectedFiles) {
    const QString root = QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + "/edits";
    const QString current = cacheDirectory();
    qint64 removed = 0;
    for (const auto& info : QDir(root).entryInfoList({"session-*"}, QDir::Dirs | QDir::NoDotAndDotDot, QDir::Time | QDir::Reversed)) {
        if (info.isSymLink() || info.absoluteFilePath() == current) continue;
        QLockFile lease(info.absoluteFilePath() + "/session.lock");
        lease.setStaleLockTime(0);
        if (!lease.tryLock()) continue;
        bool protectedSession = false;
        for (const auto& path : protectedFiles)
            protectedSession |= QFileInfo(path).absoluteFilePath().startsWith(info.absoluteFilePath() + "/");
        if (protectedSession) continue;
        QDirIterator files(info.absoluteFilePath(), QDir::Files, QDirIterator::Subdirectories);
        qint64 bytes = 0;
        while (files.hasNext()) { files.next(); bytes += files.fileInfo().size(); }
        lease.unlock();
        if (QDir(info.absoluteFilePath()).removeRecursively()) removed += bytes;
    }
    return removed;
}
Project Project::fromJson(const QJsonObject& object) {
    Project project;
    if (object["sources"].toArray().size() > 10000 || object["clips"].toArray().size() > 10000)
        throw Error("Слишком большой проект");
    for (const auto& value : object["sources"].toArray()) {
        const auto item = value.toObject(); Source s;
        s.path = item["path"].toString(); s.duration = item["duration"].toDouble();
        s.size = item["size"].toInteger(); s.modified = item["modified"].toInteger();
        s.fingerprint = QByteArray::fromHex(item["fingerprint"].toString().toLatin1());
        s.sampleRate = item["sampleRate"].toInt(44100); s.channels = item["channels"].toInt(2); s.bits = item["bits"].toInt(16);
        if (s.path.isEmpty() || !std::isfinite(s.duration) || s.duration <= 0 || s.duration >= 86400 ||
            s.sampleRate < 8000 || s.sampleRate > 384000 || s.channels < 1 || s.channels > 8)
            throw Error("Повреждённый источник проекта");
        if (item["peaks"].toArray().size() > 10000) throw Error("Повреждённая волна проекта");
        for (const auto& peak : item["peaks"].toArray()) s.peaks << float(peak.toDouble());
        if (project.sources.contains(s.path)) throw Error("Повторяющийся источник проекта");
        project.sources[s.path] = s;
    }
    for (const auto& value : object["clips"].toArray()) {
        const auto item = value.toObject(); Clip c;
        c.id = item["id"].toString(); c.source = item["source"].toString(); c.originalSource = item["originalSource"].toString();
        c.lane = item["lane"].toInt(); c.start = item["start"].toDouble(); c.end = item["end"].toDouble();
        c.position = item["position"].toDouble(); c.gain = item["gain"].toDouble();
        c.fadeIn = item["fadeIn"].toDouble(); c.fadeOut = item["fadeOut"].toDouble();
        c.volume = item["volume"].toDouble(1); c.speed = item["speed"].toDouble(1);
        c.bass = item["bass"].toDouble(); c.mid = item["mid"].toDouble(); c.treble = item["treble"].toDouble();
        project.clips << c;
    }
    for (const auto& value : object["muted"].toArray()) project.muted.insert(value.toInt(-1));
    project.validate();
    return project;
}
QString scaleLyrics(const QString& text, double speed) {
    if (!std::isfinite(speed) || speed <= 0) throw Error("Неверная скорость текста");
    auto lines = parseLyrics(text, false);
    if (lines.isEmpty()) return text;
    for (auto& line : lines) { line.start /= speed; line.end /= speed; }
    return lrc(lines);
}
}
