#include "core.h"
#include <algorithm>
namespace sf {
static QString saveError(const QString& path, const QString& reason) {
    return "Не удалось сохранить файл: " + QDir::toNativeSeparators(path) + "\n" + reason;
}
struct Frame {
    QByteArray name, data, flags;
    QByteArray plain = {};
};
struct Tag {
    int version = 4;
    qint64 offset = 0;
    QList<Frame> frames;
};
static quint32 syncSize(const QByteArray& bytes) {
    if (bytes.size() != 4) throw Error("Повреждённый размер ID3");
    quint32 n = 0;
    for (char b : bytes) {
        if (quint8(b) & 128) throw Error("Неверный synchsafe-размер ID3");
        n = (n << 7) | (quint8(b) & 127);
    }
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
    if (h.size() != 10) throw Error("Оборванный заголовок ID3");
    result.version = quint8(h[3]);
    if (result.version != 2 && result.version != 3 && result.version != 4)
        throw Error("Неподдерживаемая версия ID3: " + QString::number(result.version));
    if ((quint8(h[5]) & (result.version == 4 ? 0x0f : result.version == 2 ? 0x3f : 0x1f)) || quint8(h[4]) != 0)
        throw Error("Неизвестные флаги или ревизия ID3");
    if (result.version == 2 && (quint8(h[5]) & 0x40)) throw Error("Сжатый ID3v2.2 не поддерживается; исходный файл сохранён");
    quint32 size = syncSize(h.mid(6, 4));
    if (size > 64000000)
        throw Error("Слишком большой ID3");
    result.offset = 10 + size + ((result.version == 4 && (quint8(h[5]) & 16)) ? 10 : 0);
    QByteArray body = file.read(size);
    if (body.size() != size)
        throw Error("Повреждённый ID3");
    if (result.offset > file.size()) throw Error("Оборванный footer ID3");
    if (quint8(h[5]) & 0x80) body.replace(QByteArray::fromHex("ff00"), QByteArray::fromHex("ff"));
    qsizetype at = 0;
    if (result.version != 2 && (quint8(h[5]) & 0x40)) {
        if (body.size() < 4) throw Error("Оборванный расширенный заголовок ID3");
        at = result.version == 4 ? syncSize(body.left(4)) : 4 + qFromBigEndian<quint32>(body.constData());
        if (at < 6 || at > body.size()) throw Error("Неверный расширенный заголовок ID3");
    }
    const int headerBytes = result.version == 2 ? 6 : 10;
    for (; at + headerBytes <= body.size();) {
        QByteArray id = body.mid(at, result.version == 2 ? 3 : 4);
        if (id[0] == 0)
            break;
        for (char b : id)
            if (!((b >= 'A' && b <= 'Z') || (b >= '0' && b <= '9')))
                throw Error("Повреждённый идентификатор ID3");
        quint32 count = result.version == 2 ? (quint32(quint8(body[at+3])) << 16) | (quint32(quint8(body[at+4])) << 8) | quint8(body[at+5]) : result.version == 4 ? syncSize(body.mid(at + 4, 4)) : qFromBigEndian<quint32>(body.constData() + at + 4);
        if (!count || count > quint32(body.size() - at - headerBytes))
            throw Error("Повреждённая длина ID3-кадра");
        Frame frame{id, body.mid(at + headerBytes, count), result.version == 2 ? QByteArray(2, 0) : body.mid(at + 8, 2)};
        if (result.version == 2) {
            static const QMap<QByteArray,QByteArray> names{{"TT2","TIT2"},{"TP1","TPE1"},{"TP2","TPE2"},{"TAL","TALB"},{"TCM","TCOM"},{"TYE","TYER"},{"TDA","TDAT"},{"TIM","TIME"},{"TRK","TRCK"},{"TPA","TPOS"},{"TCO","TCON"},{"TPB","TPUB"},{"TCR","TCOP"},{"COM","COMM"},{"ULT","USLT"},{"SLT","SYLT"},{"TXX","TXXX"},{"PIC","APIC"},{"TLE","TLEN"},{"TEN","TENC"},{"TSS","TSSE"},{"TT1","TIT1"},{"TT3","TIT3"},{"TLA","TLAN"},{"TBP","TBPM"},{"TKE","TKEY"},{"TP3","TPE3"},{"TP4","TPE4"},{"TOA","TOPE"},{"TOT","TOAL"},{"TOR","TORY"},{"TOL","TOLY"},{"TXT","TEXT"},{"WXX","WXXX"},{"WAF","WOAF"},{"WAR","WOAR"},{"WAS","WOAS"},{"WCM","WCOM"},{"WCP","WCOP"},{"WPB","WPUB"},{"UFI","UFID"},{"MCI","MCDI"},{"CNT","PCNT"},{"POP","POPM"},{"GEO","GEOB"},{"ETC","ETCO"},{"MLL","MLLT"},{"STC","SYTC"},{"REV","RVRB"},{"BUF","RBUF"},{"CRA","AENC"},{"LNK","LINK"},{"IPL","IPLS"},{"RVA","RVAD"},{"EQU","EQUA"}};
            if (!names.contains(id)) throw Error("Неизвестный кадр ID3v2.2: " + QString::fromLatin1(id) + ". Исходник сохранён.");
            frame.name = names[id];
            if (id == "PIC") {
                if (frame.data.size() < 6) throw Error("Повреждённый PIC");
                const auto mime = frame.data.mid(1, 3) == "JPG" ? QByteArray("image/jpeg") : frame.data.mid(1, 3) == "PNG" ? QByteArray("image/png") : QByteArray();
                if (mime.isEmpty()) throw Error("Неизвестный формат PIC");
                frame.data = frame.data.left(1) + mime + '\0' + frame.data.mid(4);
            }
        }
        auto decoded = frame.data;
        const quint8 flags = quint8(frame.flags[1]);
        if (result.version == 4 && (flags & 2)) {
            if (!(quint8(h[5]) & 0x80)) decoded.replace(QByteArray::fromHex("ff00"), QByteArray::fromHex("ff"));
            frame.data = decoded; frame.flags[1] = char(flags & ~2);
        }
        quint32 unpacked = 0;
        const bool compressed = result.version == 3 ? (flags & 0x80) : (flags & 8);
        if ((result.version == 3 && (flags & 0x40)) || (result.version == 4 && (flags & 4))) throw Error("Зашифрованный ID3-кадр требует ключ. Исходник сохранён.");
        if (result.version == 3 && compressed) { if (decoded.size() < 4) throw Error("Оборванный сжатый кадр"); unpacked = qFromBigEndian<quint32>(decoded.constData()); decoded.remove(0,4); }
        if ((result.version == 3 && (flags & 0x20)) || (result.version == 4 && (flags & 0x40))) { if (decoded.isEmpty()) throw Error("Оборванная группа ID3"); decoded.remove(0,1); }
        if (result.version == 4 && (flags & 1)) { unpacked = syncSize(decoded.left(4)); decoded.remove(0,4); }
        if (compressed) {
            if (!unpacked || unpacked > 64000000) throw Error("Слишком большой сжатый кадр ID3");
            QByteArray prefix(4, 0); qToBigEndian<quint32>(unpacked, prefix.data()); decoded = qUncompress(prefix + decoded);
            if (decoded.size() != unpacked) throw Error("Повреждённый сжатый кадр ID3");
        }
        frame.plain = decoded;
        result.frames << frame;
        at += headerBytes + count;
    }
    for (; at < body.size(); ++at) if (body[at] != 0) throw Error("Неразобранные данные в конце ID3");
    if (result.version == 2) result.version = 4;
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
static void compatiblePicture(Frame& frame) {
    if (frame.name != "APIC" || frame.data.size() < 5 || quint8(frame.flags[1]) != 0)
        return;
    int encoding = quint8(frame.data[0]);
    if (encoding != 2 && encoding != 3)
        return;
    int mimeEnd = frame.data.indexOf('\0', 1);
    if (mimeEnd < 0 || mimeEnd + 2 >= frame.data.size())
        return;
    int start = mimeEnd + 2, end = terminator(frame.data, start, encoding);
    int separatorSize = encoding == 3 ? 1 : 2;
    QString description = text(frame.data.mid(start, end - start - separatorSize), encoding);
    QByteArray prefix = frame.data.left(start);
    // Windows' MP3 thumbnail handler rejects UTF-8 APIC descriptions, even
    // when empty. Keep the image bytes intact; use Latin-1 or UTF-16 instead.
    if (QString::fromLatin1(description.toLatin1()) == description) {
        prefix[0] = 0;
        prefix += description.toLatin1();
        prefix += '\0';
    } else {
        prefix[0] = 1;
        prefix += QByteArray("\xff\xfe", 2);
        for (QChar c : description) {
            char bytes[2];
            qToLittleEndian<quint16>(c.unicode(), bytes);
            prefix.append(bytes, 2);
        }
        prefix += QByteArray(2, 0);
    }
    frame.data = prefix + frame.data.mid(end);
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
    for (const auto& raw : value.frames) {
        auto frame = raw; frame.data = raw.plain;
        checkpoint(cancel);
        if (frame.data.isEmpty())
            continue;
        int enc = quint8(frame.data[0]);
        if (frame.name == "SYLT") {
            result.synchronizedLyrics << frame.data;
        } else if (frame.name == "APIC") {
            int mimeEnd = frame.data.indexOf('\0', 1);
            if (mimeEnd < 0)
                continue;
            if (!result.cover.isEmpty() && (mimeEnd + 1 >= frame.data.size() || frame.data[mimeEnd + 1] != 3)) continue;
            int imageStart = terminator(frame.data, mimeEnd + 2, enc);
            result.coverMime = QString::fromLatin1(frame.data.mid(1, mimeEnd - 1));
            result.cover = frame.data.mid(imageStart);
        } else if (frame.name == "USLT" || frame.name == "COMM") {
            int body = terminator(frame.data, 4, enc);
            const QString key = frame.name == "USLT" ? "lyrics" : "comment";
            const auto language = QString::fromLatin1(frame.data.mid(1, 3));
            if (frame.name == "USLT") result.lyricTracks[language + "|" + text(frame.data.mid(4, body - 4), enc)] = text(frame.data.mid(body), enc);
            if (frame.name == "USLT" && !result.lyricLanguages.contains(language)) result.lyricLanguages << language;
            if (!result.values.contains(key) || language == "und") result.values[key] = text(frame.data.mid(body), enc);
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
                   const Cancel& cancel, const QList<QByteArray>& synchronizedLyrics, const QString& language, const QString& description) {
    checkpoint(cancel);
    if (!QRegularExpression("^[a-z]{3}$").match(language).hasMatch()) throw Error("Неверный код языка ID3");
    if (QFileInfo(path).suffix().toLower() != "mp3") {
        const QString suffix = QFileInfo(path).suffix().toLower();
        Metadata previous;
        if (replaceAll && preserveLyrics)
            previous = readMetadata(path, cancel);
        QString temporary = QFileInfo(path).absolutePath() + "/.metadata-" +
                            QUuid::createUuid().toString(QUuid::Id128) + "." +
                            QFileInfo(path).suffix();
        auto cleanup = qScopeGuard([&] { QFile::remove(temporary); });
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
            if (!(preserveLyrics && i.key() == "lyrics"))
                args << "-metadata" << i.key() + "=" + i.value();
        if (replaceCover && cover.isEmpty()) {
            args = {"-i", path, "-map", "0:a", "-map_metadata", replaceAll ? "-1" : "0", "-c", "copy"};
            for (auto i = values.begin(); i != values.end(); ++i)
                if (!(preserveLyrics && i.key() == "lyrics")) args << "-metadata" << i.key() + "=" + i.value();
            if (suffix == "ogg" || suffix == "opus") args << "-metadata" << "METADATA_BLOCK_PICTURE=";
        }
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
            throw Error(saveError(path, destination.errorString()));
        while (!input.atEnd()) {
            checkpoint(cancel);
            if (destination.write(input.read(1024 * 1024)) < 0) throw Error(destination.errorString());
        }
        if (!destination.commit())
            throw Error(saveError(path, destination.errorString()));
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
        if (names.contains(i.key()) &&
            !(preserveLyrics && i.key() == "lyrics"))
            changes.insert(names[i.key()]);
    if (changes.contains("TDRC"))
        { changes.insert("TYER"); changes.insert("TDAT"); changes.insert("TIME"); }
    if (replaceCover)
        changes.insert("APIC");
    QList<Frame> frames;
    for (auto& f : original.frames) {
        bool retained = !changes.contains(f.name);
        if ((f.name == "USLT" || f.name == "COMM") && changes.contains(f.name)) {
            const auto payload = f.plain.isEmpty() ? f.data : f.plain;
            const int enc = payload.isEmpty() ? 0 : quint8(payload[0]);
            const int body = terminator(payload, 4, enc);
            retained = payload.mid(1,3) != language.toLatin1() || text(payload.mid(4, body-4), enc) != description;
        }
        if (f.name == "APIC" && replaceCover) {
            const auto payload = f.plain.isEmpty() ? f.data : f.plain; const int mime = payload.indexOf('\0',1);
            if (mime >= 0 && mime+1 < payload.size() && payload[mime+1] != 3) retained = true;
        }
        if (f.name == "SYLT" && !synchronizedLyrics.isEmpty()) retained = false;
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
        QByteArray data(1, char(original.version == 3 ? 1 : 3));
        if (i.key() == "lyrics" || i.key() == "comment") {
            data += language.toLatin1();
            if (original.version == 3) {
                data += QByteArray::fromHex("fffe");
                for (const auto ch : description) { char bytes[2]; qToLittleEndian<quint16>(ch.unicode(), bytes); data.append(bytes,2); }
            } else data += description.toUtf8();
            data += QByteArray(original.version == 3 ? 2 : 1, 0);
        }
        if (original.version == 3) {
            data += QByteArray::fromHex("fffe");
            for (const auto ch : i.value()) { char bytes[2]; qToLittleEndian<quint16>(ch.unicode(), bytes); data.append(bytes, 2); }
        } else data += i.value().toUtf8();
        frames << Frame{i.key() == "date" && original.version == 3 ? QByteArray("TYER") : names[i.key()], data, QByteArray(2, 0)};
    }
    if (replaceCover && !cover.isEmpty()) {
        QByteArray data(1, char(0));
        data += cover.startsWith("\xff\xd8") ? "image/jpeg" : "image/png";
        data += '\0';
        data += char(3);
        data += '\0';
        data += cover;
        frames << Frame{"APIC", data, QByteArray(2, 0)};
    }
    for (auto& frame : frames)
        compatiblePicture(frame);
    for (const auto& data : synchronizedLyrics) frames << Frame{"SYLT", data, QByteArray(2, 0)};
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
        throw Error(saveError(path, output.errorString()));
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
        throw Error(saveError(path, output.errorString()));
}
QString saveLyrics(const QString& audio, const QString& text, const QString& format,
                const Cancel& cancel, const QString& language, const QString& description) {
    if (text.trimmed().isEmpty())
        throw Error("Нет текста для сохранения");
    if (text.contains(QRegularExpression("\\[\\d+:")))
        parseLyrics(text, true);
    if (format == "embedded" && QFileInfo(audio).suffix().toLower() != "mp3")
        throw Error("Встроенная запись текста доступна для MP3. Выберите LRC или TXT.");
    if (format == "embedded") {
        writeMetadata(audio, {{"lyrics", text}}, false, false, {}, false, cancel, {}, language, description);
        return audio;
    } else {
        QString name = QFileInfo(audio).absolutePath() + "/" + QFileInfo(audio).completeBaseName() +
                       "." + (format == "lrc" ? "lrc" : "txt");
        return saveLyricsFile(name, text, format, cancel);
    }
}
QString saveLyricsFile(const QString& name, const QString& text, const QString& format, const Cancel& cancel) {
        checkpoint(cancel);
        if (text.trimmed().isEmpty()) throw Error("Нет текста для сохранения");
        if (format == "lrc" && parseLyrics(text, false).isEmpty())
            throw Error("Для LRC нужны таймкоды");
        if (format == "lrc") parseLyrics(text, true);
        backupFile(name);
        QSaveFile output(name);
        if (!output.open(QIODevice::WriteOnly))
            throw Error(saveError(name, output.errorString()));
        output.write(((format == "txt" ? plainLyrics(text) : text).trimmed() + "\n").toUtf8());
        checkpoint(cancel);
        if (!output.commit())
            throw Error(saveError(name, output.errorString()));
        return name;
}
void transferLyrics(const QString& source, const QString& target, double speed, const Cancel& cancel) {
    if (QFileInfo(target).suffix().compare("mp3", Qt::CaseInsensitive) != 0) return;
    auto metadata = readMetadata(source, cancel);
    for (auto& payload : metadata.synchronizedLyrics) {
        if (payload.size() < 7) throw Error("Повреждённый SYLT");
        const int enc = quint8(payload[0]);
        const int format = quint8(payload[4]);
        const int rate = readSource(source, cancel, false).sampleRate;
        qsizetype at = terminator(payload, 6, enc);
        payload[4] = 2;
        while (at < payload.size()) {
            at = terminator(payload, at, enc);
            if (at + 4 > payload.size()) throw Error("Оборванная метка SYLT");
            double ms = qFromBigEndian<quint32>(payload.constData() + at);
            if (format == 1) ms *= (rate >= 32000 ? 1152. : 576.) * 1000 / rate;
            else if (format != 2) throw Error("Неизвестный формат меток SYLT");
            qToBigEndian<quint32>(quint32(qRound64(ms / speed)), payload.data() + at);
            at += 4;
        }
    }
    QMap<QString, QString> lyrics;
    if (metadata.values.contains("lyrics")) lyrics["lyrics"] = scaleLyrics(metadata.values["lyrics"], speed);
    if (!lyrics.isEmpty() || !metadata.synchronizedLyrics.isEmpty())
        writeMetadata(target, lyrics, false, false, {}, false, cancel, metadata.synchronizedLyrics);
    for (auto it = metadata.lyricTracks.cbegin(); it != metadata.lyricTracks.cend(); ++it)
        writeMetadata(target, {{"lyrics", scaleLyrics(it.value(), speed)}}, false, false, {}, false, cancel, {}, it.key().section('|',0,0), it.key().section('|',1));
}
} // namespace sf
