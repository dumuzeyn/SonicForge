#pragma once
#include "core.h"
#include <optional>

namespace sf {
struct CtcMatch {
    QVector<int> first, last;
    QVector<float> tokenConfidence;
    double confidence = 0, coverage = 0;
};
std::optional<CtcMatch> ctcViterbi(const QVector<float>& logProbabilities, int frames,
                                   int vocabulary, const QVector<int>& tokens, int blank = 0);
void appendSpeechWindow(QList<Lyric>& target, const QList<Lyric>& words, double begin, double end);
QList<Lyric> speechLines(const QList<Lyric>& words);
QList<Lyric> refineSpeechTiming(const QString& audio, QList<Lyric> lines,
                                const QString& modelDirectory, const QString& reference = {},
                                bool preserveText = true);
} // namespace sf
