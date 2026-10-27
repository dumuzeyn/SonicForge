#include "core.h"
#include "speech.h"
#ifndef _MSC_VER
#ifndef _Return_type_success_
#define _Return_type_success_(X)
#endif
#endif
#include "vendor/onnxruntime_c_api.h"
#include <QLibrary>
#include <QtNetwork>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <model.hpp>
#include <numbers>
#include <numeric>
#include <optional>
#include <thread>
#include <whisper.h>

namespace sf {
static QString modelRoot() {
    QString local = QCoreApplication::applicationDirPath() + "/models";
    if (QDir(local).exists())
        return local;
    QString path =
        QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/models";
    QDir().mkpath(path);
    return path;
}
QString ensureModel(const QString& kind, const Cancel& cancel, Progress progress) {
    QFile manifest(":/models.json");
    if (!manifest.open(QIODevice::ReadOnly))
        throw Error("Не найден манифест моделей");
    auto model = QJsonDocument::fromJson(manifest.readAll()).object()[kind].toObject();
    const QString name = model["file"].toString();
    if (name.isEmpty())
        throw Error("Неизвестная модель");
    const QString userRoot = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/models";
    QString path = modelRoot() + "/" + name;
    if (QFileInfo(userRoot + "/" + name).isFile()) path = userRoot + "/" + name;
    const QByteArray expected = model["sha256"].toString().toLatin1();
    static QMutex verifiedMutex;
    static QHash<QString, QPair<qint64, qint64>> verified;
    QMutexLocker guard(&verifiedMutex);
    if (QFileInfo(path).size() == model["size"].toInteger()) {
        const auto identity = qMakePair(QFileInfo(path).size(), QFileInfo(path).lastModified().toMSecsSinceEpoch());
        if (verified.value(path) == identity) return path;
        if (fileFingerprint(path, cancel).toHex() == expected) {
            verified[path] = identity;
            return path;
        }
        if (progress) progress("Восстанавливаю повреждённую модель…", 0);
    }
    path = userRoot + "/" + name;
    guard.unlock();
    QDir().mkpath(userRoot);
    QLockFile downloadLock(path + ".lock"); downloadLock.setStaleLockTime(0);
    while (!downloadLock.tryLock(100)) checkpoint(cancel);
    if (QFileInfo(path).size() == model["size"].toInteger() && fileFingerprint(path, cancel).toHex() == expected) return path;
    const QUrl url(model["url"].toString());
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile output(path);
    if (!output.open(QIODevice::WriteOnly))
        throw Error(output.errorString());
    QNetworkAccessManager manager;
    manager.setTransferTimeout(60000);
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                         QNetworkRequest::NoLessSafeRedirectPolicy);
    auto* reply = manager.get(request);
    QCryptographicHash hash(QCryptographicHash::Sha256);
    QEventLoop loop;
    QTimer timer;
    QElapsedTimer elapsed; elapsed.start();
    timer.setInterval(100);
    QObject::connect(&timer, &QTimer::timeout, &loop, [&] {
        if ((cancel && cancel->load()) || elapsed.elapsed() > 30 * 60 * 1000)
            reply->abort();
    });
    QObject::connect(reply, &QNetworkReply::readyRead, &loop, [&] {
        auto bytes = reply->readAll();
        hash.addData(bytes);
        if (output.write(bytes) != bytes.size()) reply->abort();
    });
    QObject::connect(reply, &QNetworkReply::downloadProgress, &loop, [&](qint64 got, qint64 total) {
        if (progress)
            progress("Загрузка модели: " + QString::number(got / 1048576) + " МБ",
                     total > 0 ? double(got) / total : -1);
    });
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    timer.start();
    loop.exec();
    auto remaining = reply->readAll();
    hash.addData(remaining);
    output.write(remaining);
    checkpoint(cancel);
    if (reply->error() != QNetworkReply::NoError)
        throw Error("Не удалось загрузить модель: " + reply->errorString());
    if (output.size() != model["size"].toInteger() || hash.result().toHex() != expected)
        throw Error("Загруженная модель не прошла проверку контрольной суммы");
    if (!output.commit())
        throw Error(output.errorString());
    { QMutexLocker lock(&verifiedMutex); verified[path] = qMakePair(QFileInfo(path).size(), QFileInfo(path).lastModified().toMSecsSinceEpoch()); }
    return path;
}
static QList<Lyric> readResult(const QString& file) {
    QFile input(file);
    if (!input.open(QIODevice::ReadOnly))
        throw Error(input.errorString());
    auto object = QJsonDocument::fromJson(input.readAll()).object();
    if (object.contains("error"))
        throw Error(object["error"].toString());
    QList<Lyric> lines;
    for (auto value : object["lines"].toArray()) {
        auto v = value.toObject();
        lines << Lyric{v["start"].toDouble(), v["end"].toDouble(), v["text"].toString(),
                       v["confidence"].toDouble(1)};
    }
    return lines;
}
static QString speechModel(bool fast, const QString& language, const Cancel& cancel,
                           Progress progress) {
    auto model = ensureModel(fast ? "speech_fast" : "speech", cancel, progress);
    if (language != "en")
        ensureModel("alignment_ru", cancel, progress);
    if (language != "ru")
        ensureModel("alignment_en", cancel, progress);
    return model;
}
QList<Lyric> recognize(const QString& audio, const QString& language, const Cancel& cancel,
                       Progress progress, const QString& reference, bool fast) {
    QString model = speechModel(fast, language, cancel, progress), result = uniqueFile(".json");
    auto cleanup = qScopeGuard([&] { QFile::remove(result); });
    QStringList arguments{"--speech-worker", "--audio", audio,      "--model", model,
                          "--language",      language,  "--result", result,    "--reference",
                          reference};
    if (fast)
        arguments << "--fast";
    process(QCoreApplication::applicationFilePath(), arguments, cancel, progress);
    auto lines = readResult(result);
    QFile::remove(result);
    return lines;
}
QList<Lyric> alignLyrics(const QString& audio, const QString& text, const QString& language,
                         const Cancel& cancel, Progress progress, const QString& reference,
                         bool fast) {
    const auto direct = directAlignmentLanguage(text);
    if (progress && !direct.isEmpty()) progress("Проверяю модель выравнивания…", 0);
    QString model = direct.isEmpty() ? speechModel(fast, language, cancel, progress)
                                     : ensureModel("alignment_" + direct, cancel, progress);
    QString result = uniqueFile(".json"),
            input = uniqueFile(".txt");
    QFile file(input);
    if (!file.open(QIODevice::WriteOnly))
        throw Error(file.errorString());
    file.write(text.toUtf8());
    file.close();
    try {
        QStringList arguments{
            "--speech-worker", "--audio",  audio,  "--model", model, "--language",
            language,          "--result", result, "--align", input, "--reference",
            reference};
        if (!direct.isEmpty()) arguments << "--ctc-direct";
        else if (fast)
            arguments << "--fast";
        process(QCoreApplication::applicationFilePath(), arguments, cancel, progress);
        auto lines = readResult(result);
        QFile::remove(result);
        QFile::remove(input);
        return lines;
    } catch (...) {
        QFile::remove(input);
        QFile::remove(result);
        throw;
    }
}
QStringList separate(const QString& audio, bool two, const Cancel& cancel, Progress progress) {
    QString model = ensureModel("stems", cancel, progress);
    QString out = cacheDirectory() + "/stems-" + QUuid::createUuid().toString(QUuid::Id128);
    QDir().mkpath(out);
    bool completed = false;
    auto cleanup = qScopeGuard([&] { if (!completed) QDir(out).removeRecursively(); });
    const auto info = readSource(audio, cancel, false);
    QStorageInfo space(out);
    if (space.isValid() && space.bytesAvailable() < qint64(info.duration * 44100 * 2 * (two ? 20 : 16)) + 128 * 1024 * 1024)
        throw Error("Недостаточно места для разделения звука и результата");
    process(QCoreApplication::applicationFilePath(),
            {"--stems-worker", "--audio", audio, "--model", model, "--out", out}, cancel, progress,
            false);
    QStringList files{out + "/vocals.wav"};
    if (two) {
        QString instrumental = out + "/instrumental.wav";
        ffmpeg({"-i", out + "/drums.wav", "-i", out + "/bass.wav", "-i", out + "/other.wav",
                "-filter_complex", "[0:a][1:a][2:a]amix=inputs=3:normalize=0[out]", "-map", "[out]",
                "-c:a", "pcm_f32le", instrumental},
               cancel);
        files << instrumental;
        for (const auto& stem : {"drums", "bass", "other"}) QFile::remove(out + "/" + stem + ".wav");
    } else
        files << out + "/drums.wav" << out + "/bass.wav" << out + "/other.wav";
    completed = true;
    return files;
}
static QString normalized(const QString& text) {
    QString s = text.toCaseFolded();
    s.remove(QRegularExpression("[^\\p{L}\\p{N}]+"));
    return s;
}
static double similarity(const QString& a, const QString& b) {
    QString x = normalized(a), y = normalized(b);
    if (x.isEmpty() || y.isEmpty())
        return 0;
    QVector<int> previous(y.size() + 1), current(y.size() + 1);
    std::iota(previous.begin(), previous.end(), 0);
    for (int i = 1; i <= x.size(); ++i) {
        current[0] = i;
        for (int j = 1; j <= y.size(); ++j)
            current[j] = qMin(qMin(current[j - 1] + 1, previous[j] + 1),
                              previous[j - 1] + (x[i - 1] == y[j - 1] ? 0 : 1));
        previous.swap(current);
    }
    return 1. - double(previous.last()) / qMax(x.size(), y.size());
}
static QList<Lyric> speechWindow(whisper_context* context, const QVector<float>& audio,
                                 double origin, const QString& language, const QString& prompt = {},
                                 QList<Lyric>* words = nullptr, bool splitSilence = true) {
    if (splitSilence) {
        QList<QPair<int, int>> ranges;
        int first = -1, last = -1;
        for (int offset = 0; offset + 160 <= audio.size(); offset += 160) {
            double power = 0;
            for (int i = 0; i < 160; ++i)
                power += audio[offset + i] * audio[offset + i];
            if (power / 160 <= 1e-10)
                continue;
            if (first >= 0 && offset - last > 32000) {
                ranges << qMakePair(first, last + 160);
                first = -1;
            }
            if (first < 0)
                first = offset;
            last = offset;
        }
        if (first >= 0)
            ranges << qMakePair(first, last + 160);
        if (ranges.isEmpty())
            return {};
        if (ranges.size() <= 4 && (ranges.size() > 1 || ranges.first().first > 8000 ||
                                   ranges.last().second < audio.size() - 8000)) {
            QList<Lyric> result;
            for (auto range : ranges) {
                int left = qMax(0, range.first - 3200),
                    right = qMin(int(audio.size()), range.second + 3200);
                result << speechWindow(context, audio.mid(left, right - left),
                                       origin + left / 16000., language, prompt, words, false);
            }
            return result;
        }
    }
    whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);
    params.n_threads = qBound(1, int(std::thread::hardware_concurrency() / 2), 4);
    params.translate = false;
    params.print_realtime = false;
    params.print_progress = false;
    params.print_timestamps = false;
    params.print_special = false;
    params.token_timestamps = true;
    params.no_context = true;
    params.suppress_blank = true;
    params.suppress_nst = true;
    params.no_speech_thold = .85f;
    params.temperature = 0;
    params.temperature_inc = .2f;
    params.greedy.best_of = 3;
    params.beam_search.beam_size = 3;
    params.max_initial_ts = float(audio.size() / 16000.);
    QVector<float> adjusted = audio;
    double energy = 0, maximum = 0;
    for (float sample : adjusted) {
        energy += sample * sample;
        maximum = qMax(maximum, std::abs(double(sample)));
    }
    const double rms = std::sqrt(energy / qMax(qsizetype(1), adjusted.size()));
    if (rms < .00002)
        return {};
    const double gain = qMin(qBound(.25, .1 / rms, 12.), .98 / qMax(.0001, maximum));
    for (float& sample : adjusted)
        sample = float(sample * gain);
    QByteArray lang = language.toUtf8(), hint = prompt.toUtf8();
    if (language == "other_ru" || language == "other_en" || language == "auto" ||
        language.isEmpty())
        params.language = "auto";
    else
        params.language = lang.constData();
    if (!prompt.isEmpty())
        params.initial_prompt = hint.constData();
    if (whisper_full(context, params, adjusted.constData(), int(adjusted.size())) != 0)
        throw Error("Распознавание не завершено");
    QList<Lyric> lines;
    for (int i = 0; i < whisper_full_n_segments(context); ++i) {
        QString text = QString::fromUtf8(whisper_full_get_segment_text(context, i)).trimmed();
        double confidence = 0;
        int count = 0;
        double first = -1;
        for (int j = 0; j < whisper_full_n_tokens(context, i); ++j) {
            auto token = whisper_full_get_token_data(context, i, j);
            if (token.id < whisper_token_eot(context)) {
                confidence += token.p;
                ++count;
                if (first < 0 && (token.t_dtw >= 0 || token.t0 >= 0))
                    first = (token.t_dtw >= 0 ? token.t_dtw : token.t0) * .01;
            }
        }
        confidence /= qMax(1, count);
        const double noSpeech = whisper_full_get_segment_no_speech_prob(context, i);
        static const QRegularExpression annotation(
            "^[\\s\\[\\(]*(music|музыка|песня|instrumental|applause|аплодисменты)[\\s\\]\\)!.]*$",
            QRegularExpression::CaseInsensitiveOption);
        if (text.isEmpty() || normalized(text).isEmpty() || (confidence < .12 && noSpeech > .65) ||
            (noSpeech > .95 && confidence < .8) ||
            (annotation.match(text).hasMatch() && noSpeech > .25))
            continue;
        if (words) {
            QByteArray bytes;
            double begin = -1, finish = -1, probability = 0;
            int tokens = 0;
            auto flush = [&] {
                QString word = QString::fromUtf8(bytes).trimmed();
                const int left = qBound(0, int((begin - .06) * 16000), int(adjusted.size()));
                const int right = qBound(left, int((begin + .18) * 16000), int(adjusted.size()));
                double activity = 0;
                for (int sample = left; sample < right; ++sample)
                    activity += adjusted[sample] * adjusted[sample];
                const bool audible = right > left && std::sqrt(activity / (right - left)) > .00001;
                if (!normalized(word).isEmpty() && begin >= 0 && audible &&
                    begin < adjusted.size() / 16000.) {
                    if (language == "other_ru" || language == "other_en") {
                        const char* detected = whisper_lang_str(whisper_full_lang_id(context));
                        QString spoken = QString::fromLatin1(detected ? detected : "en");
                        if (spoken != "ru" && spoken != "en")
                            word =
                                soundSpelling(word, language == "other_ru" ? "ru" : "en", spoken);
                    }
                    words->append(
                        Lyric{qMax(0., origin + begin - LyricLead),
                              origin + qMin(adjusted.size() / 16000., qMax(begin, finish)), word,
                              probability / qMax(1, tokens)});
                }
                bytes.clear();
                begin = finish = -1;
                probability = 0;
                tokens = 0;
            };
            for (int j = 0; j < whisper_full_n_tokens(context, i); ++j) {
                auto token = whisper_full_get_token_data(context, i, j);
                if (token.id >= whisper_token_eot(context))
                    continue;
                QByteArray part(whisper_full_get_token_text(context, i, j));
                if (!bytes.isEmpty() && (part.startsWith(' ') || part.startsWith('\n')))
                    flush();
                const double onset = (token.t_dtw >= 0 ? token.t_dtw : token.t0) * .01;
                if (begin < 0 && onset >= 0)
                    begin = onset;
                finish = qMax(finish, token.t_dtw >= 0 ? onset + .08 : token.t1 * .01);
                probability += token.p;
                ++tokens;
                bytes += part;
            }
            flush();
        }
        if (language == "other_ru" || language == "other_en") {
            const char* detected = whisper_lang_str(whisper_full_lang_id(context));
            QString spoken = QString::fromLatin1(detected ? detected : "en");
            if (spoken != "ru" && spoken != "en")
                text = soundSpelling(text, language == "other_ru" ? "ru" : "en", spoken);
        }
        double start = first >= 0 ? first : whisper_full_get_segment_t0(context, i) * .01;
        double end = whisper_full_get_segment_t1(context, i) * .01;
        lines << Lyric{qMax(0., origin + start - LyricLead), origin + end, text, confidence};
    }
    return lines;
}
static std::optional<QPair<Lyric, int>> matchWords(const QString& text, const QList<Lyric>& words,
                                                   int first = 0, double preferred = -1) {
    double best = .6;
    std::optional<QPair<Lyric, int>> result;
    const qsizetype length = normalized(text).size();
    for (int start = first; start < words.size(); ++start) {
        QString combined;
        for (int end = start; end < words.size(); ++end) {
            combined += words[end].text;
            if (normalized(combined).size() > length * 1.8 + 16)
                break;
            double score = similarity(text, combined);
            bool nearer = preferred >= 0 && result && std::abs(score - best) < .02 &&
                          std::abs(words[start].start - preferred) <
                              std::abs(result->first.start - preferred);
            if (score > best + (preferred >= 0 ? .02 : 0) || nearer) {
                best = score;
                result = qMakePair(Lyric{words[start].start, words[end].end, text, score}, end);
            }
        }
        if (best >= .995 && preferred < 0)
            break;
    }
    return result;
}
static QList<Lyric> transcribeWindow(whisper_context* context, const QString& audio,
                                     const QString& reference, double at, double length,
                                     const QString& language, const QString& prompt,
                                     QList<Lyric>* words) {
    auto result =
        speechWindow(context, decode(audio, 16000, 1, at, length), at, language, prompt, words);
    double certainty = 0, gap = 0, previous = at;
    for (const auto& word : *words) {
        certainty += word.confidence;
        gap = qMax(gap, word.start - previous);
        previous = word.end;
    }
    gap = qMax(gap, at + length - previous);
    certainty /= qMax(qsizetype(1), words->size());
    if (!reference.isEmpty() && reference != audio &&
        (words->isEmpty() || certainty < .4 || gap > 6)) {
        QList<Lyric> alternativeWords;
        auto alternatives = speechWindow(context, decode(reference, 16000, 1, at, length), at,
                                         language, prompt, &alternativeWords);
        if (words->isEmpty()) {
            *words = alternativeWords;
            result = alternatives;
        }
        for (const auto& word : alternativeWords) {
            if (word.confidence < .4)
                continue;
            const double center = (word.start + word.end) / 2;
            bool covered = false;
            for (const auto& existing : *words)
                if (center >= existing.start - .55 && center <= existing.end + .55) {
                    covered = true;
                    break;
                }
            if (!covered)
                words->append(word);
        }
        std::stable_sort(words->begin(), words->end(),
                         [](const Lyric& a, const Lyric& b) { return a.start < b.start; });
    }
    // Recheck uncovered intervals in shorter contexts so a dominant language or intro
    // cannot suppress a short sung phrase in the same window.
    QList<QPair<double, double>> gaps;
    previous = at;
    for (const auto& word : *words) {
        if (word.start - previous > 5)
            gaps << qMakePair(previous, word.start + LyricLead);
        previous = qMax(previous, word.end);
    }
    if (at + length - previous > 5)
        gaps << qMakePair(previous, at + length);
    int budget = 3;
    for (auto gap : gaps) {
        for (double begin = gap.first; begin < gap.second - .5 && budget > 0; begin += 9) {
            --budget;
            QList<Lyric> recovered;
            auto snippet = decode(audio, 16000, 1, begin, qMin(11., gap.second - begin));
            double peak = 0;
            for (float sample : snippet)
                peak = qMax(peak, std::abs(double(sample)));
            int active = 0;
            for (qsizetype offset = 0; offset + 160 <= snippet.size(); offset += 160) {
                double energy = 0;
                for (int sample = 0; sample < 160; ++sample)
                    energy += snippet[offset + sample] * snippet[offset + sample];
                active += std::sqrt(energy / 160) > qMax(.0001, peak * .03);
            }
            if (active < 12)
                continue;
            speechWindow(context, snippet, begin,
                         language == "ru" || language == "en" ? QString("auto") : language, {},
                         &recovered);
            for (const auto& word : recovered) {
                if (word.confidence < .3)
                    continue;
                bool duplicate = false;
                for (const auto& existing : *words)
                    if (normalized(word.text) == normalized(existing.text) &&
                        std::abs(word.start - existing.start) < .75) {
                        duplicate = true;
                        break;
                    }
                if (!duplicate)
                    words->append(word);
            }
        }
    }
    std::stable_sort(words->begin(), words->end(),
                     [](const Lyric& a, const Lyric& b) { return a.start < b.start; });
    return result;
}
int neuralWorker(const QStringList& arguments) {
    auto option = [&](const QString& key) {
        int i = arguments.indexOf(key);
        return i >= 0 && i + 1 < arguments.size() ? arguments[i + 1] : QString();
    };
    QString result = option("--result");
    try {
#if defined(__GNUC__) && (defined(__x86_64__) || defined(__i386__))
        __builtin_cpu_init();
        if (!__builtin_cpu_supports("avx2")) throw Error("Для нейросетевой обработки нужен процессор с AVX2. Редактор и метаданные доступны без распознавания.");
#endif
        if (arguments.contains("--stems-worker")) {
            const auto source = readSource(option("--audio"));
            QStorageInfo disk(option("--out"));
            const qint64 required =
                qint64(std::ceil(source.duration * 44100 * 2 * 4 * 4)) + 64 * 1024 * 1024;
            if (disk.isValid() && disk.bytesAvailable() < required)
                throw Error("Недостаточно места для четырёх WAV-файлов");
            auto model = std::make_unique<demucscpp::demucs_model>();
            QByteArray path = option("--model").toUtf8();
            if (!demucscpp::load_demucs_model(path.toStdString(), model.get()))
                throw Error("Не удалось загрузить HTDemucs");
            QStringList names{"drums", "bass", "other", "vocals"};
            std::vector<std::unique_ptr<WavWriter>> writers;
            for (const auto& name : names)
                writers.push_back(
                    std::make_unique<WavWriter>(option("--out") + "/" + name + ".wav", 44100, 2, true));
            QVector<float> tails[4];
            const double blockSeconds =
                option("--segment-seconds").isEmpty()
                    ? 60
                    : qBound(2., option("--segment-seconds").toDouble(), 60.);
            constexpr double overlapSeconds = 2;
            for (double at = 0; at < source.duration; at += blockSeconds) {
                auto values = decode(source.path, 44100, 2, at,
                                     qMin(blockSeconds + overlapSeconds, source.duration - at));
                const qsizetype frames = values.size() / 2;
                if (!frames)
                    break;
                Eigen::MatrixXf audio(2, frames);
                for (qsizetype i = 0; i < frames; ++i) {
                    audio(0, i) = values[i * 2];
                    audio(1, i) = values[i * 2 + 1];
                }
                values.clear();
                values.squeeze();
                auto targets = demucscpp::demucs_inference(
                    *model, audio,
                    [at, blockSeconds, total = source.duration](float value, const std::string&) {
                        std::cerr << "progress=" << qMin(1., (at + blockSeconds * value) / total)
                                  << std::endl;
                    });
                const qsizetype writeFrames = qMin(frames, qsizetype(blockSeconds * 44100));
                for (int stem = 0; stem < 4; ++stem) {
                    QVector<float> block(writeFrames * 2);
                    for (qsizetype i = 0; i < writeFrames; ++i)
                        for (int channel = 0; channel < 2; ++channel) {
                            float sample = targets(stem, channel, i);
                            if (i * 2 + channel < tails[stem].size()) {
                                double weight =
                                    double(i) / qMax(qsizetype(1), tails[stem].size() / 2 - 1);
                                sample = float(tails[stem][i * 2 + channel] * (1 - weight) +
                                               sample * weight);
                            }
                            block[i * 2 + channel] = sample;
                        }
                    writers[stem]->append(block.constData(), block.size());
                    tails[stem].resize((frames - writeFrames) * 2);
                    for (qsizetype i = writeFrames; i < frames; ++i)
                        for (int channel = 0; channel < 2; ++channel)
                            tails[stem][(i - writeFrames) * 2 + channel] =
                                targets(stem, channel, i);
                }
            }
            for (auto& writer : writers)
                writer->finish();
            return 0;
        }
        if (!arguments.contains("--speech-worker"))
            return -1;
        if (arguments.contains("--ctc-only") || arguments.contains("--ctc-direct")) {
            QFile text(option("--align"));
            if (!text.open(QIODevice::ReadOnly))
                throw Error(text.errorString());
            auto supplied = QString::fromUtf8(text.readAll());
            auto lines = parseLyrics(supplied, false);
            if (lines.isEmpty())
                for (const auto& line : plainLyrics(supplied).split('\n', Qt::SkipEmptyParts))
                    lines << Lyric{-1, -1, line.trimmed(), 0};
            if (arguments.contains("--ctc-direct"))
                lines = alignSuppliedLyrics(option("--audio"), supplied, QFileInfo(option("--model")).absolutePath(), option("--reference"));
            else lines = refineSpeechTiming(
                option("--audio"), lines, QFileInfo(option("--model")).absolutePath(),
                option("--reference"), !arguments.contains("--verify-recognition"));
            QJsonArray output;
            for (const auto& line : lines) {
                if (line.start < 0)
                    throw Error("Текст не найден в звуке");
                output << QJsonObject{{"start", line.start},
                                      {"end", line.end},
                                      {"text", line.text},
                                      {"confidence", line.confidence}};
            }
            QSaveFile file(result);
            if (!file.open(QIODevice::WriteOnly))
                throw Error(file.errorString());
            file.write(QJsonDocument(QJsonObject{{"lines", output}}).toJson());
            if (!file.commit())
                throw Error(file.errorString());
            return 0;
        }
        auto params = whisper_context_default_params();
        params.use_gpu = !qEnvironmentVariableIsSet("SF_CPU_ONLY");
        params.flash_attn = false;
        params.dtw_token_timestamps = true;
        params.dtw_aheads_preset = option("--model").contains("turbo")
                                       ? WHISPER_AHEADS_LARGE_V3_TURBO
                                       : WHISPER_AHEADS_LARGE_V3;
        QByteArray path = option("--model").toUtf8();
        std::unique_ptr<whisper_context, decltype(&whisper_free)> context(
            whisper_init_from_file_with_params(path.constData(), params), &whisper_free);
        if (!context)
            throw Error("Не удалось загрузить модель Whisper");
        auto source = readSource(option("--audio"));
        const QString reference = option("--reference");
        QString language = option("--language");
        QList<Lyric> lines, traceWords;
        QString align = option("--align");
        if (!align.isEmpty()) {
            QFile textFile(align);
            if (!textFile.open(QIODevice::ReadOnly))
                throw Error(textFile.errorString());
            QString supplied = QString::fromUtf8(textFile.readAll());
            auto anchors = parseLyrics(supplied, false);
            QStringList textLines = plainLyrics(supplied).split('\n', Qt::SkipEmptyParts);
            for (auto& line : textLines)
                line = line.trimmed();
            if (anchors.size() == textLines.size() && !anchors.isEmpty()) {
                for (int i = 0; i < anchors.size(); ++i) {
                    double left = qMax(0., anchors[i].start - 4),
                           right = qMin(source.duration, anchors[i].start + 16);
                    if (i > 0)
                        left = qMax(left, anchors[i - 1].start + .01);
                    if (i + 1 < anchors.size())
                        right = qMin(right, anchors[i + 1].start + 8);
                    Lyric value = anchors[i];
                    value.confidence = 0;
                    if (right > left) {
                        QList<Lyric> words;
                        auto candidates =
                            transcribeWindow(context.get(), source.path, reference, left,
                                             right - left, language, value.text, &words);
                        auto matched = matchWords(value.text, words, 0, value.start);
                        if (matched)
                            value = matched->first;
                        double best = 0;
                        for (auto& candidate : candidates) {
                            double score = similarity(value.text, candidate.text);
                            if (!matched && score > best && score > .6) {
                                best = score;
                                value.start = candidate.start;
                                value.end = candidate.end;
                                value.confidence = candidate.confidence;
                            }
                        }
                    }
                    lines << value;
                    std::cerr << "progress=" << .8 * double(i + 1) / anchors.size() << std::endl;
                }
            } else {
                QList<Lyric> detected;
                QList<Lyric> allWords;
                for (double at = 0; at < source.duration; at += 20) {
                    QList<Lyric> words;
                    transcribeWindow(context.get(), source.path, reference, at,
                                     qMin(26., source.duration - at), language, supplied.left(500),
                                     &words);
                    appendSpeechWindow(allWords, words, at == 0 ? 0 : at + 3, at + 23);
                    std::cerr << "progress=" << .8 * qMin(1., (at + 20) / source.duration)
                              << std::endl;
                }
                detected = speechLines(allWords);
                int previous = 0;
                int previousWord = 0;
                for (auto& line : textLines) {
                    auto match = matchWords(line, allWords, previousWord);
                    if (match) {
                        lines << match->first;
                        previousWord = match->second + 1;
                        while (previous < detected.size() &&
                               detected[previous].end <= match->first.end)
                            ++previous;
                        continue;
                    }
                    double best = 0;
                    int index = -1;
                    for (int i = previous; i < detected.size(); ++i) {
                        double score = similarity(line, detected[i].text);
                        if (score > best) {
                            best = score;
                            index = i;
                        }
                    }
                    if (index < 0 || best < .4) {
                        lines << Lyric{-1, -1, line, 0};
                        continue;
                    }
                    Lyric value = detected[index];
                    value.text = line;
                    lines << value;
                    previous = index + 1;
                }
            }
            for (int i = 1; i < lines.size(); ++i)
                if (lines[i].start >= 0 && lines[i - 1].start >= 0 &&
                    lines[i].start < lines[i - 1].start) {
                    if (i < anchors.size()) {
                        lines[i] = anchors[i];
                        for (int j = i - 1; j >= 0 && lines[j].start > lines[j + 1].start; --j)
                            lines[j] = anchors[j];
                    } else
                        throw Error("Порядок строк не подтверждён");
                }
        } else {
            QList<Lyric> allWords;
            for (double at = 0; at < source.duration; at += 20) {
                QList<Lyric> words;
                transcribeWindow(context.get(), source.path, reference, at,
                                 qMin(26., source.duration - at), language, {}, &words);
                appendSpeechWindow(allWords, words, at == 0 ? 0 : at + 3, at + 23);
                std::cerr << "progress=" << .8 * qMin(1., (at + 20) / source.duration) << std::endl;
            }
            lines = speechLines(allWords);
            traceWords = allWords;
        }
        context.reset(); // Never hold Whisper and the alignment model in memory together.
        lines = refineSpeechTiming(source.path, lines, QFileInfo(option("--model")).absolutePath(),
                                   reference, !align.isEmpty());
        for (const auto& line : lines)
            if (line.start < 0)
                throw Error("Не все строки удалось сопоставить со звуком. Исходный текст сохранён; "
                            "добавьте примерные метки для непонятных строк.");
        QJsonArray array;
        for (auto& line : lines)
            array << QJsonObject{{"start", line.start},
                                 {"end", line.end},
                                 {"text", line.text},
                                 {"confidence", line.confidence}};
        QSaveFile out(result);
        if (!out.open(QIODevice::WriteOnly))
            throw Error(out.errorString());
        QJsonObject payload{{"lines", array}};
        if (arguments.contains("--trace-words")) {
            QJsonArray words;
            for (const auto& word : traceWords)
                words << QJsonObject{{"start", word.start},
                                     {"end", word.end},
                                     {"text", word.text},
                                     {"confidence", word.confidence}};
            payload["words"] = words;
        }
        out.write(QJsonDocument(payload).toJson());
        if (!out.commit())
            throw Error(out.errorString());
        return 0;
    } catch (const std::exception& e) {
        if (!result.isEmpty()) {
            QFile out(result);
            if (out.open(QIODevice::WriteOnly))
                out.write(
                    QJsonDocument(QJsonObject{{"error", QString::fromUtf8(e.what())}}).toJson());
        }
        std::cerr << e.what() << std::endl;
        return 1;
    }
}

QString genre(const QString& audio, const Cancel& cancel, Progress progress) {
    QLibrary library(QCoreApplication::applicationDirPath() + "/tools/onnxruntime.dll");
    if (!library.load())
        throw Error("Не найдена нативная библиотека ONNX Runtime");
    using ApiBase = const OrtApiBase*(ORT_API_CALL*)();
    auto getApi = reinterpret_cast<ApiBase>(library.resolve("OrtGetApiBase"));
    if (!getApi)
        throw Error("ONNX Runtime API недоступен");
    const OrtApi* api = getApi()->GetApi(ORT_API_VERSION);
    if (!api)
        throw Error("Версия ONNX Runtime не поддерживается");
    auto check = [&](OrtStatus* status) {
        if (status) {
            QString message = QString::fromUtf8(api->GetErrorMessage(status));
            api->ReleaseStatus(status);
            throw Error(message);
        }
    };
    OrtEnv* env = nullptr;
    OrtSessionOptions* options = nullptr;
    OrtSession* session = nullptr;
    OrtMemoryInfo* memory = nullptr;
    OrtAllocator* allocator = nullptr;
    struct Cleanup {
        const OrtApi* api;
        OrtEnv*& env;
        OrtSessionOptions*& options;
        OrtSession*& session;
        OrtMemoryInfo*& memory;
        ~Cleanup() {
            if (session)
                api->ReleaseSession(session);
            if (memory)
                api->ReleaseMemoryInfo(memory);
            if (options)
                api->ReleaseSessionOptions(options);
            if (env)
                api->ReleaseEnv(env);
        }
    } cleanup{api, env, options, session, memory};
    QString root = QCoreApplication::applicationDirPath() + "/models/genre";
    if (!QFile::exists(root + "/manifest.json"))
        root = QDir::currentPath() + "/assets/models/genre";
    QFile manifest(root + "/manifest.json");
    if (!manifest.open(QIODevice::ReadOnly))
        throw Error("Не найдена модель жанров");
    auto metadata = QJsonDocument::fromJson(manifest.readAll()).object();
    QString model = root + "/msd_musicnn.onnx";
    QFile modelFile(model);
    if (!modelFile.open(QIODevice::ReadOnly))
        throw Error(modelFile.errorString());
    if (QCryptographicHash::hash(modelFile.readAll(), QCryptographicHash::Sha256).toHex() !=
        metadata["sha256"].toString().toLatin1())
        throw Error("Контрольная сумма модели жанров не совпадает");
    check(api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "SonicForge", &env));
    check(api->CreateSessionOptions(&options));
    check(api->SetIntraOpNumThreads(options, 2));
    check(api->SetInterOpNumThreads(options, 1));
    check(api->CreateSession(env, reinterpret_cast<const wchar_t*>(model.utf16()), options,
                             &session));
    check(api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &memory));
    check(api->GetAllocatorWithDefaultOptions(&allocator));
    char* input = nullptr;
    char* output = nullptr;
    check(api->SessionGetInputName(session, 0, allocator, &input));
    check(api->SessionGetOutputName(session, 0, allocator, &output));
    QByteArray inputName(input), outputName(output);
    allocator->Free(allocator, input);
    allocator->Free(allocator, output);
    auto hzToMel = [](double hz) {
        return hz < 1000 ? hz / (200. / 3) : 15 + std::log(hz / 1000) / (std::log(6.4) / 27);
    };
    auto melToHz = [](double mel) {
        return mel < 15 ? mel * (200. / 3) : 1000 * std::exp((mel - 15) * (std::log(6.4) / 27));
    };
    QVector<double> frequencies(98);
    for (int i = 0; i < 98; ++i)
        frequencies[i] = melToHz(hzToMel(8000) * i / 97);
    QVector<QVector<float>> filters(96, QVector<float>(257));
    for (int mel = 0; mel < 96; ++mel)
        for (int bin = 0; bin < 257; ++bin) {
            double f = bin * 16000. / 512;
            filters[mel][bin] =
                qMax(0., qMin((f - frequencies[mel]) / (frequencies[mel + 1] - frequencies[mel]),
                              (frequencies[mel + 2] - f) /
                                  (frequencies[mel + 2] - frequencies[mel + 1]))) *
                2 / (frequencies[mel + 2] - frequencies[mel]);
        }
    auto info = readSource(audio, cancel);
    auto labels = metadata["labels"].toArray();
    QVector<double> sums(labels.size()), support(labels.size());
    int patches = 0;
    int regions = qMin(30, qMax(1, int(std::ceil(info.duration / 30))));
    double width = qMin(9., info.duration / regions);
    for (int region = 0; region < regions; ++region) {
        double at = qMax(0., (region + .5) * info.duration / regions - width / 2);
        auto samples = decode(audio, 16000, 1, at, width, cancel);
        for (int offset = 0; offset + 24000 <= samples.size(); offset += 48000) {
            checkpoint(cancel);
            double rms = 0;
            int size = qMin(48000, samples.size() - offset);
            for (int i = 0; i < size; ++i)
                rms += samples[offset + i] * samples[offset + i];
            if (std::sqrt(rms / size) < .001)
                continue;
            QVector<float> feature(187 * 96);
            for (int frame = 0; frame < 187; ++frame) {
                QList<std::complex<double>> signal(512);
                for (int i = 0; i < 512; ++i) {
                    int index = frame * 256 + i - 256;
                    if (index < 0)
                        index = -index;
                    if (index >= 48000)
                        index = 95998 - index;
                    index = qBound(0, index % size, size - 1);
                    signal[i] = samples[offset + index] *
                                (.5 - .5 * std::cos(2 * std::numbers::pi * i / 512));
                }
                auto bins = fft(signal);
                for (int mel = 0; mel < 96; ++mel) {
                    double value = 0;
                    for (int k = 0; k < 257; ++k)
                        value += std::norm(bins[k]) * filters[mel][k];
                    feature[frame * 96 + mel] = std::log10(1 + 10000 * value);
                }
            }
            int64_t shape[]{1, 187, 96};
            OrtValue* in = nullptr;
            OrtValue* out = nullptr;
            check(api->CreateTensorWithDataAsOrtValue(memory, feature.data(),
                                                      feature.size() * sizeof(float), shape, 3,
                                                      ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &in));
            const char* inputs[]{inputName.constData()};
            const char* outputs[]{outputName.constData()};
            const OrtValue* values[]{in};
            OrtStatus* status = api->Run(session, nullptr, inputs, values, 1, outputs, 1, &out);
            api->ReleaseValue(in);
            check(status);
            float* scores = nullptr;
            check(api->GetTensorMutableData(out, reinterpret_cast<void**>(&scores)));
            for (int i = 0; i < labels.size(); ++i) {
                if (!std::isfinite(scores[i])) {
                    api->ReleaseValue(out);
                    throw Error("Неверный результат модели жанров");
                }
                sums[i] += scores[i];
                if (scores[i] >= .2f)
                    support[i]++;
            }
            api->ReleaseValue(out);
            patches++;
        }
        if (progress)
            progress("Анализ жанра", double(region + 1) / regions);
    }
    if (!patches)
        return {};
    QSet<QString> allowed{"rock",
                          "pop",
                          "alternative",
                          "indie",
                          "electronic",
                          "dance",
                          "alternative rock",
                          "jazz",
                          "metal",
                          "chillout",
                          "classic rock",
                          "soul",
                          "indie rock",
                          "electronica",
                          "folk",
                          "punk",
                          "blues",
                          "hard rock",
                          "ambient",
                          "acoustic",
                          "experimental",
                          "hip-hop",
                          "country",
                          "easy listening",
                          "funk",
                          "electro",
                          "heavy metal",
                          "progressive rock",
                          "rnb",
                          "indie pop",
                          "house"};
    QList<int> indices;
    for (int i = 0; i < labels.size(); ++i)
        indices << i;
    std::sort(indices.begin(), indices.end(), [&](int a, int b) { return sums[a] > sums[b]; });
    QStringList selected;
    for (int i : indices) {
        QString name = labels[i].toString().toLower();
        if (allowed.contains(name) && sums[i] / patches >= .2 && support[i] / patches >= .4) {
            name = name == "rnb" ? "R&B" : name;
            for (int j = 0; j < name.size(); ++j)
                if (j == 0 || name[j - 1] == ' ' || name[j - 1] == '-')
                    name[j] = name[j].toUpper();
            selected << name;
            if (selected.size() == 3)
                break;
        }
    }
    if (progress) {
        QStringList explanation;
        for (int i : indices) if (allowed.contains(labels[i].toString().toLower()) && sums[i] / patches >= .1) {
            explanation << labels[i].toString() + " " + QString::number(sums[i] / patches * 100, 'f', 0) + "%";
            if (explanation.size() == 3) break;
        }
        progress(explanation.isEmpty() ? "Жанр не определён уверенно" : "MSD: " + explanation.join(", "), 1);
    }
    return selected.join("; ");
}
} // namespace sf
