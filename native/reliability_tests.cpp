#include "core.h"
#include "speech.h"
#include <QtTest>

class ReliabilityTests : public QObject {
    Q_OBJECT
    static void write(const QString& path, const QByteArray& data) { QFile f(path); if (!f.open(QIODevice::WriteOnly) || f.write(data) != data.size()) throw sf::Error(f.errorString()); }
    static QByteArray read(const QString& path) { QFile f(path); if (!f.open(QIODevice::ReadOnly)) throw sf::Error(f.errorString()); return f.readAll(); }
    QString tone(QTemporaryDir& dir, const QString& name = "test.wav", double seconds = .1) {
        const auto path = dir.filePath(name); sf::ffmpeg({"-f", "lavfi", "-i", "sine=frequency=440:duration=" + QString::number(seconds), path}); return path;
    }
  private slots:
    void initTestCase() { Q_INIT_RESOURCE(resources); }
    void malformedTagsNeverOverwrite() {
        QTemporaryDir dir;
        for (const auto& data : {QByteArray("ID3"), QByteArray::fromHex("49443304"), QByteArray::fromHex("49443304000000000008") + "PRIV1234"}) {
            const auto path = dir.filePath("bad.mp3"); write(path, data);
            QVERIFY_EXCEPTION_THROWN(sf::writeMetadata(path, {{"title", "x"}}), sf::Error); QCOMPARE(read(path), data);
        }
    }
    void projectRoundTripAndDuplicateIds() {
        sf::Project p; const auto id = p.add({"one.wav", 10, {.1f, .2f}}); p.get(id).originalSource = "original.wav";
        const auto copy = sf::Project::fromJson(p.json()); QCOMPARE(copy.clips.size(), 1); QCOMPARE(copy.clips[0].originalSource, QString("original.wav")); QCOMPARE(copy.sources["one.wav"].peaks.size(), 2);
        p.clips << p.clips.first(); QVERIFY_EXCEPTION_THROWN(p.validate(), sf::Error);
    }
    void legacyAndMultilingualTags() {
        QTemporaryDir dir; const auto path = dir.filePath("legacy.mp3");
        auto synchsafe = [](quint32 value) { QByteArray bytes(4, 0); for (int i = 3; i >= 0; --i) { bytes[i] = char(value & 127); value >>= 7; } return bytes; };
        const auto title = QByteArray("\0Legacy", 7);
        const auto frame22 = QByteArray("TT2") + QByteArray::fromHex("000007") + title;
        write(path, QByteArray::fromHex("494433020000") + synchsafe(frame22.size()) + frame22 + "audio");
        QCOMPARE(sf::readMetadata(path).values["title"], QString("Legacy"));
        sf::writeMetadata(path, {{"artist", "Исполнитель"}}); QCOMPARE(sf::readMetadata(path).values["title"], QString("Legacy"));
        const auto compressed = qCompress(title); QByteArray size(4, 0); qToBigEndian<quint32>(compressed.size(), size.data());
        const auto frame23 = QByteArray("TIT2") + size + QByteArray::fromHex("0080") + compressed;
        write(path, QByteArray::fromHex("494433030040") + synchsafe(frame23.size() + 10) + QByteArray::fromHex("00000006000000000000") + frame23 + "audio");
        QCOMPARE(sf::readMetadata(path).values["title"], QString("Legacy"));
        sf::writeMetadata(path, {{"artist", "Исполнитель"}}); QCOMPARE(quint8(read(path)[3]), quint8(3)); QCOMPARE(sf::readMetadata(path).values["artist"], QString("Исполнитель"));
        sf::writeMetadata(path, {{"lyrics", "Русский текст"}}, false, false, {}, false, {}, {}, "rus", "original");
        sf::writeMetadata(path, {{"lyrics", "English text"}}, false, false, {}, false, {}, {}, "eng", "translation");
        const auto tracks = sf::readMetadata(path).lyricTracks; QCOMPARE(tracks.value("rus|original"), QString("Русский текст")); QCOMPARE(tracks.value("eng|translation"), QString("English text"));
        sf::writeMetadata(path, {{"lyrics", "Updated"}}, false, false, {}, false, {}, {}, "eng", "translation");
        QCOMPARE(sf::readMetadata(path).lyricTracks.value("rus|original"), QString("Русский текст")); QCOMPARE(sf::readMetadata(path).lyricTracks.value("eng|translation"), QString("Updated"));
    }
    void sidecarBackupAndUnsupportedEmbedding() {
        QTemporaryDir dir; const auto wave = tone(dir); write(dir.filePath("test.lrc"), "old text");
        sf::saveLyrics(wave, "[00:00.010]new text", "lrc");
        const auto backups = QDir(dir.filePath(".sonicforge-backups")).entryList(QDir::Files); QCOMPARE(backups.size(), 1);
        QCOMPARE(read(dir.filePath(".sonicforge-backups/" + backups.first())), QByteArray("old text"));
        QVERIFY_EXCEPTION_THROWN(sf::saveLyrics(wave, "words", "embedded"), sf::Error);
    }
    void publicationRollsBackAndNeverOverwrites() {
        QTemporaryDir dir; const auto a = dir.filePath("a"), b = dir.filePath("b"); write(a, "original");
        QVERIFY_EXCEPTION_THROWN(sf::publishFiles({{a, b}, {dir.filePath("missing"), dir.filePath("c")}}), sf::Error);
        QCOMPARE(read(a), QByteArray("original")); QVERIFY(!QFileInfo::exists(b));
        write(b, "existing"); QVERIFY_EXCEPTION_THROWN(sf::publishFiles({{a, b}}), sf::Error); QCOMPARE(read(b), QByteArray("existing"));
    }
    void originalContentFingerprint() {
        QTemporaryDir dir; const auto wave = tone(dir); sf::Project p; p.add(sf::readSource(wave));
        const auto stamp = QFileInfo(wave).lastModified(); auto bytes = read(wave); bytes[bytes.size()-1] ^= 1; write(wave, bytes);
        QFile f(wave); QVERIFY(f.open(QIODevice::ReadWrite)); QVERIFY(f.setFileTime(stamp, QFileDevice::FileModificationTime)); f.close();
        QVERIFY_EXCEPTION_THROWN(sf::render(p, dir.filePath("out.wav")), sf::Error);
    }
    void largeProjectAndPrecision() {
        try {
        QTemporaryDir dir; const auto wave = tone(dir); const auto source = sf::readSource(wave);
        sf::Project p; for (int i=0;i<150;++i) p.add(source);
        const auto out = dir.filePath("many.wav"); sf::render(p, out); QVERIFY(std::abs(sf::readSource(out, {}, false).duration - 15) < .02);
        const auto hires = dir.filePath("96k.wav"); sf::ffmpeg({"-i", wave, "-ar", "96000", "-ac", "6", "-c:a", "pcm_s24le", hires});
        p = {}; p.add(sf::readSource(hires)); sf::render(p, dir.filePath("precision.wav"));
        const auto info = sf::readSource(dir.filePath("precision.wav"), {}, false); QCOMPARE(info.sampleRate, 96000); QCOMPARE(info.channels, 6); QVERIFY(info.bits >= 24);
        } catch (const std::exception& error) { QFAIL(error.what()); }
    }
    void audioProcessingKeepsAndScalesSylt() {
        QTemporaryDir dir; const auto wave = tone(dir, "tone.wav", 1), mp3 = dir.filePath("lyrics.mp3"), out = dir.filePath("fast.mp3");
        sf::ffmpeg({"-i", wave, mp3});
        const auto payload = QByteArray::fromHex("00656e67020100") + QByteArray("hello\0",6) + QByteArray::fromHex("00000320");
        sf::writeMetadata(mp3, {{"lyrics", "[00:00.800]hello"}}, false, false, {}, false, {}, {payload});
        sf::AudioOptions options; options.speed = 2; sf::normalize(mp3, out, options);
        const auto tags = sf::readMetadata(out); QCOMPARE(tags.synchronizedLyrics.size(), 1);
        QCOMPARE(qFromBigEndian<quint32>(tags.synchronizedLyrics[0].constData()+tags.synchronizedLyrics[0].size()-4), quint32(400));
        QVERIFY(tags.values["lyrics"].contains("[00:00.400]"));
    }
    void coverRemovalAndFieldDeletion() {
        QTemporaryDir dir; const auto wave = tone(dir), flac = dir.filePath("test.flac"); sf::ffmpeg({"-i", wave, flac});
        QImage image(8,8,QImage::Format_RGB32); image.fill(Qt::red); QByteArray bytes; QBuffer buffer(&bytes); QVERIFY(buffer.open(QIODevice::WriteOnly)); QVERIFY(image.save(&buffer,"PNG"));
        sf::writeMetadata(flac, {{"title","keep"}}, false, true, bytes, true); QVERIFY(!sf::readMetadata(flac).cover.isEmpty());
        sf::writeMetadata(flac, {{"title", ""}}, false, true, {}, true); QVERIFY(sf::readMetadata(flac).cover.isEmpty()); QVERIFY(sf::readMetadata(flac).values["title"].isEmpty());
    }
    void encodedPeakAndTaskLimits() {
        QTemporaryDir dir; const auto wave = dir.filePath("square.wav"), out = dir.filePath("limited.mp3");
        sf::ffmpeg({"-f", "lavfi", "-i", "aevalsrc=0.8*sgn(sin(2*PI*8191*t)):s=44100:d=1", wave});
        sf::AudioOptions options; options.lufs = -9; options.truePeak = -.5; options.gain = 4; options.quality = 9;
        sf::normalize(wave, out, options);
        const auto stats = sf::analyze(out); QVERIFY(stats["truePeak"].toString().toDouble() <= -.45);
        QVERIFY_EXCEPTION_THROWN(sf::checkCacheCapacity(sf::uniqueFile(), 129LL * 1024 * 1024 * 1024), sf::Error);
        const auto previous = qgetenv("SF_PROCESS_TIMEOUT_MS"); auto restore = qScopeGuard([&] { if (previous.isNull()) qunsetenv("SF_PROCESS_TIMEOUT_MS"); else qputenv("SF_PROCESS_TIMEOUT_MS", previous); });
        qputenv("SF_PROCESS_TIMEOUT_MS", "1000"); QElapsedTimer timer; timer.start();
        QVERIFY_EXCEPTION_THROWN(sf::ffmpeg({"-re", "-f", "lavfi", "-i", "sine=duration=60", "-f", "null", "-"}), sf::Error);
        QVERIFY(timer.elapsed() < 5000);
    }
    void textEncodingsAndHeaders() {
        QTemporaryDir dir; const auto path = dir.filePath("utf16.txt"); write(path, QByteArray::fromHex("fffe1f0440043804320435044204")); QCOMPARE(sf::readTextFile(path), QString::fromUtf8("Привет"));
        QCOMPARE(sf::plainLyrics("[ar:Artist]\n[offset:100]\n[00:01.000]hello"), QString("hello"));
    }
    void checkpointedAlignment() {
        const int frames=14000, classes=3; QVector<float> probabilities(frames*classes, -10); QVector<int> tokens(5000);
        for(int i=0;i<tokens.size();++i) tokens[i]=1+i%2;
        for(int i=0;i<frames;++i) probabilities[i*classes]=-.1f;
        for(int i=0;i<tokens.size();++i) probabilities[(i+100)*classes+tokens[i]]=0;
        const auto match=sf::ctcViterbi(probabilities,frames,classes,tokens);
        QVERIFY(match.has_value()); QCOMPARE(match->first.size(),tokens.size()); QVERIFY(match->last.last()>=match->first.first());
    }
};
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv); ReliabilityTests tests;
    try { return QTest::qExec(&tests, argc, argv); }
    catch (const std::exception& error) { qCritical().noquote() << error.what(); return 1; }
}
#include "reliability_tests.moc"
