#include "core.h"
#include <algorithm>
namespace sf {
struct Frame {
    QByteArray name, data, flags;
};
struct Tag {
    int version = 4;
    qint64 offset = 0;
    QList<Frame> frames;
};
static quint32 syncSize(const QByteArray& bytes) {
    quint32 n = 0;
    for (char b : bytes)
        n = (n << 7) | (quint8(b) & 127);
    return n;
}
static QByteArray syncBytes(quint32 n) {
    QByteArray b(4, 0);
    for (int i = 3; i >= 0; --i) {
        b[i] = char(n & 127);
        n >>= 7;
    }
    return b;
}
static Tag tag(QFile& file) {
    file.seek(0);
    QByteArray h = file.read(10);
    Tag result;
    if (h.left(3) != "ID3") {
        file.seek(0);
        return result;
    }
    result.version = quint8(h[3]);
    if (result.version != 3 && result.version != 4)
        throw Error("Неподдерживаемая версия ID3: " + QString::number(result.version));
    if (quint8(h[5]) & 0xc0)
        throw Error(
            "Расширенные или несинхронизированные ID3 отклонены для безопасного сохранения");
    quint32 size = syncSize(h.mid(6, 4));
    if (size > 64000000)
        throw Error("Слишком большой ID3");
    result.offset = 10 + size + ((result.version == 4 && (quint8(h[5]) & 16)) ? 10 : 0);
    QByteArray body = file.read(size);
    if (body.size() != size)
        throw Error("Повреждённый ID3");
    for (qsizetype at = 0; at + 10 <= body.size();) {
        QByteArray id = body.mid(at, 4);
        if (id[0] == 0)
            break;
        for (char b : id)
            if (!((b >= 'A' && b <= 'Z') || (b >= '0' && b <= '9')))
                throw Error("Повреждённый идентификатор ID3");
        quint32 count = result.version == 4 ? syncSize(body.mid(at + 4, 4))
                                            : qFromBigEndian<quint32>(body.constData() + at + 4);
        if (count > quint32(body.size() - at - 10))
            throw Error("Повреждённая длина ID3-кадра");
        result.frames << Frame{id, body.mid(at + 10, count), body.mid(at + 8, 2)};
        at += 10 + count;
    }
    return result;
}
static QString text(const QByteArray& data, int encoding) {
    if (encoding == 3)
        return QString::fromUtf8(data).remove(QChar(0));
    if (encoding == 0)
        return QString::fromLatin1(data).remove(QChar(0));
    QString result;
    bool little = encoding == 1 && data.startsWith("\xff\xfe");
    for (int at = 0; at + 1 < data.size(); at += 2) {
        quint16 c = little ? qFromLittleEndian<quint16>(data.constData() + at)
                           : qFromBigEndian<quint16>(data.constData() + at);
        if (c && c != 0xfeff && c != 0xfffe)
            result += QChar(c);
    }
    return result;
}
static int terminator(const QByteArray& data, int at, int enc) {
    if (enc == 0 || enc == 3) {
        int pos = data.indexOf('\0', at);
        return pos < 0 ? data.size() : pos + 1;
    }
    for (int i = at; i + 1 < data.size(); i += 2)
        if (data[i] == 0 && data[i + 1] == 0)
            return i + 2;
    return data.size();
}
static QMap<QString, QByteArray> frameNames() {
    return {{"title", "TIT2"},        {"artist", "TPE1"},    {"album", "TALB"},
            {"album_artist", "TPE2"}, {"composer", "TCOM"},  {"date", "TDRC"},
            {"track", "TRCK"},        {"disc", "TPOS"},      {"genre", "TCON"},
            {"publisher", "TPUB"},    {"copyright", "TCOP"}, {"comment", "COMM"},
            {"lyrics", "USLT"}};
}
Metadata readMetadata(const QString& path, const Cancel& cancel) {
    Metadata result;
    if (QFileInfo(path).suffix().toLower() != "mp3") {
        auto doc = QJsonDocument::fromJson(
            process(executable("ffprobe"),
                    {"-v", "error", "-show_format", "-show_streams", "-of", "json", path}, cancel));
        auto values = doc.object()["format"].toObject()["tags"].toObject();
        for (auto i = values.begin(); i != values.end(); ++i)
            result.values[i.key().toLower()] = i.value().toString();
        for (auto stream : doc.object()["streams"].toArray()) {
            auto value = stream.toObject();
            auto streamTags = value["tags"].toObject();
            for (auto it = streamTags.begin(); it != streamTags.end(); ++it)
                if (!result.values.contains(it.key().toLower()))
                    result.values[it.key().toLower()] = it.value().toString();
            if (value["disposition"].toObject()["attached_pic"].toInt() == 1) {
                result.cover =
                    ffmpeg({"-i", path, "-map", "0:" + QString::number(value["index"].toInt()),
                            "-frames:v", "1", "-c:v", "copy", "-f", "image2pipe", "pipe:1"},
                           cancel);
                result.coverMime = result.cover.startsWith("\xff\xd8") ? "image/jpeg" : "image/png";
            }
        }
        for (const auto& alias : QList<QPair<QString, QString>>{{"albumartist", "album_artist"},
                                                                {"tracknumber", "track"},
                                                                {"discnumber", "disc"},
                                                                {"year", "date"},
                                                                {"unsyncedlyrics", "lyrics"},
                                                                {"lyrics-eng", "lyrics"}})
            if (!result.values.contains(alias.second) && result.values.contains(alias.first))
                result.values[alias.second] = result.values[alias.first];
        return result;
    }
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        throw Error(file.errorString());
    auto value = tag(file);
    const auto names = frameNames();
    for (auto& frame : value.frames) {
        checkpoint(cancel);
        if (frame.data.isEmpty())
            continue;
        int enc = quint8(frame.data[0]);
        if (frame.name == "APIC") {
            int mimeEnd = frame.data.indexOf('\0', 1);
            if (mimeEnd < 0)
                continue;
            int imageStart = terminator(frame.data, mimeEnd + 2, enc);
            result.coverMime = QString::fromLatin1(frame.data.mid(1, mimeEnd - 1));
            result.cover = frame.data.mid(imageStart);
        } else if (frame.name == "USLT" || frame.name == "COMM") {
            int body = terminator(frame.data, 4, enc);
            result.values[frame.name == "USLT" ? "lyrics" : "comment"] =
                text(frame.data.mid(body), enc);
        } else if (frame.name == "TXXX") {
            int body = terminator(frame.data, 1, enc);
            QString name = text(frame.data.mid(1, body - 1), enc);
            result.values[name] = text(frame.data.mid(body), enc);
        } else {
            auto it = std::find_if(names.begin(), names.end(),
                                   [&](const auto& id) { return id == frame.name; });
            if (it != names.end())
                result.values[it.key()] = text(frame.data.mid(1), enc);
            else if (frame.name == "TYER" && !result.values.contains("date"))
                result.values["date"] = text(frame.data.mid(1), enc);
        }
    }
    return result;
}
void writeMetadata(const QString& path, const QMap<QString, QString>& values, bool replaceAll,
                   bool preserveLyrics, const QByteArray& cover, bool replaceCover,
                   const Cancel& cancel) {
    checkpoint(cancel);
    if (QFileInfo(path).suffix().toLower() != "mp3") {
        const QString suffix = QFileInfo(path).suffix().toLower();
        Metadata previous;
        if (replaceAll && preserveLyrics)
            previous = readMetadata(path, cancel);
        QString temporary = QFileInfo(path).absolutePath() + "/.metadata-" +
                            QUuid::createUuid().toString(QUuid::Id128) + "." +
                            QFileInfo(path).suffix();
        QStringList args{"-i", path, "-map", "0", "-c", "copy"};
        QTemporaryFile picture(QDir::tempPath() + "/sonicforge-cover-XXXXXX.png");
        if (replaceCover && !cover.isEmpty() && (suffix == "flac" || suffix == "m4a")) {
            if (!picture.open())
                throw Error(picture.errorString());
            picture.write(cover);
            picture.close();
            args = {"-i",  path, "-i",   picture.fileName(), "-map",        "0:a", "-map",
                    "1:v", "-c", "copy", "-disposition:v",   "attached_pic"};
        }
        if (replaceAll)
            args << "-map_metadata" << "-1";
        if (replaceAll && preserveLyrics && !previous.values.value("lyrics").isEmpty())
            args << "-metadata" << "lyrics=" + previous.values.value("lyrics");
        for (auto i = values.begin(); i != values.end(); ++i)
            if (!(preserveLyrics && i.key() == "lyrics") && (!i.value().isEmpty() || replaceAll))
                args << "-metadata" << i.key() + "=" + i.value();
        if (replaceCover && !cover.isEmpty() && (suffix == "ogg" || suffix == "opus")) {
            QByteArray block;
            QDataStream stream(&block, QIODevice::WriteOnly);
            stream.setByteOrder(QDataStream::BigEndian);
            QByteArray mime = cover.startsWith("\xff\xd8") ? "image/jpeg" : "image/png";
            QImage image = QImage::fromData(cover);
            stream << quint32(3) << quint32(mime.size());
            stream.writeRawData(mime.constData(), mime.size());
            stream << quint32(0) << quint32(image.width()) << quint32(image.height()) << quint32(24)
                   << quint32(0) << quint32(cover.size());
            stream.writeRawData(cover.constData(), cover.size());
            args << "-metadata"
                 << "METADATA_BLOCK_PICTURE=" + QString::fromLatin1(block.toBase64());
        }
        ffmpeg(args + QStringList{temporary}, cancel);
        QFile input(temporary);
        if (!input.open(QIODevice::ReadOnly))
            throw Error(input.errorString());
        QSaveFile destination(path);
        if (!destination.open(QIODevice::WriteOnly))
            throw Error(destination.errorString());
        while (!input.atEnd()) {
            checkpoint(cancel);
            destination.write(input.read(1024 * 1024));
        }
        if (!destination.commit())
            throw Error(destination.errorString());
        input.close();
        QFile::remove(temporary);
        return;
    }
    QFile input(path);
    if (!input.open(QIODevice::ReadOnly))
        throw Error(input.errorString());
    Tag original = tag(input);
    auto names = frameNames();
    QSet<QByteArray> changes;
    for (auto i = values.begin(); i != values.end(); ++i)
        if ((!i.value().isEmpty() || replaceAll) && names.contains(i.key()) &&
            !(preserveLyrics && i.key() == "lyrics"))
            changes.insert(names[i.key()]);
    if (changes.contains("TDRC"))
        changes.insert("TYER");
    if (replaceCover)
        changes.insert("APIC");
    QList<Frame> frames;
    for (auto& f : original.frames) {
        bool retained = !changes.contains(f.name);
        if (replaceAll && f.name != "APIC" &&
            !(preserveLyrics && (f.name == "USLT" || f.name == "SYLT")))
            retained = false;
        if (retained)
            frames << f;
    }
    for (auto i = values.begin(); i != values.end(); ++i) {
        if (!names.contains(i.key()) || i.value().isEmpty() ||
            (preserveLyrics && i.key() == "lyrics"))
            continue;
        QByteArray data(1, char(3));
        if (i.key() == "lyrics" || i.key() == "comment") {
            data += "und";
            data += '\0';
        }
        data += i.value().toUtf8();
        frames << Frame{names[i.key()], data, QByteArray(2, 0)};
    }
    if (replaceCover && !cover.isEmpty()) {
        QByteArray data(1, char(3));
        data += cover.startsWith("\xff\xd8") ? "image/jpeg" : "image/png";
        data += '\0';
        data += char(3);
        data += '\0';
        data += cover;
        frames << Frame{"APIC", data, QByteArray(2, 0)};
    }
    // Publish UTF-8 frames as ID3v2.4. Retained v2.3 text, artwork and timed
    // lyric payloads remain valid; translate frame status flags explicitly.
    if (original.version == 3) {
        for (auto& frame : frames) {
            if (quint8(frame.flags[1]) != 0)
                throw Error("Сжатые или зашифрованные ID3-кадры не изменяются");
            frame.flags[0] = char((quint8(frame.flags[0]) & 0xe0) >> 1);
        }
    }
    original.version = 4;
    QByteArray body;
    for (auto& f : frames) {
        body += f.name;
        QByteArray size(4, 0);
        if (original.version == 4)
            size = syncBytes(f.data.size());
        else
            qToBigEndian<quint32>(f.data.size(), size.data());
        body += size;
        body += f.flags;
        body += f.data;
    }
    body += QByteArray(1024, 0);
    QByteArray header = "ID3";
    header += char(original.version);
    header += QByteArray(2, 0);
    header += syncBytes(body.size());
    QSaveFile output(path);
    if (!output.open(QIODevice::WriteOnly))
        throw Error(output.errorString());
    output.write(header);
    output.write(body);
    input.seek(original.offset);
    while (!input.atEnd()) {
        checkpoint(cancel);
        if (output.write(input.read(1024 * 1024)) < 0)
            throw Error(output.errorString());
    }
    input.close();
    checkpoint(cancel);
    if (!output.commit())
        throw Error(output.errorString());
}
void saveLyrics(const QString& audio, const QString& text, const QString& format,
                const Cancel& cancel) {
    if (text.trimmed().isEmpty())
        throw Error("Нет текста для сохранения");
    if (text.contains(QRegularExpression("\\[\\d+:")))
        parseLyrics(text, true);
    if (format == "embedded" && QFileInfo(audio).suffix().toLower() == "mp3")
        writeMetadata(audio, {{"lyrics", text}}, false, false, {}, false, cancel);
    else {
        QString name = QFileInfo(audio).absolutePath() + "/" + QFileInfo(audio).completeBaseName() +
                       "." + (format == "lrc" ? "lrc" : "txt");
        if (format == "lrc" && parseLyrics(text, false).isEmpty())
            throw Error("Для LRC нужны таймкоды");
        QSaveFile output(name);
        if (!output.open(QIODevice::WriteOnly))
            throw Error(output.errorString());
        output.write((text.trimmed() + "\n").toUtf8());
        if (!output.commit())
            throw Error(output.errorString());
    }
}
} // namespace sf
