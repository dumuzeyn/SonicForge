#include "core.h"
#include "genre.h"
#include "speech.h"
#include "cover_symbols.h"
#include <QtTest>
#include <cmath>
#include "windows_cover_test.h"
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
    void genreAlwaysChoosesHighestSupportedScore() {
        const QJsonArray labels{"female", "rock", "pop", "rnb", "hip-hop"};
        auto ranked = sf::rankedGenres(labels, {.99, .03, .04, .02, .01});
        QCOMPARE(ranked.first().name, QString("Pop"));
        QCOMPARE(ranked.first().score, .04);
        ranked = sf::rankedGenres(labels, {.99, .8, .9, .95, .85});
        QCOMPARE(ranked.first().name, QString("R&B"));
        ranked = sf::rankedGenres(labels, {0, 0, 0, 0, 0});
        QCOMPARE(ranked.first().name, QString("Rock"));
        ranked = sf::rankedGenres(labels, {0, .8, .8, .1, .1});
        QCOMPARE(ranked.first().name, QString("Rock"));
    }
    void singleSongEditsKeepTheirName() {
        QTemporaryDir directory;
        auto song = tone(directory, "Ночная песня", 2);
        sf::writeMetadata(song, {{"title", "Другое название"}, {"artist", "Исполнитель"}});
        sf::Project project;
        const auto id = project.add(sf::readSource(song));
        project.split(id, 1);
        QCOMPARE(project.songSource(), song);
        QCOMPARE(project.outputBaseName(), QString("Ночная песня"));
        const auto result = sf::render(project, directory.filePath(project.outputBaseName() + ".mp3"));
        const auto tags = sf::readMetadata(result);
        QCOMPARE(tags.values.value("title"), QString("Ночная песня"));
        QCOMPARE(tags.values.value("artist"), QString("Исполнитель"));
        auto other = tone(directory, "Другая песня", 1);
        const auto otherId = project.add(sf::readSource(other), 1, 0);
        QVERIFY(project.songSource().isEmpty());
        QCOMPARE(project.outputBaseName(), QString("SonicForge-mix"));
        project.muted.insert(1);
        QCOMPARE(project.songSource(), song);
        project.muted.clear();
        project.get(otherId).originalSource = song;
        QCOMPARE(project.songSource(), song);
        // The batched render path must carry the song identity as well.
        for (int i = 0; i < 7; ++i) project.add(project.sources.value(song), 0);
        const auto batched = sf::render(project, directory.filePath("batched.mp3"));
        QCOMPARE(sf::readMetadata(batched).values.value("title"), QString("Ночная песня"));
    }
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
    void windowsMp3Cover() {
        QTemporaryDir directory;
        QString file = directory.filePath("Обложка.mp3");
        sf::ffmpeg({"-i", tone(directory, "source", 1), file});
        auto before = sf::decode(file, 8000, 1);
        QImage image(128, 128, QImage::Format_RGB32);
        image.fill(QColor("#6550b9"));
        QByteArray picture;
        QBuffer buffer(&picture);
        QVERIFY(buffer.open(QIODevice::WriteOnly));
        QVERIFY(image.save(&buffer, "JPEG"));
        sf::writeMetadata(file, {{"title", "Лисица"}, {"lyrics", "[00:00.10]Строка"}},
                          false, false, picture, true);
        auto metadata = sf::readMetadata(file);
        QCOMPARE(metadata.cover, picture);
        QCOMPARE(metadata.values["title"], QString("Лисица"));
        QCOMPARE(metadata.values["lyrics"], QString("[00:00.10]Строка"));
        QFile bytes(file);
        QVERIFY(bytes.open(QIODevice::ReadOnly));
        QByteArray data = bytes.readAll();
        bytes.close();
        int apic = data.indexOf("APIC");
        QVERIFY(apic >= 0);
        QCOMPARE(data[apic + 10], char(0));
#ifdef Q_OS_WIN
        QVERIFY(windowsReadsCover(file));
#endif
        // Simulate a file produced by older builds, then save lyrics only.
        data[apic + 10] = 3;
        QVERIFY(bytes.open(QIODevice::WriteOnly));
        QCOMPARE(bytes.write(data), data.size());
        bytes.close();
        sf::saveLyrics(file, "[00:00.20]Новая строка", "embedded");
        QCOMPARE(sf::readMetadata(file).cover, picture);
        QVERIFY(bytes.open(QIODevice::ReadOnly));
        data = bytes.readAll();
        bytes.close();
        QCOMPARE(data[data.indexOf("APIC") + 10], char(0));
        QCOMPARE(sf::decode(file, 8000, 1), before);
#ifdef Q_OS_WIN
        QString fresh = directory.filePath("После исправления.mp3");
        QVERIFY(QFile::copy(file, fresh));
        QVERIFY(windowsReadsCover(fresh));
#endif
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
    void coverColorFollowsLocalRhythm() {
        QTemporaryDir directory;
        constexpr int rate=11025;
        QVector<float> audio(rate*40);
        for (int i=0;i<audio.size();++i) {
            double t=double(i)/rate;
            if (t>=36) continue;
            if (t>=24 && t<28) { audio[i]=.3*std::sin(2*3.141592653589793*220*t); continue; }
            double bpm=(t>=8 && t<16)||(t>=28 && t<36) ? 180 : 60;
            double local=std::fmod(t,60/bpm);
            double pulse=local<.12 ? std::exp(-local*45)*std::sin(2*3.141592653589793*130*local) : 0;
            double amplitude=t>=28 ? .08 : .4;
            // Alternating strong/weak beats encourage a half-time detector error.
            if (bpm==180 && int(t*bpm/60)%2) amplitude*=.65;
            audio[i]=amplitude*pulse;
        }
        QString file=directory.filePath("slow-fast-slow-sustain-quiet-fast-silence.wav");
        sf::writeWav(file,audio,rate,1);
        const auto report=sf::analyzeCoverRhythm(file);
        QDir().mkpath("validation/native-artwork");
        QFile diagnostic("validation/native-artwork/rhythm-fixture.json");
        if (diagnostic.open(QIODevice::WriteOnly)) diagnostic.write(QJsonDocument(report).toJson());
        const auto timeline=report["timeline"].toArray();
        auto pace=[&](double second) { return timeline[qRound(second/40*(timeline.size()-1))].toObject()["pace"].toDouble(); };
        QVERIFY2(pace(4)<.45,qPrintable(QString::number(pace(4))));
        QVERIFY2(pace(12)>.72,qPrintable(QString::number(pace(12))));
        QVERIFY2(pace(20)<.45,qPrintable(QString::number(pace(20))));
        QVERIFY2(pace(26)<.15,qPrintable(QString::number(pace(26))));
        QVERIFY2(pace(32)>.72,qPrintable(QString::number(pace(32))));
        QVERIFY(pace(38)<.05);
        sf::CoverOptions options;
        options.size=384;options.colorSource=2;options.title=options.symbol=false;
        QImage explicitRhythm;
        for (int pattern=0;pattern<3;++pattern) {
            options.pattern=pattern;
            auto image=sf::makeCover(file,{},options);
            if (pattern==2) explicitRhythm=image;
            auto warmth=[&](double second) {
                const int x=qRound(second/40*(image.width()-1));
                double result=0;
                for (int y=0;y<image.height();++y) result+=qRed(image.pixel(x,y))-qBlue(image.pixel(x,y));
                return result/image.height();
            };
            QVERIFY(warmth(4)<-15);
            QVERIFY(warmth(12)>25);
            QVERIFY(warmth(20)<-15);
            QVERIFY(warmth(32)>25);
            QDir().mkpath("validation/native-artwork");
            QVERIFY(image.save("validation/native-artwork/rhythm-history-"+QString::number(pattern)+".png"));
            for (double second : {4.,12.,20.,32.}) {
                int x=qRound(second/40*(image.width()-1));
                auto top=image.pixelColor(x,20),bottom=image.pixelColor(x,image.height()-21);
                const bool fast=second==12||second==32;
                QVERIFY(fast ? top.red()>top.blue() && bottom.red()>bottom.blue()
                             : top.blue()>top.red() && bottom.blue()>bottom.red());
            }
        }
        options.pattern=2;options.colorSource=4;
        QCOMPARE(sf::makeCover(file,{},options),explicitRhythm);
        auto cancel=std::make_shared<std::atomic_bool>(true);
        QVERIFY_EXCEPTION_THROWN(sf::analyzeCoverRhythm(file,cancel),sf::Error);
        QRandomGenerator noise(42);
        QVector<float> hiss(rate*8);
        for (auto& sample:hiss) sample=float(noise.generateDouble()-.5)*.4;
        QString noiseFile=directory.filePath("stationary-noise.wav");
        sf::writeWav(noiseFile,hiss,rate,1);
        const auto noiseTimeline=sf::analyzeCoverRhythm(noiseFile)["timeline"].toArray();
        double noisePace=0;
        for (const auto& point:noiseTimeline) noisePace+=point.toObject()["pace"].toDouble();
        QVERIFY(noisePace/noiseTimeline.size()<.1);
    }
    void coverPaletteIncludesMediumRhythmAndKeepsSteadySections() {
        QTemporaryDir directory;
        constexpr int rate = 11025;
        QVector<float> audio(rate * 24);
        for (int i = 0; i < audio.size(); ++i) {
            const double t = double(i) / rate;
            const double bpm = t < 8 ? 72 : t < 16 ? 112 : 152;
            const double local = std::fmod(t - (t < 8 ? 0 : t < 16 ? 8 : 16), 60 / bpm);
            audio[i] = local < .12 ? .4 * std::exp(-local * 45) * std::sin(2 * 3.141592653589793 * 130 * local) : 0;
        }
        const auto file = directory.filePath("slow-medium-faster.wav");
        sf::writeWav(file, audio, rate, 1);
        sf::CoverOptions options;
        options.size = 192; options.colorSource = 2; options.title = options.symbol = false;
        for (int pattern = 0; pattern < 3; ++pattern) {
            options.pattern = pattern;
            const auto image = sf::makeCover(file, {}, options);
            auto section = [&](double second) {
                const int x = qRound(second / 24 * (image.width() - 1));
                double r = 0, g = 0, b = 0;
                for (int y = 0; y < image.height(); ++y) {
                    const auto color = image.pixelColor(x, y);
                    r += color.red(); g += color.green(); b += color.blue();
                }
                return QColor(qRound(r / image.height()), qRound(g / image.height()), qRound(b / image.height()));
            };
            const auto slow = section(4), medium = section(12), fast = section(20);
            QVERIFY(slow.blue() > slow.red() + 20 && slow.blue() > slow.green());
            QVERIFY(medium.green() > medium.red() + 20 && medium.blue() > medium.red() + 20);
            QVERIFY(fast.red() > fast.blue() + 20 && fast.red() > fast.green() + 20);
            QVERIFY(image.save("validation/native-artwork/slow-medium-faster-" + QString::number(pattern) + ".png"));
        }
    }
    void tempoTracksAccentsInsteadOfLegatoSubdivisions() {
        QTemporaryDir directory;
        constexpr int rate=11025;
        constexpr double bpm=66, beat=60/bpm, note=beat/2;
        QVector<float> samples(rate*18);
        for (int i=0;i<samples.size();++i) {
            const double t=double(i)/rate;
            double value=.025*std::sin(2*3.141592653589793*196*t);
            const int latest=int(t/note);
            for (int event=qMax(0,latest-8);event<=latest;++event) {
                const double age=t-event*note;
                const bool accented=event%2==0;
                const double frequency=accented ? 523.25 : 659.25;
                value+=(accented ? .24 : .09)*std::exp(-age*2.8)*(1-std::exp(-age*90))*
                       (std::sin(2*3.141592653589793*frequency*age)+.2*std::sin(4*3.141592653589793*frequency*age));
            }
            samples[i]=value;
        }
        for (const double gain : {1.,.2}) {
            auto audio=samples;
            for (auto& value:audio) value*=gain;
            const auto file=directory.filePath(QString("legato-%1.wav").arg(gain));
            sf::writeWav(file,audio,rate,1);
            const auto timeline=sf::analyzeCoverRhythm(file)["timeline"].toArray();
            for (double second : {5.,9.,13.}) {
                const auto point=timeline[qRound(second/18*(timeline.size()-1))].toObject();
                QVERIFY2(std::abs(point["pulse_bpm"].toDouble()-bpm)<5,
                         qPrintable(QJsonDocument(point).toJson(QJsonDocument::Compact)));
                QVERIFY(point["pace"].toDouble()<.45);
            }
        }
    }
    void tempoKeepsFastPercussionOverSustainedMusic() {
        QTemporaryDir directory;
        constexpr int rate=11025;
        QVector<float> samples(rate*12);
        for (int i=0;i<samples.size();++i) {
            const double t=double(i)/rate,local=std::fmod(t,1./3);
            // A sustained chord masks the drum's gaps in the overall RMS.
            const double pad=.10*std::sin(2*3.141592653589793*440*t)+.07*std::sin(2*3.141592653589793*659.25*t);
            const double kick=local<.12 ? .4*std::exp(-local*45)*std::sin(2*3.141592653589793*130*local) : 0;
            samples[i]=pad+kick;
        }
        const auto file=directory.filePath("fast-drums-and-chord.wav");
        sf::writeWav(file,samples,rate,1);
        const auto timeline=sf::analyzeCoverRhythm(file)["timeline"].toArray();
        for (double second : {4.,6.,8.}) {
            const auto point=timeline[qRound(second/12*(timeline.size()-1))].toObject();
            QVERIFY2(std::abs(point["pulse_bpm"].toDouble()-180)<8,
                     qPrintable(QJsonDocument(point).toJson(QJsonDocument::Compact)));
            QVERIFY(point["pace"].toDouble()>.72);
        }
    }
    void artworkIsDeterministicAndDistinct() {
        QTemporaryDir directory;
        QString sample = qEnvironmentVariable("SONICFORGE_COVER_SAMPLE");
        auto input = sample.isEmpty() ? tone(directory, "Музыка", 4) : sample;
        sf::CoverOptions options;
        options.size = sample.isEmpty() ? 384 : 1000;
        sf::Metadata tags;
        tags.values = {{"title", "Ночная музыка"}, {"artist", "SonicForge"}};
        if (!sample.isEmpty())
            tags = sf::coverMetadata(input, sf::readMetadata(input));
        QList<QByteArray> hashes;
        for (int pattern = 0; pattern < 3; ++pattern) {
            options.pattern = pattern;
            auto image = sf::makeCover(input, tags, options);
            QCOMPARE(image.size(), QSize(options.size, options.size));
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
    void audioHighlightsCompareActualOutput() {
        QTemporaryDir directory;
        constexpr int rate = 8000;
        QVector<float> original(rate * 4), modified;
        for (int i = 0; i < rate * 2; ++i) {
            float sample = .15 * std::sin(2 * 3.141592653589793 * 220 * i / rate);
            original[i * 2] = sample;
            original[i * 2 + 1] = -sample; // Stereo differences must not cancel in a mono mix.
        }
        modified = original;
        for (int i = rate / 2; i < rate; ++i)
            for (int channel = 0; channel < 2; ++channel)
                modified[i * 2 + channel] *= .5;
        QString input = directory.filePath("original.wav"), output = directory.filePath("modified.wav");
        sf::writeWav(input, original, rate, 2);
        sf::writeWav(output, original, rate, 2);
        QVERIFY(sf::audioChanges(input, output).isEmpty());
        sf::writeWav(output, modified, rate, 2);
        auto changes = sf::audioChanges(input, output);
        QCOMPARE(changes.size(), 1);
        QVERIFY(changes[0].first >= .44 && changes[0].first <= .51);
        QVERIFY(changes[0].second >= .99 && changes[0].second <= 1.06);
        // A shorter output uses its own time axis, without marks for the discarded end.
        sf::writeWav(output, modified.mid(0, rate * 2), rate, 2);
        changes = sf::audioChanges(input, output);
        QVERIFY(!changes.isEmpty());
        QVERIFY(changes.last().second <= 1.001);
        // Extra processed audio, such as a reverb tail, remains part of the comparison.
        modified = original;
        modified += original.mid(0, rate * 2);
        sf::writeWav(output, modified, rate, 2);
        changes = sf::audioChanges(input, output);
        QCOMPARE(changes.size(), 1);
        QVERIFY(changes.first().first >= 1.94 && changes.first().first <= 2.01);
        QVERIFY(changes.last().second >= 2.99 && changes.last().second <= 3.01);
        auto cancel = std::make_shared<std::atomic_bool>(true);
        QVERIFY_EXCEPTION_THROWN(sf::audioChanges(input, output, cancel), sf::Error);
    }
    void artworkUsesSongNamesAndAllSymbols() {
        QCOMPARE(sf::coverMetadata("C:/music/Ночная песня.wav", {}).values.value("title"),
                 QString("Ночная песня"));
        sf::Metadata tags;
        tags.values["title"] = "Настоящее название";
        QCOMPARE(sf::coverMetadata("12345.wav", tags).values["title"], tags.values["title"]);
        auto names = sf::coverSymbolNames();
        QCOMPARE(names.size(), 66);
        QSet<QString> automatic;
        for (quint32 variation = 0; variation < quint32(names.size()); ++variation)
            automatic.insert(sf::coverSymbolFamily("Безымянная песня", .3, .4, .2, variation));
        QCOMPARE(automatic.size(), names.size());
        QCOMPARE(sf::coverSymbolFamily("Солнце", .3, .4, .2, 42), QString("sun"));
        QCOMPARE(sf::coverSymbolFamily("Горы", .3, .4, .2, 42), QString("mountain"));
        QCOMPARE(sf::coverSymbolFamily("Птица", .3, .4, .2, 42), QString("bird"));
        QCOMPARE(sf::coverSymbolFamily("Охота на лисицу", .3, .4, .2, 42), QString("fox"));
        QCOMPARE(sf::coverSymbolFamily("Волк", .3, .4, .2, 42), QString("wolf"));
        QSet<QByteArray> shapes;
        QImage gallery(1200, ((names.size() + 9) / 10) * 120, QImage::Format_RGB32);
        gallery.fill(QColor("#302544"));
        QPainter painter(&gallery);
        painter.setRenderHint(QPainter::Antialiasing);
        int i = 0;
        for (const auto& name : names) {
            QCOMPARE(sf::coverSymbolFamily(name, .5, .3, .2), name);
            auto path = sf::coverSymbolPath(name, .5);
            QVERIFY2(!path.isEmpty(), qPrintable(name));
            QImage tile(100,100,QImage::Format_RGB32);
            tile.fill(Qt::black);
            QPainter p(&tile); p.scale(100,100); p.fillPath(path,Qt::white); p.end();
            shapes.insert(QCryptographicHash::hash(QByteArray(reinterpret_cast<const char*>(tile.constBits()),tile.sizeInBytes()),QCryptographicHash::Sha256));
            painter.save(); painter.translate((i%10)*120+10,(i/10)*120+2); painter.scale(100,100);
            painter.fillPath(path,QColor("#f7ddbb")); painter.restore();
            painter.setPen(Qt::white); painter.drawText(QRect((i%10)*120,(i/10)*120+102,120,18),Qt::AlignCenter,name);
            ++i;
        }
        painter.end();
        QDir().mkpath("validation/native-artwork");
        QVERIFY(gallery.save("validation/native-artwork/symbol-catalog.png"));
        QCOMPARE(shapes.size(), names.size());
        QVERIFY(sf::coverSymbolFamily("Мечта", .2, .3, .2) != "sword");
        QVERIFY(sf::coverSymbolFamily("Sunday", .2, .3, .2) != "sun");
        QCOMPARE(sf::coverSymbolFamily("Сердце", .2, .3, .2), QString("heart"));
    }
    void artworkPatternsChangeGeometryWithOnePalette() {
        QTemporaryDir directory;
        auto input = tone(directory,"patterns",2);
        sf::CoverOptions options;
        options.size=192; options.title=false; options.symbol=false;
        options.colorSource=3;
        options.palette={Qt::black,Qt::white}; options.stops={0,1};
        QList<QImage> images;
        for(int pattern=0;pattern<3;++pattern) {
            options.pattern=pattern;
            images << sf::makeCover(input,{},options);
        }
        for(int a=0;a<3;++a) for(int b=a+1;b<3;++b) {
            double difference=0;
            for(int y=0;y<192;++y) for(int x=0;x<192;++x)
                difference+=std::abs(qGray(images[a].pixel(x,y))-qGray(images[b].pixel(x,y)));
            QVERIFY2(difference/(192*192)>12,"Patterns must visibly change the large-scale geometry");
        }
        options.palette={QColor("#ff0000"),QColor("#ff0000")};
        auto red=sf::makeCover(input,{},options);
        options.palette={QColor("#0000ff"),QColor("#0000ff")};
        auto blue=sf::makeCover(input,{},options);
        QVERIFY(red.pixelColor(96,96).red()>red.pixelColor(96,96).blue()+40);
        QVERIFY(blue.pixelColor(96,96).blue()>blue.pixelColor(96,96).red()+40);
    }
    void artworkInkFollowsBackgroundPalette() {
        for (auto base : {QColor("#127d86"), QColor("#ab531b"), QColor("#8841a1")}) {
            QImage image(128, 128, QImage::Format_RGB32);
            image.fill(base);
            auto colors = sf::coverColors(image);
            QVERIFY(std::abs(colors.symbol.hslHueF() - base.hslHueF()) < .03);
            QVERIFY(std::abs(colors.title.hslHueF() - colors.symbol.hslHueF()) < .03);
            QVERIFY(colors.title.lightnessF() > .8);
            QCOMPARE(colors.title, colors.symbol);
            QCOMPARE(colors.artist, colors.symbol);
            QVERIFY(colors.symbol.lightnessF() > base.lightnessF() + .15);
        }
        QImage mostlyTeal(128, 128, QImage::Format_RGB32);
        mostlyTeal.fill(QColor("#127d86"));
        mostlyTeal.setPixelColor(64, 45, QColor("#8811bb"));
        auto colors = sf::coverColors(mostlyTeal);
        QVERIFY(std::abs(colors.symbol.hslHueF() - QColor("#127d86").hslHueF()) < .03);
        QImage gray(128, 128, QImage::Format_RGB32);
        gray.fill(QColor("#999999"));
        colors = sf::coverColors(gray);
        QCOMPARE(colors.symbol.hslSaturation(), 0);
        QCOMPARE(colors.title.hslSaturation(), 0);
        QVERIFY(colors.symbol.lightnessF() < .4);
    }
    void coverTextCanBeEditedAndSharesSymbolColor() {
        sf::CoverOptions options;
        options.size = 512;
        options.text = "Своя надпись\nВторая строка";
        options.fontFamily = "Noto Serif";
        options.textSize = 5;
        options.textX = 35;
        options.textY = 80;
        options.ink = QColor("#a9e5d3");
        sf::Metadata metadata;
        metadata.values = {{"title", "Солнце"}, {"artist", "Исполнитель"}};
        QImage background(512, 512, QImage::Format_RGB32);
        background.fill(QColor("#163b45"));
        auto artwork = sf::coverArtworkFromImage(background, metadata, options);
        auto layout = sf::layoutCoverText(metadata, options);
        QCOMPARE(layout.title, options.text);
        QCOMPARE(layout.titleFont.family(), options.fontFamily);
        QCOMPARE(layout.titleFont.pixelSize(), 26);
        QVERIFY(std::abs(layout.bounds.center().x() / 512 * 100 - 35) < 1);
        QVERIFY(std::abs(layout.bounds.center().y() / 512 * 100 - 80) < 1);
        auto image = sf::decorateCover(artwork, options);
        int textPixels = 0, symbolPixels = 0;
        for (int y = 0; y < 512; ++y) for (int x = 0; x < 512; ++x)
            if (image.pixelColor(x, y) == options.ink) {
                if (layout.bounds.contains(QPointF(x, y))) ++textPixels;
                else ++symbolPixels;
            }
        QVERIFY(textPixels > 100);
        QVERIFY(symbolPixels > 100);
        options.textX = 70;
        options.textY = 20;
        options.textSize = 9;
        options.fontFamily = "Noto Sans";
        auto moved = sf::layoutCoverText(metadata, options);
        QVERIFY(moved.bounds.top() < layout.bounds.top());
        QVERIFY(moved.titleFont.pixelSize() > layout.titleFont.pixelSize());
        QVERIFY(sf::decorateCover(artwork, options) != image);
        options.text.clear();
        QCOMPARE(sf::layoutCoverText(metadata, options).title, metadata.values["title"]);
        options.title = options.artist = options.symbol = false;
        QCOMPARE(sf::decorateCover(artwork, options), background);
        options.title = true;
        options.artist = true;
        options.text = "Перенос текста";
        options.textX = options.textY = 100;
        auto edge = sf::layoutCoverText(metadata, options);
        QVERIFY(edge.bounds.right() <= 512.01 && edge.bounds.bottom() <= 512.01);
    }
    void referenceEnginesKeepTheirTextureFamilies() {
        QTemporaryDir directory;
        auto input = tone(directory, "reference", 4);
        sf::CoverOptions options;
        options.size = 384;
        options.colorSource = 4;
        options.title = options.symbol = false;
        QList<QImage> images;
        QList<double> edges;
        QImage gallery(384*3, 416, QImage::Format_RGB32);
        gallery.fill(QColor("#f4f4fa"));
        QPainter painter(&gallery);
        painter.setPen(QColor("#302b45"));
        for (int pattern = 0; pattern < 3; ++pattern) {
            options.pattern = pattern;
            auto image = sf::makeCover(input, {}, options);
            images << image;
            double edge = 0;
            for (int y = 1; y < 384; ++y) for (int x = 1; x < 384; ++x)
                edge += std::abs(qGray(image.pixel(x,y))-qGray(image.pixel(x-1,y))) +
                        std::abs(qGray(image.pixel(x,y))-qGray(image.pixel(x,y-1)));
            edges << edge / (383*383*2);
            painter.drawText(QRect(pattern*384+8, 0, 376, 32),Qt::AlignVCenter,"M2Pv"+QString::number(pattern+1));
            painter.drawImage(QPoint(pattern*384,32),image);
        }
        painter.end();
        QDir().mkpath("validation/native-artwork");
        QVERIFY(gallery.save("validation/native-artwork/reference-engines.png"));
        QVERIFY2(edges[0] > edges[1] * 1.3, "Classic spectral contours must be finer than the broad organic folds");
        QVERIFY(images[0] != images[1] && images[1] != images[2]);
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
    void suppliedLyricsUseDirectAlignmentAndKeepLongSequences() {
        QCOMPARE(sf::directAlignmentLanguage("[00:12.00]Дале-далеко\nВторая строка"), QString("ru"));
        QCOMPARE(sf::directAlignmentLanguage("The morning sun\nis shining"), QString("en"));
        QVERIFY(sf::directAlignmentLanguage("Русский mixed text").isEmpty());
        constexpr int count = 900, frames = count * 2 + 10;
        QVector<float> probabilities(frames * 3, std::log(.001f));
        QVector<int> tokens;
        for (int frame = 0; frame < frames; ++frame) probabilities[frame * 3] = std::log(.998f);
        for (int i = 0; i < count; ++i) {
            int token = 1 + i % 2, frame = 5 + i * 2;
            tokens << token;
            probabilities[frame * 3] = std::log(.001f);
            probabilities[frame * 3 + token] = std::log(.998f);
        }
        const auto match = sf::ctcViterbi(probabilities, frames, 3, tokens);
        QVERIFY(match.has_value());
        QCOMPARE(match->first.first(), 5);
        QCOMPARE(match->last.last(), 5 + (count-1) * 2);
        QVERIFY(match->confidence > .99);
        // Long alignments now use disk checkpoints and a bounded backtracking block.
        QVERIFY(sf::ctcViterbi(QVector<float>(120000 * 3), 120000, 3, tokens).has_value());
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
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv); CoreTests tests;
    try { return QTest::qExec(&tests, argc, argv); }
    catch (const std::exception& error) { qCritical().noquote() << error.what(); return 1; }
}
#include "tests.moc"
