#include "core.h"
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
    const QString path = modelRoot() + "/" + name;
    const QByteArray expected = model["sha256"].toString().toLatin1();
    if (QFileInfo(path).size() == model["size"].toInteger()) {
        QFile input(path);
        QCryptographicHash hash(QCryptographicHash::Sha256);
        if (input.open(QIODevice::ReadOnly) && hash.addData(&input) &&
            hash.result().toHex() == expected)
            return path;
        throw Error("Контрольная сумма модели не совпадает: " + path);
    }
    const QUrl url(model["url"].toString());
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile output(path);
    if (!output.open(QIODevice::WriteOnly))
        throw Error(output.errorString());
    QNetworkAccessManager manager;
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                         QNetworkRequest::NoLessSafeRedirectPolicy);
    auto* reply = manager.get(request);
    QCryptographicHash hash(QCryptographicHash::Sha256);
    QEventLoop loop;
    QTimer timer;
    timer.setInterval(100);
    QObject::connect(&timer, &QTimer::timeout, &loop, [&] {
        if (cancel && cancel->load())
            reply->abort();
    });
    QObject::connect(reply, &QNetworkReply::readyRead, &loop, [&] {
        auto bytes = reply->readAll();
        hash.addData(bytes);
        output.write(bytes);
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
QList<Lyric> recognize(const QString& audio, const QString& language, const Cancel& cancel,
                       Progress progress) {
    QString model = ensureModel("speech", cancel, progress), result = uniqueFile(".json");
    process(QCoreApplication::applicationFilePath(),
            {"--speech-worker", "--audio", audio, "--model", model, "--language", language,
             "--result", result},
            cancel, progress);
    auto lines = readResult(result);
    QFile::remove(result);
    return lines;
}
QList<Lyric> alignLyrics(const QString& audio, const QString& text, const QString& language,
                         const Cancel& cancel, Progress progress) {
    QString model = ensureModel("speech", cancel, progress), result = uniqueFile(".json"),
            input = uniqueFile(".txt");
    QFile file(input);
    if (!file.open(QIODevice::WriteOnly))
        throw Error(file.errorString());
    file.write(text.toUtf8());
    file.close();
    try {
        process(QCoreApplication::applicationFilePath(),
                {"--speech-worker", "--audio", audio, "--model", model, "--language", language,
                 "--result", result, "--align", input},
                cancel, progress);
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
    } else
        files << out + "/drums.wav" << out + "/bass.wav" << out + "/other.wav";
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
                                 QList<Lyric>* words = nullptr) {
    whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
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
    params.no_speech_thold = .65f;
    params.temperature = 0;
    params.temperature_inc = 0;
    params.greedy.best_of = 1;
    QByteArray lang = language.toUtf8(), hint = prompt.toUtf8();
    if (language == "other_ru" || language == "other_en" || language == "auto" ||
        language.isEmpty())
        params.language = "auto";
    else
        params.language = lang.constData();
    if (!prompt.isEmpty())
        params.initial_prompt = hint.constData();
    if (whisper_full(context, params, audio.constData(), int(audio.size())) != 0)
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
        if (text.isEmpty() || normalized(text).size() < 2 || confidence < .25 ||
            whisper_full_get_segment_no_speech_prob(context, i) > .8f)
            continue;
        if (words) {
            QByteArray bytes;
            double begin = -1, finish = -1, probability = 0;
            int tokens = 0;
            auto flush = [&] {
                QString word = QString::fromUtf8(bytes).trimmed();
                if (!normalized(word).isEmpty() && begin >= 0) {
                    if (language == "other_ru" || language == "other_en") {
                        const char* detected = whisper_lang_str(whisper_full_lang_id(context));
                        QString spoken = QString::fromLatin1(detected ? detected : "en");
                        if (spoken != "ru" && spoken != "en")
                            word =
                                soundSpelling(word, language == "other_ru" ? "ru" : "en", spoken);
                    }
                    words->append(Lyric{qMax(0., origin + begin - .1), origin + qMax(begin, finish),
                                        word, probability / qMax(1, tokens)});
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
        lines << Lyric{qMax(0., origin + start - .1), origin + end, text, confidence};
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
int neuralWorker(const QStringList& arguments) {
    auto option = [&](const QString& key) {
        int i = arguments.indexOf(key);
        return i >= 0 && i + 1 < arguments.size() ? arguments[i + 1] : QString();
    };
    QString result = option("--result");
    try {
        if (arguments.contains("--stems-worker")) {
            auto values = decode(option("--audio"), 44100, 2);
            if (values.isEmpty())
                throw Error("Нет звука");
            Eigen::MatrixXf audio(2, values.size() / 2);
            for (qsizetype i = 0; i < values.size() / 2; ++i) {
                audio(0, i) = values[i * 2];
                audio(1, i) = values[i * 2 + 1];
            }
            values.clear();
            values.squeeze();
            auto model = std::make_unique<demucscpp::demucs_model>();
            QByteArray path = option("--model").toUtf8();
            if (!demucscpp::load_demucs_model(path.toStdString(), model.get()))
                throw Error("Не удалось загрузить HTDemucs");
            auto targets =
                demucscpp::demucs_inference(*model, audio, [](float value, const std::string&) {
                    std::cerr << "progress=" << value << std::endl;
                });
            QStringList names{"drums", "bass", "other", "vocals"};
            for (int stem = 0; stem < 4; ++stem) {
                QVector<float> samples(audio.cols() * 2);
                for (int i = 0; i < audio.cols(); ++i) {
                    samples[i * 2] = targets(stem, 0, i);
                    samples[i * 2 + 1] = targets(stem, 1, i);
                }
                writeWav(option("--out") + "/" + names[stem] + ".wav", samples, 44100, 2);
            }
            return 0;
        }
        if (!arguments.contains("--speech-worker"))
            return -1;
        auto params = whisper_context_default_params();
        params.use_gpu = false;
        params.flash_attn = false;
        params.dtw_token_timestamps = true;
        params.dtw_aheads_preset = WHISPER_AHEADS_LARGE_V3_TURBO;
        QByteArray path = option("--model").toUtf8();
        std::unique_ptr<whisper_context, decltype(&whisper_free)> context(
            whisper_init_from_file_with_params(path.constData(), params), &whisper_free);
        if (!context)
            throw Error("Не удалось загрузить модель Whisper");
        auto source = readSource(option("--audio"));
        QString language = option("--language");
        QList<Lyric> lines;
        QString align = option("--align");
        if (!align.isEmpty()) {
            QFile textFile(align);
            if (!textFile.open(QIODevice::ReadOnly))
                throw Error(textFile.errorString());
            QString supplied = QString::fromUtf8(textFile.readAll());
            auto anchors = parseLyrics(supplied, false);
            QStringList textLines = plainLyrics(supplied).split('\n', Qt::SkipEmptyParts);
            if (anchors.size() == textLines.size() && !anchors.isEmpty()) {
                for (int i = 0; i < anchors.size(); ++i) {
                    double left = qMax(0., anchors[i].start - 4),
                           right = qMin(source.duration, anchors[i].start + 16);
                    if (i > 0)
                        left = qMax(left, anchors[i - 1].start + .01);
                    if (i + 1 < anchors.size())
                        right = qMin(right, anchors[i + 1].start + 8);
                    Lyric value = anchors[i];
                    if (right > left) {
                        auto decoded = decode(source.path, 16000, 1, left, right - left);
                        QList<Lyric> words;
                        auto candidates = speechWindow(context.get(), decoded, left, language,
                                                       value.text, &words);
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
                    std::cerr << "progress=" << double(i + 1) / anchors.size() << std::endl;
                }
            } else {
                QList<Lyric> detected;
                QList<Lyric> allWords;
                for (double at = 0; at < source.duration; at += 20) {
                    auto decoded =
                        decode(source.path, 16000, 1, at, qMin(26., source.duration - at));
                    QList<Lyric> words;
                    auto found = speechWindow(context.get(), decoded, at, language,
                                              supplied.left(500), &words);
                    for (auto& candidate : found)
                        if (detected.isEmpty() || candidate.start >= detected.last().end - .2)
                            detected << candidate;
                    double lastEnd = allWords.isEmpty() ? -1 : allWords.last().end;
                    for (const auto& word : words)
                        if (word.start >= lastEnd - .02)
                            allWords << word;
                }
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
                    if (index < 0 || best < .4)
                        throw Error("Не все строки найдены в аудио. Исходный текст сохранён; "
                                    "добавьте начальные таймкоды для точной коррекции.");
                    Lyric value = detected[index];
                    value.text = line;
                    lines << value;
                    previous = index + 1;
                }
            }
            for (int i = 1; i < lines.size(); ++i)
                if (lines[i].start < lines[i - 1].start) {
                    if (i < anchors.size()) {
                        lines[i] = anchors[i];
                        for (int j = i - 1; j >= 0 && lines[j].start > lines[j + 1].start; --j)
                            lines[j] = anchors[j];
                    } else
                        throw Error("Порядок строк не подтверждён");
                }
        } else {
            for (double at = 0; at < source.duration; at += 20) {
                auto decoded = decode(source.path, 16000, 1, at, qMin(26., source.duration - at));
                auto detected = speechWindow(context.get(), decoded, at, language);
                for (auto value : detected) {
                    if (!lines.isEmpty() && value.start < lines.last().end) {
                        if (similarity(value.text, lines.last().text) > .6)
                            continue;
                        if (value.end <= lines.last().end)
                            continue;
                    }
                    if (!lines.isEmpty() &&
                        normalized(value.text) == normalized(lines.last().text) &&
                        value.start - lines.last().end < 1)
                        continue;
                    lines << value;
                }
                std::cerr << "progress=" << qMin(1., (at + 20) / source.duration) << std::endl;
            }
        }
        QJsonArray array;
        for (auto& line : lines)
            array << QJsonObject{{"start", line.start},
                                 {"end", line.end},
                                 {"text", line.text},
                                 {"confidence", line.confidence}};
        QSaveFile out(result);
        if (!out.open(QIODevice::WriteOnly))
            throw Error(out.errorString());
        out.write(QJsonDocument(QJsonObject{{"lines", array}}).toJson());
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
    int regions = qMin(5, qMax(1, int(std::ceil(info.duration / 9))));
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
    return selected.join("; ");
}
} // namespace sf
