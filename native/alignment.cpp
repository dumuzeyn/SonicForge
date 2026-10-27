#include "speech.h"
#ifndef _MSC_VER
#ifndef _Return_type_success_
#define _Return_type_success_(X)
#endif
#endif
#include "vendor/onnxruntime_c_api.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>

namespace sf {
std::optional<CtcMatch> ctcViterbiView(const float* emission, qsizetype emissionSize, int frames, int vocabulary,
                                    const QVector<int>& tokens, int blank) {
    if (tokens.isEmpty() || frames < tokens.size() || vocabulary < 2 || blank < 0 || blank >= vocabulary ||
        emissionSize != qsizetype(frames) * vocabulary || tokens.size() > 1000000) return {};
    for (int token : tokens) if (token < 0 || token >= vocabulary || token == blank) return {};
    const int states = int(tokens.size()) * 2 + 1;
    const int blockFrames = qBound(1, (16 * 1024 * 1024) / states, 512);
    const float impossible = -std::numeric_limits<float>::infinity();
    QVector<float> previous(states, impossible), current(states, impossible);
    previous[0] = 0;
    QTemporaryFile checkpoints(cacheDirectory() + "/ctc-scores-XXXXXX.bin");
    if (!checkpoints.open()) throw Error(checkpoints.errorString());
    auto advance = [&](int t, QByteArray* back, int localFrame) {
        current.fill(impossible); current[0] = 0;
        for (int state = 1; state < states; ++state) {
            const int token = state % 2 ? tokens[state / 2] : blank;
            float score = previous[state]; int step = 0;
            if (previous[state - 1] > score) { score = previous[state - 1]; step = 1; }
            if (state > 1 && token != blank && token != tokens[(state - 2) / 2] && previous[state - 2] > score) { score = previous[state - 2]; step = 2; }
            current[state] = score + emission[qsizetype(t) * vocabulary + token];
            if (back) (*back)[qsizetype(localFrame) * states + state] = char(step);
        }
        previous.swap(current);
    };
    float best = impossible; int bestFrame = -1;
    const qint64 rowBytes = qint64(states) * sizeof(float);
    for (int t = 0; t < frames; ++t) {
        if (t % blockFrames == 0 && checkpoints.write(reinterpret_cast<const char*>(previous.constData()), rowBytes) != rowBytes) throw Error(checkpoints.errorString());
        advance(t, nullptr, 0);
        if (previous[states - 2] > best) { best = previous[states - 2]; bestFrame = t; }
    }
    if (bestFrame < 0 || !std::isfinite(best)) return {};
    CtcMatch match; match.first.fill(-1, tokens.size()); match.last.fill(-1, tokens.size());
    QVector<float> peaks(tokens.size(), 0); int state = states - 2;
    for (int block = bestFrame / blockFrames; block >= 0 && state > 0; --block) {
        if (!checkpoints.seek(qint64(block) * rowBytes) || checkpoints.read(reinterpret_cast<char*>(previous.data()), rowBytes) != rowBytes) throw Error(checkpoints.errorString());
        const int first = block * blockFrames, last = qMin(bestFrame, first + blockFrames - 1);
        QByteArray back(qsizetype(last - first + 1) * states, 0);
        for (int t = first; t <= last; ++t) advance(t, &back, t - first);
        for (int t = last; t >= first && state > 0; --t) {
            if (state % 2) {
                const int index = state / 2; match.first[index] = t; match.last[index] = qMax(match.last[index], t);
                peaks[index] = qMax(peaks[index], std::exp(emission[qsizetype(t) * vocabulary + tokens[index]]));
            }
            state -= quint8(back[qsizetype(t - first) * states + state]);
        }
    }
    if (state != 0 || match.first.contains(-1)) return {};
    int supported = 0;
    for (float peak : peaks) { match.confidence += peak; supported += peak >= .12; }
    match.confidence /= peaks.size(); match.tokenConfidence = peaks; match.coverage = double(supported) / peaks.size();
    return match;
}
std::optional<CtcMatch> ctcViterbi(const QVector<float>& emission, int frames, int vocabulary,
                                    const QVector<int>& tokens, int blank) {
    return ctcViterbiView(emission.constData(), emission.size(), frames, vocabulary, tokens, blank);
}

void appendSpeechWindow(QList<Lyric>& target, const QList<Lyric>& words, double begin, double end) {
    for (const auto& word : words) {
        // Ownership is by word onset, never by a whole overlapping segment.
        const double onset = word.start + LyricLead;
        if (onset >= begin && onset < end)
            target << word;
    }
}
QList<Lyric> speechLines(const QList<Lyric>& words) {
    QList<Lyric> lines;
    Lyric line;
    line.confidence = 0;
    int count = 0;
    auto flush = [&] {
        if (!line.text.isEmpty()) {
            line.confidence /= qMax(1, count);
            lines << line;
        }
        line = {};
        line.confidence = 0;
        count = 0;
    };
    for (const auto& word : words) {
        if (!line.text.isEmpty() &&
            (word.start - line.end > .85 || count >= 13 || word.end - line.start > 8.5))
            flush();
        if (line.text.isEmpty())
            line.start = word.start;
        if (!line.text.isEmpty())
            line.text += ' ';
        line.text += word.text;
        line.end = qMax(line.end, word.end);
        line.confidence += word.confidence;
        ++count;
        if (word.text.endsWith('.') || word.text.endsWith('!') || word.text.endsWith('?') ||
            word.text.endsWith(QChar(0x3002))) {
            flush();
        }
    }
    flush();
    return lines;
}

namespace {
struct CtcEmission { QVector<float> probabilities; int frames = 0, classes = 0; };
class CtcEngine {
    QLibrary library;
    const OrtApi* api = nullptr;
    OrtEnv* environment = nullptr;
    OrtSessionOptions* options = nullptr;
    OrtSession* session = nullptr;
    OrtMemoryInfo* memory = nullptr;
    QVector<QByteArray> names;
    QByteArray outputName;
    QJsonObject vocabulary;

  public:
    QString language;
    void check(OrtStatus* status) {
        if (status) {
            auto message = QString::fromUtf8(api->GetErrorMessage(status));
            api->ReleaseStatus(status);
            throw Error(message);
        }
    }
    explicit CtcEngine(const QString& path, const QString& lang)
        : library(QCoreApplication::applicationDirPath() + "/tools/onnxruntime.dll"),
          language(lang) {
        if (!library.load())
            throw Error("Не найден ONNX Runtime для точного выравнивания");
        using ApiBase = const OrtApiBase*(ORT_API_CALL*)();
        auto getApi = reinterpret_cast<ApiBase>(library.resolve("OrtGetApiBase"));
        if (!getApi || !(api = getApi()->GetApi(ORT_API_VERSION)))
            throw Error("Недоступен ONNX API");
        try {
            check(api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "SonicForge alignment", &environment));
            check(api->CreateSessionOptions(&options));
            check(api->SetIntraOpNumThreads(options, 2));
            check(api->SetInterOpNumThreads(options, 1));
            check(api->DisableCpuMemArena(options));
            check(api->DisableMemPattern(options));
            QString modelPath = path;
            if (!QFileInfo::exists(modelPath)) modelPath = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/models/" + QFileInfo(path).fileName();
            check(api->CreateSession(environment, reinterpret_cast<const wchar_t*>(modelPath.utf16()),
                                     options, &session));
            check(api->CreateCpuMemoryInfo(OrtDeviceAllocator, OrtMemTypeDefault, &memory));
            OrtAllocator* allocator = nullptr;
            check(api->GetAllocatorWithDefaultOptions(&allocator));
            size_t count = 0;
            check(api->SessionGetInputCount(session, &count));
            for (size_t i = 0; i < count; ++i) {
                char* name = nullptr;
                check(api->SessionGetInputName(session, i, allocator, &name));
                names << QByteArray(name);
                allocator->Free(allocator, name);
            }
            char* name = nullptr;
            check(api->SessionGetOutputName(session, 0, allocator, &name));
            outputName = name;
            allocator->Free(allocator, name);
            QFile vocab(":/ctc-" + lang + ".json");
            if (!vocab.open(QIODevice::ReadOnly))
                throw Error("Не найден словарь выравнивания");
            vocabulary = QJsonDocument::fromJson(vocab.readAll()).object();
        } catch (...) {
            release();
            throw;
        }
    }
    void release() {
        if (session)
            api->ReleaseSession(session);
        session = nullptr;
        if (memory)
            api->ReleaseMemoryInfo(memory);
        memory = nullptr;
        if (options)
            api->ReleaseSessionOptions(options);
        options = nullptr;
        if (environment)
            api->ReleaseEnv(environment);
        environment = nullptr;
    }
    ~CtcEngine() {
        release();
    }
    CtcEmission infer(QVector<float> audio) {
        if (audio.size() < 1600) return {};
        double mean = 0, variance = 0;
        for (float value : audio)
            mean += value;
        mean /= audio.size();
        for (float value : audio)
            variance += (value - mean) * (value - mean);
        double deviation = std::sqrt(variance / audio.size() + 1e-7);
        if (deviation < .0004)
            return {};
        for (float& value : audio)
            value = float((value - mean) / deviation);
        int64_t shape[]{1, audio.size()};
        QVector<int64_t> mask(audio.size(), 1);
        std::vector<OrtValue*> values(names.size(), nullptr);
        OrtValue* output = nullptr;
        auto cleanup = qScopeGuard([&] {
            for (auto* value : values)
                if (value)
                    api->ReleaseValue(value);
            if (output)
                api->ReleaseValue(output);
        });
        QVector<const char*> inputs;
        for (int i = 0; i < names.size(); ++i) {
            inputs << names[i].constData();
            if (names[i] == "attention_mask")
                check(api->CreateTensorWithDataAsOrtValue(
                    memory, mask.data(), mask.size() * sizeof(int64_t), shape, 2,
                    ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &values[i]));
            else
                check(api->CreateTensorWithDataAsOrtValue(
                    memory, audio.data(), audio.size() * sizeof(float), shape, 2,
                    ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &values[i]));
        }
        const char* outName = outputName.constData();
        std::vector<const OrtValue*> inputValues(values.begin(), values.end());
        check(api->Run(session, nullptr, inputs.constData(), inputValues.data(), inputValues.size(),
                       &outName, 1, &output));
        OrtTensorTypeAndShapeInfo* info = nullptr;
        check(api->GetTensorTypeAndShape(output, &info));
        auto releaseInfo = qScopeGuard([&] { api->ReleaseTensorTypeAndShapeInfo(info); });
        size_t rank = 0;
        check(api->GetDimensionsCount(info, &rank));
        QVector<int64_t> dimensions(rank);
        check(api->GetDimensions(info, dimensions.data(), rank));
        if (rank != 3 || dimensions[0] != 1 || dimensions[2] != vocabulary.size())
            throw Error("Неверная размерность CTC-модели");
        int frames = int(dimensions[1]), classes = int(dimensions[2]);
        float* data = nullptr;
        check(api->GetTensorMutableData(output, reinterpret_cast<void**>(&data)));
        if (qEnvironmentVariableIsSet("SF_TRACE_ALIGNMENT")) {
            QString greedy;
            int previous = -1;
            for (int t = 0; t < frames; ++t) {
                int best = int(std::max_element(data + t * classes, data + (t + 1) * classes) -
                               (data + t * classes));
                if (best && best != previous)
                    for (auto key = vocabulary.begin(); key != vocabulary.end(); ++key)
                        if (key.value().toInt() == best)
                            greedy += key.key();
                previous = best;
            }
            std::cerr << "CTC greedy: " << greedy.toUtf8().constData() << std::endl;
        }
        QVector<float> probabilities(frames * classes);
        for (int t = 0; t < frames; ++t) {
            float maximum = *std::max_element(data + t * classes, data + (t + 1) * classes);
            double sum = 0;
            for (int k = 0; k < classes; ++k)
                sum += std::exp(data[t * classes + k] - maximum);
            double normalizer = maximum + std::log(sum);
            for (int k = 0; k < classes; ++k)
                probabilities[t * classes + k] = float(data[t * classes + k] - normalizer);
        }
        return {std::move(probabilities), frames, classes};
    }
    std::optional<Lyric> align(QVector<float> audio, const QString& text, double origin,
                               bool preserveText, bool splitSilence = true) {
        if (splitSilence) {
            QVector<QPair<int, int>> regions;
            int first = -1, last = -1;
            for (int at = 0; at < audio.size(); at += 160) {
                double energy = 0;
                const int end = qMin(at + 160, int(audio.size()));
                for (int sample = at; sample < end; ++sample)
                    energy += double(audio[sample]) * audio[sample];
                if (energy / qMax(1, end - at) <= 1e-10)
                    continue;
                if (first >= 0 && at - last > 32000) {
                    regions << qMakePair(qMax(0, first - 2400),
                                         qMin(int(audio.size()), last + 2560));
                    first = -1;
                }
                if (first < 0)
                    first = at;
                last = at;
            }
            if (first < 0)
                return {};
            regions << qMakePair(qMax(0, first - 2400), qMin(int(audio.size()), last + 2560));
            if (regions.size() > 1 || regions[0].second - regions[0].first < audio.size() - 16000) {
                std::optional<Lyric> best;
                for (const auto& region : regions) {
                    auto candidate =
                        align(audio.mid(region.first, region.second - region.first), text,
                              origin + region.first / 16000., preserveText, false);
                    if (candidate && (!best || candidate->confidence > best->confidence))
                        best = candidate;
                }
                if (best && best->confidence > .65)
                    return best;
            }
        }
        QVector<int> tokens, tokenWords;
        const auto originalWords = text.split(QRegularExpression("\\s+"), Qt::SkipEmptyParts);
        for (int word = 0; word < originalWords.size(); ++word) {
            const auto input =
                language == "en" ? originalWords[word].toUpper() : originalWords[word].toLower();
            for (auto character : input)
                if (character.isLetterOrNumber() && !vocabulary.contains(QString(character)))
                    return {}; // Preserve mixed-language words and written numbers.
            if (!tokens.isEmpty()) {
                tokens << vocabulary["|"].toInt();
                tokenWords << -1;
            }
            for (auto character : input) {
                QString key(character);
                if (!vocabulary.contains(key))
                    continue;
                tokens << vocabulary[key].toInt();
                tokenWords << word;
            }
        }
        if (audio.size() < 1600 || tokens.isEmpty() || tokens.size() > 800)
            return {};
        auto emission = infer(std::move(audio));
        auto match = ctcViterbi(emission.probabilities, emission.frames, emission.classes, tokens);
        if (!match)
            return {};
        QVector<double> certainty(originalWords.size(), 0), coverage(originalWords.size(), 0);
        QVector<int> counts(originalWords.size(), 0);
        for (int i = 0; i < tokens.size(); ++i)
            if (tokenWords[i] >= 0) {
                const int word = tokenWords[i];
                certainty[word] += match->tokenConfidence[i];
                coverage[word] += match->tokenConfidence[i] >= .12;
                ++counts[word];
            }
        int confirmed = 0;
        for (int i = 0; i < counts.size(); ++i) {
            certainty[i] /= qMax(1, counts[i]);
            coverage[i] /= qMax(1, counts[i]);
            confirmed += certainty[i] > .65 && coverage[i] > .7;
            if (qEnvironmentVariableIsSet("SF_TRACE_ALIGNMENT"))
                std::cerr << "CTC " << originalWords[i].toUtf8().constData()
                          << " score=" << certainty[i] << " coverage=" << coverage[i] << std::endl;
        }
        int firstWord = 0, lastWord = originalWords.size() - 1;
        if (!preserveText && confirmed >= 3) {
            while (firstWord < lastWord && certainty[firstWord] < .2 && coverage[firstWord] < .45)
                ++firstWord;
            while (lastWord > firstWord && certainty[lastWord] < .2 && coverage[lastWord] < .45)
                --lastWord;
        }
        int firstToken = 0, lastToken = tokens.size() - 1;
        while (firstToken < tokens.size() && tokenWords[firstToken] != firstWord)
            ++firstToken;
        while (lastToken >= 0 && tokenWords[lastToken] != lastWord)
            --lastToken;
        if (firstToken > lastToken)
            return {};
        double confidence = 0, supported = 0;
        for (int i = firstToken; i <= lastToken; ++i) {
            confidence += match->tokenConfidence[i];
            supported += match->tokenConfidence[i] >= .12;
        }
        confidence /= lastToken - firstToken + 1;
        supported /= lastToken - firstToken + 1;
        if (confidence < .12 || supported < .45)
            return {};
        const QString resultText =
            preserveText ? text : originalWords.mid(firstWord, lastWord - firstWord + 1).join(' ');
        // Wav2Vec2 uses 320-sample stride and a 400-sample receptive field at 16 kHz.
        return Lyric{qMax(0., origin + match->first[firstToken] * .02 - LyricLead),
                     origin + match->last[lastToken] * .02 + .025, resultText, confidence};
    }
};
QString textLanguage(const QString& text) {
    int russian = 0, english = 0;
    for (auto ch : text) {
        if ((ch.unicode() >= 0x410 && ch.unicode() <= 0x44f) || ch == QChar(0x451) ||
            ch == QChar(0x401))
            ++russian;
        else if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z'))
            ++english;
    }
    if (russian >= 2 && russian > english * 2)
        return "ru";
    if (english >= 2 && english > russian * 2)
        return "en";
    return {};
}
} // namespace
QString directAlignmentLanguage(const QString& text) {
    const auto plain = plainLyrics(text);
    const auto language = textLanguage(plain);
    if (language.isEmpty()) return {};
    QFile file(":/ctc-" + language + ".json");
    if (!file.open(QIODevice::ReadOnly)) return {};
    const auto vocabulary = QJsonDocument::fromJson(file.readAll()).object();
    const auto normalized = language == "en" ? plain.toUpper() : plain.toLower();
    for (auto character : normalized)
        if (character.isLetterOrNumber() && !vocabulary.contains(QString(character))) return {};
    return language;
}
QList<Lyric> alignSuppliedLyrics(const QString& audio, const QString& text, const QString& directory,
                                const QString& reference) {
    const auto language = directAlignmentLanguage(text);
    if (language.isEmpty()) throw Error("Для прямого выравнивания нужен русский или английский текст");
    const auto supplied = plainLyrics(text).split('\n', Qt::SkipEmptyParts);
    const auto anchors = parseLyrics(text, false);
    if (!anchors.isEmpty() && anchors.size() == supplied.size())
        return refineSpeechTiming(audio, anchors, directory, reference, true);
    QFile file(":/ctc-" + language + ".json");
    if (!file.open(QIODevice::ReadOnly)) throw Error("Не найден словарь выравнивания");
    const auto vocabulary = QJsonDocument::fromJson(file.readAll()).object();
    QVector<int> tokens;
    QVector<QPair<int,int>> ranges;
    for (const auto& line : supplied) {
        if (!tokens.isEmpty()) tokens << vocabulary["|"].toInt();
        const int first = tokens.size();
        auto normalized = language == "en" ? line.toUpper() : line.toLower();
        bool space = false;
        for (auto character : normalized) {
            if (character.isSpace()) { space = tokens.size() > first; continue; }
            const auto key = QString(character);
            if (!vocabulary.contains(key)) continue;
            if (space) { tokens << vocabulary["|"].toInt(); space = false; }
            tokens << vocabulary[key].toInt();
        }
        if (tokens.size() == first) throw Error("Строка не содержит слов для выравнивания");
        ranges << qMakePair(first, int(tokens.size()) - 1);
    }
    const auto source = readSource(audio, {}, false);
    const int frames = qCeil(source.duration / .02), classes = vocabulary.size();

    std::cerr << "stage=Загрузка модели выравнивания\nprogress=0" << std::endl;
    CtcEngine engine(directory + "/ctc-" + language + ".onnx", language);
    QTemporaryFile emissions(cacheDirectory() + "/ctc-emissions-XXXXXX.bin");
    if (!emissions.open()) throw Error(emissions.errorString());
    QVector<float> emptyFrame(classes, -30.f); emptyFrame[0] = 0;
    QByteArray emptyBlock;
    for (int frame = 0; frame < 512; ++frame) emptyBlock.append(reinterpret_cast<const char*>(emptyFrame.constData()), classes * sizeof(float));
    for (int frame = 0; frame < frames; frame += 512) {
        const auto bytes = qMin(512, frames - frame) * classes * qint64(sizeof(float));
        if (emissions.write(emptyBlock.constData(), bytes) != bytes) throw Error(emissions.errorString());
    }
    constexpr double blockSeconds = 12, contextSeconds = 1;
    const int blocks = qCeil(source.duration / blockSeconds);
    for (int block = 0; block < blocks; ++block) {
        const double at = block * blockSeconds, begin = qMax(0., at - contextSeconds);
        const double end = qMin(source.duration, at + blockSeconds + contextSeconds);
        std::cerr << "stage=" << QString("Выравнивание: анализ звука %1/%2").arg(block+1).arg(blocks).toUtf8().constData()
                  << "\nprogress=" << .85 * block / blocks << std::endl;
        auto emission = engine.infer(decode(audio, 16000, 1, begin, end - begin));
        if (!emission.frames) continue;
        if (emission.classes != classes) throw Error("Неверный словарь выравнивания");
        const int first = qRound(at / .02), last = qMin(frames, qRound((at + blockSeconds) / .02));
        for (int frame = first; frame < last; ++frame) {
            const int local = frame - qRound(begin / .02);
            if (local < emission.frames) {
                if (!emissions.seek(qint64(frame) * classes * sizeof(float)) ||
                    emissions.write(reinterpret_cast<const char*>(emission.probabilities.constData() + local * classes), classes * sizeof(float)) != qint64(classes * sizeof(float))) throw Error(emissions.errorString());
            }
        }
    }
    std::cerr << "stage=Сопоставление строк с музыкой\nprogress=0.85" << std::endl;
    emissions.flush();
    auto* mapped = emissions.map(0, qint64(frames) * classes * sizeof(float));
    if (!mapped) throw Error("Не удалось отобразить данные выравнивания");
    auto unmap = qScopeGuard([&] { emissions.unmap(mapped); });
    const auto match = ctcViterbiView(reinterpret_cast<const float*>(mapped), qsizetype(frames) * classes, frames, classes, tokens, 0);
    if (!match) throw Error("Не удалось сопоставить текст со звуком. Исходный текст сохранён.");
    QList<Lyric> result;
    for (int line = 0; line < ranges.size(); ++line) {
        const auto [first,last] = ranges[line];
        double certainty = 0, coverage = 0;
        for (int token = first; token <= last; ++token) {
            certainty += match->tokenConfidence[token];
            coverage += match->tokenConfidence[token] >= .12;
        }
        certainty /= last - first + 1; coverage /= last - first + 1;
        if (qEnvironmentVariableIsSet("SF_TRACE_ALIGNMENT"))
            std::cerr << "line=" << line+1 << " confidence=" << certainty << " coverage=" << coverage << std::endl;
        Lyric value{qMax(0., match->first[first] * .02 - LyricLead),
                    qMin(source.duration, match->last[last] * .02 + .025), supplied[line].trimmed(), certainty};
        if (certainty < .12 || coverage < .45) {
            // Recheck only the uncertain row, constrained by its neighbours.
            // The separated stem can lose a short syllable that remains in the mix.
            std::cerr << "stage=" << QString("Проверяю строку %1/%2").arg(line+1).arg(ranges.size()).toUtf8().constData()
                      << "\nprogress=" << .85 + .15 * line / ranges.size() << std::endl;
            const double begin = result.isEmpty() ? 0 : qMax(0., result.last().end - .12);
            const double end = line + 1 < ranges.size()
                                   ? qMin(source.duration, match->first[ranges[line+1].first] * .02 + .12)
                                   : source.duration;
            std::optional<Lyric> confirmed;
            for (double at = begin; at < end; at += 20) {
                const auto length = qMin(24., end-at);
                auto candidate = engine.align(decode(audio, 16000, 1, at, length), value.text, at, true);
                if (!reference.isEmpty() && reference != audio && (!candidate || candidate->confidence < .45)) {
                    auto alternative = engine.align(decode(reference, 16000, 1, at, length), value.text, at, true);
                    if (alternative && (!candidate || alternative->confidence > candidate->confidence)) candidate = alternative;
                }
                if (candidate && (!confirmed || candidate->confidence > confirmed->confidence)) confirmed = candidate;
            }
            if (!confirmed)
                throw Error(QString("Не удалось подтвердить строку %1 по звуку. Исходный текст сохранён; проверьте соответствие текста песне.").arg(line+1));
            value = *confirmed;
        }
        result << value;
    }
    std::cerr << "progress=1" << std::endl;
    return result;
}
QList<Lyric> refineSpeechTiming(const QString& audio, QList<Lyric> lines, const QString& directory,
                                const QString& reference, bool preserveText) {
    if (lines.isEmpty())
        return lines;
    const auto source = readSource(audio);
    std::unique_ptr<CtcEngine> engine;
    const auto rough = lines;
    for (int i = 0; i < lines.size(); ++i) {
        std::cerr << "progress=" << .8 + .2 * double(i) / lines.size() << std::endl;
        auto lang = textLanguage(lines[i].text);
        const auto path = directory + "/ctc-" + lang + ".onnx";
        if (lang.isEmpty() || !QFileInfo(path).isFile())
            continue;
        if (!engine || engine->language != lang) {
            engine.reset();
            engine = std::make_unique<CtcEngine>(path, lang);
        }
        const bool missing = rough[i].start < 0 || rough[i].confidence <= 0;
        double begin = missing ? 0 : qMax(0., rough[i].start - 2.5);
        double end = missing ? source.duration
                             : qMin(source.duration, qMax(rough[i].end + 2, rough[i].start + 5));
        if (i > 0)
            begin = qMax(begin, missing ? lines[i - 1].end - .08 : lines[i - 1].start + .1);
        for (int j = i + 1; j < rough.size(); ++j)
            if (rough[j].start >= 0 && rough[j].confidence > 0) {
                end = qMin(end, qMax(rough[j].start + .1, rough[i].end));
                break;
            }
        if (end <= begin)
            continue;
        std::optional<Lyric> match;
        for (double at = begin; at < end; at += 20) {
            double length = qMin(24., end - at);
            auto candidate =
                engine->align(decode(audio, 16000, 1, at, length), lines[i].text, at, preserveText);
            if (!reference.isEmpty() && QFileInfo(reference).isFile() &&
                (!candidate || candidate->confidence < .45)) {
                auto alternative = engine->align(decode(reference, 16000, 1, at, length),
                                                 lines[i].text, at, preserveText);
                if (alternative &&
                    (!candidate || alternative->confidence > candidate->confidence + .08))
                    candidate = alternative;
            }
            if (candidate && (!match || candidate->confidence > match->confidence))
                match = candidate;
            if (!missing || (match && match->confidence > .65))
                break;
        }
        if (match && (i == 0 || match->start > lines[i - 1].start))
            lines[i] = *match;
        if (!preserveText && (!match || match->confidence < .25)) {
            static const QRegularExpression annotation("(субтитр|корректор|subtitles|captioned)|^"
                                                       "\\s*(музыка|песня|music|instrumental)\\s*$",
                                                       QRegularExpression::CaseInsensitiveOption);
            if (annotation.match(lines[i].text).hasMatch())
                lines[i].text.clear();
        }
    }
    lines.removeIf([](const Lyric& line) { return line.text.trimmed().isEmpty(); });
    return lines;
}
} // namespace sf
