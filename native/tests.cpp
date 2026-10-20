#include "core.h"
#include "speech.h"
#include <QtTest>
#include <cmath>
class CoreTests : public QObject {
    Q_OBJECT
    QString tone(QTemporaryDir& directory, const QString& name, double seconds = 6,
                 double frequency = 220, double amplitude = .12) {
        QVector<float> samples(qRound(seconds * 8000));
        for (int i = 0; i < samples.size(); ++i)
            samples[i] = amplitude * std::sin(2 * 3.141592653589793 * frequency * i / 8000);
        QString path = directory.filePath(name + ".wav");
        sf::writeWav(path, samples, 8000, 1);
        return path;
    }
    double rms(const QVector<float>& values) {
        double sum = 0;
        for (float value : values)
            sum += value * value;
        return std::sqrt(sum / qMax(qsizetype(1), values.size()));
    }
  private slots:
    void initTestCase() {
        Q_INIT_RESOURCE(resources);
        QDir fonts(QDir::currentPath() + "/assets/fonts");
        for (const auto& name : fonts.entryList({"*.ttf"}, QDir::Files))
            QFontDatabase::addApplicationFont(fonts.filePath(name));
    }
    void timeline() {
        sf::Project project;
        auto first = project.add(sf::Source{"first.wav", 10, {.1f}});
        auto next = project.add(sf::Source{"second.wav", 12, {.2f}});
        QCOMPARE(project.get(next).position, 10.);
        auto right = project.split(first, 4);
        QCOMPARE(project.get(first).duration(), 4.);
        QCOMPARE(project.get(right).position, 4.);
        QCOMPARE(project.duration(), 22.);
        project.validate();
    }
    void rejectsOverlap() {
        sf::Project project;
        project.add(sf::Source{"a.wav", 10});
        project.add(sf::Source{"b.wav", 5});
        project.clips[1].position = 3;
        QVERIFY_EXCEPTION_THROWN(project.validate(), sf::Error);
    }
    void timing() {
        QCOMPARE(sf::timestamp(62.345), QString("01:02.35"));
        QCOMPARE(sf::timestamp(62.345, 3), QString("01:02.345"));
        auto cue = sf::lrc({sf::Lyric{10 - sf::LyricLead, 11, "Cue"}});
        QCOMPARE(cue, QString("[00:09.955]Cue"));
        QCOMPARE(sf::parseTime("01:02.345"), 62.345);
        QVERIFY_EXCEPTION_THROWN(sf::parseTime("01:77"), sf::Error);
        auto lines = sf::parseLyrics("[00:01.20]Первая\n[00:03.40]Повтор\n[00:05.60]Повтор");
        QCOMPARE(lines.size(), 3);
        QCOMPARE(lines[1].end, 5.6);
        QCOMPARE(sf::lrc(lines),
                 QString("[00:01.200]Первая\n[00:03.400]Повтор\n[00:05.600]Повтор"));
        lines = sf::parseLyrics("[ti:Песня]\n[00:04][00:01.20]Припев\n[offset:-100]");
        QCOMPARE(lines.size(), 2);
        QVERIFY(std::abs(lines[0].start - 1.1) < 1e-9);
        QVERIFY(std::abs(lines[1].start - 3.9) < 1e-9);
    }
    void transforms() {
        QList<std::complex<double>> values{{1, 0}, {0, 0}, {0, 0}, {0, 0}};
        auto bins = sf::fft(values);
        for (auto bin : bins)
            QVERIFY(std::abs(bin - std::complex<double>(1, 0)) < 1e-10);
    }
    void icons() {
        for (auto name : {"fade-in", "fade-out", "crossfade", "select", "split", "delete"}) {
            QVERIFY(!sf::icon(name).isNull());
            auto picture = sf::icon(name).pixmap(128, 128).toImage();
            QVERIFY(!picture.isNull());
            QCOMPARE(picture.size(), QSize(128, 128));
        }
    }
    void tagRoundTrip() {
        QTemporaryDir directory;
        QString file = directory.filePath("Песня.mp3");
        QByteArray payload("\xff\xfb\x90\x64", 4);
        payload += QByteArray(8192, 'x');
        QFile original(file);
        QVERIFY(original.open(QIODevice::WriteOnly));
        original.write(payload);
        original.close();
        sf::writeMetadata(
            file,
            {{"title", "Название"}, {"artist", "Исполнитель"}, {"lyrics", "[00:01.20]Строка"}},
            false, false);
        auto tags = sf::readMetadata(file);
        QCOMPARE(tags.values["title"], QString("Название"));
        QCOMPARE(tags.values["lyrics"], QString("[00:01.20]Строка"));
        sf::writeMetadata(file, {{"title", "Правка"}}, true, true);
        tags = sf::readMetadata(file);
        QCOMPARE(tags.values["title"], QString("Правка"));
        QCOMPARE(tags.values["lyrics"], QString("[00:01.20]Строка"));
        QFile result(file);
        QVERIFY(result.open(QIODevice::ReadOnly));
        QVERIFY(result.readAll().endsWith(payload));
    }
    void actualRenderFadesAndOriginals() {
        QTemporaryDir directory;
        auto path = tone(directory, "Оригинал");
        QFile original(path);
        QVERIFY(original.open(QIODevice::ReadOnly));
        QByteArray before = original.readAll();
        original.close();
        sf::Project project;
        auto id = project.add(sf::readSource(path));
        QVERIFY(project.sources[path].peaks.size() <= 2401);
        project.get(id).fadeIn = 1;
        project.get(id).fadeOut = 1;
        QString output = sf::render(project, directory.filePath("mix.wav"));
        QVERIFY(rms(sf::decode(output, 8000, 1, .05, .1)) <
                rms(sf::decode(output, 8000, 1, 2, .1)) * .25);
        QVERIFY(rms(sf::decode(output, 8000, 1, 5.8, .1)) <
                rms(sf::decode(output, 8000, 1, 2, .1)) * .25);
        QVERIFY(original.open(QIODevice::ReadOnly));
        QCOMPARE(original.readAll(), before);
        QVERIFY_EXCEPTION_THROWN(sf::render(project, path), sf::Error);
    }
    void containerMetadataAndCovers() {
        QTemporaryDir directory;
        QString input = tone(directory, "source", 2);
        QImage image(64, 64, QImage::Format_RGB32);
        image.fill(QColor("#6550b9"));
        QByteArray cover;
        QBuffer buffer(&cover);
        QVERIFY(buffer.open(QIODevice::WriteOnly));
        QVERIFY(image.save(&buffer, "PNG"));
        for (auto extension : {"flac", "m4a", "ogg", "opus"}) {
            QString file = directory.filePath("song." + QString(extension));
            sf::ffmpeg({"-i", input, "-ac", "2", file});
            auto before = sf::decode(file, 8000, 1);
            sf::writeMetadata(
                file, {{"title", "Новая песня"}, {"artist", "Исполнитель"}, {"lyrics", "Строка"}},
                false, false, cover, true);
            auto tags = sf::readMetadata(file);
            QCOMPARE(tags.values["title"], QString("Новая песня"));
            QCOMPARE(tags.values["lyrics"], QString("Строка"));
            QVERIFY2(!tags.cover.isEmpty(), extension);
            QCOMPARE(sf::decode(file, 8000, 1), before);
        }
    }
    void lyricOutputFormat() {
        QTemporaryDir directory;
        QString wav = tone(directory, "source", 2);
        QString mp3 = directory.filePath("song.mp3");
        sf::ffmpeg({"-i", wav, mp3});
        sf::saveLyrics(mp3, "[00:00.10]Строка", "lrc");
        QVERIFY(QFile::exists(directory.filePath("song.lrc")));
        QVERIFY(sf::readMetadata(mp3).values.value("lyrics").isEmpty());
        sf::saveLyrics(mp3, "[00:00.20]В песне", "embedded");
        QCOMPARE(sf::readMetadata(mp3).values["lyrics"], QString("[00:00.20]В песне"));
    }
    void actualCrossfadeAndCut() {
        QTemporaryDir directory;
        sf::Project project;
        auto first = project.add(sf::readSource(tone(directory, "first", 6, 220)));
        auto next = project.add(sf::readSource(tone(directory, "next", 6, 330)));
        project.get(next).gain = -12;
        auto joined = sf::crossfade(project, project.get(first), project.get(next));
        QVERIFY(std::abs(joined.duration - 10) < .005);
        QCOMPARE(project.clips.size(), 2);
        double a = rms(sf::decode(joined.path, 8000, 1, 4.2, .1));
        double b = rms(sf::decode(joined.path, 8000, 1, 5.6, .1));
        QVERIFY(std::abs(a / b - 1) < .16);
        auto cut = sf::cutAudio(project, project.get(first), 2, 3);
        QVERIFY(std::abs(cut.duration - 4.96) < .005);
        QCOMPARE(project.get(first).duration(), 6.);
        QFile::remove(joined.path);
        QFile::remove(cut.path);
    }
    void normalizeLoudnessAndCancel() {
        QTemporaryDir directory;
        QString input = tone(directory, "quiet", 8, 440, .03);
        sf::AudioOptions options;
        options.lufs = -18;
        options.autoDenoise = false;
        QString output = sf::normalize(input, directory.filePath("loud.wav"), options);
        auto result = sf::analyze(output);
        QVERIFY(std::abs(result["integratedLufs"].toString().toDouble() + 18) < .6);
        QVERIFY(result["truePeak"].toString().toDouble() < -1.3);
        auto cancel = std::make_shared<std::atomic_bool>(true);
        sf::Project project;
        project.add(sf::readSource(input));
        QString canceled = directory.filePath("cancel.wav");
        QVERIFY_EXCEPTION_THROWN(sf::render(project, canceled, cancel), sf::Error);
        QVERIFY(!QFile::exists(canceled));
    }
    void artworkIsDeterministicAndDistinct() {
        QTemporaryDir directory;
        auto input = tone(directory, "Музыка", 4);
        sf::CoverOptions options;
        options.size = 384;
        sf::Metadata tags;
        tags.values = {{"title", "Ночная музыка"}, {"artist", "SonicForge"}};
        QList<QByteArray> hashes;
        for (int pattern = 0; pattern < 3; ++pattern) {
            options.pattern = pattern;
            auto image = sf::makeCover(input, tags, options);
            QCOMPARE(image.size(), QSize(384, 384));
            auto second = sf::makeCover(input, tags, options);
            QCOMPARE(image, second);
            hashes << QCryptographicHash::hash(
                QByteArray(reinterpret_cast<const char*>(image.constBits()), image.sizeInBytes()),
                QCryptographicHash::Sha256);
            QDir().mkpath("validation/native-artwork");
            QVERIFY(
                image.save("validation/native-artwork/cover-" + QString::number(pattern) + ".png"));
        }
        QVERIFY(hashes[0] != hashes[1]);
        QVERIFY(hashes[1] != hashes[2]);
    }
    void soundSpellingPreservesForeignSound() {
        QCOMPARE(sf::soundSpelling("გამარჯობა", "ru", "ka"), QString("гамарджоба"));
        QCOMPARE(sf::soundSpelling("Schön", "en", "de"), QString("Schon"));
        QVERIFY(sf::soundSpelling("llama", "ru", "es").startsWith("й"));
    }
    void fragmentVolumeSpeedEqAndZero() {
        QTemporaryDir directory;
        sf::Project project;
        auto id = project.add(sf::readSource(tone(directory, "speed")));
        auto& clip = project.get(id);
        clip.speed = 2;
        clip.volume = .5;
        clip.bass = 3;
        QCOMPARE(clip.duration(), 3.);
        auto path = sf::render(project, directory.filePath("fast.wav"));
        QVERIFY(std::abs(sf::readSource(path).duration - 3) < .02);
        auto right = project.split(id, 1);
        QCOMPARE(project.get(right).start, 2.);
        project.validate();
        auto silent = project.get(right);
        silent.position = 0;
        silent.speed = 0;
        project.clips = {silent};
        path = sf::render(project, directory.filePath("silent.wav"));
        QVERIFY(rms(sf::decode(path, 8000, 1)) < 1e-5);
        project.clips[0].speed = .01;
        project.clips[0].volume = 4;
        project.validate();
    }
    void symbolCanBeRemoved() {
        QTemporaryDir directory;
        auto input = tone(directory, "symbol", 2);
        sf::CoverOptions options;
        options.size = 192;
        options.title = false;
        auto with = sf::makeCover(input, {}, options);
        options.symbol = false;
        QVERIFY(with != sf::makeCover(input, {}, options));
    }
    void overlappingSpeechKeepsEveryWord() {
        QList<sf::Lyric> words;
        sf::appendSpeechWindow(
            words, {{20.9, 21.5, "first", .9}, {22.4, 23, "second", .9}, {23.5, 24, "third", .9}},
            0, 23);
        sf::appendSpeechWindow(words,
                               {{20.9, 21.5, "first", .9},
                                {22.4, 23, "second", .9},
                                {23.5, 24, "third", .9},
                                {24.1, 25, "last", .9}},
                               23, 43);
        QCOMPARE(words.size(), 4);
        auto lines = sf::speechLines(words);
        QString text;
        for (const auto& line : lines)
            text += line.text + ' ';
        QCOMPARE(text.trimmed(), QString("first second third last"));
    }
    void ctcRespectsIntroAndRepeatedLetters() {
        QVector<float> probabilities(12 * 3, std::log(.001f));
        for (int i = 0; i < 12; ++i)
            probabilities[i * 3] = std::log(.998f);
        for (auto pair : {QPair<int, int>{4, 1}, {6, 1}, {8, 2}}) {
            probabilities[pair.first * 3] = std::log(.001f);
            probabilities[pair.first * 3 + pair.second] = std::log(.998f);
        }
        auto match = sf::ctcViterbi(probabilities, 12, 3, {1, 1, 2});
        QVERIFY(match.has_value());
        QCOMPARE(match->first, QVector<int>({4, 6, 8}));
        QVERIFY(match->confidence > .99);
        QVERIFY(!sf::ctcViterbi(probabilities, 12, 3, {99}));
    }
    void longWaveformStaysCompact() {
        QTemporaryDir directory;
        auto path = directory.filePath("two-hours.flac");
        sf::ffmpeg({"-f", "lavfi", "-i", "sine=frequency=220:duration=7200:sample_rate=8000",
                    "-c:a", "flac", path});
        const auto source = sf::readSource(path);
        QCOMPARE(source.duration, 7200.);
        QVERIFY(source.peaks.size() <= 2401);
        QVERIFY(source.peaks.size() >= 2300);
    }
    void closingTerminatesOwnedProcesses() {
        QProcess child;
        child.start(sf::executable("ffmpeg"), {"-v", "error", "-re", "-f", "lavfi", "-i",
                                               "sine=duration=120", "-f", "null", "-"});
        QVERIFY(child.waitForStarted());
        sf::adoptChild(child);
        sf::shutdownWorkers();
        QVERIFY(child.waitForFinished(3000));
        QCOMPARE(child.state(), QProcess::NotRunning);
    }
};
QTEST_MAIN(CoreTests)
#include "tests.moc"
