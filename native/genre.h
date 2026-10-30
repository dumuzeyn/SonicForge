#pragma once
#include <QtCore>
#include <algorithm>
#include <cmath>

namespace sf {
struct GenrePrediction {
    QString name;
    double score;
};
inline QList<GenrePrediction> rankedGenres(const QJsonArray& labels, const QVector<double>& scores) {
    static const QSet<QString> allowed{
        "rock", "pop", "alternative", "indie", "electronic", "dance", "alternative rock",
        "jazz", "metal", "chillout", "classic rock", "soul", "indie rock", "electronica",
        "folk", "punk", "blues", "hard rock", "ambient", "acoustic", "experimental",
        "hip-hop", "country", "easy listening", "funk", "electro", "heavy metal",
        "progressive rock", "rnb", "indie pop", "house"};
    QList<GenrePrediction> result;
    for (int i = 0; i < qMin(labels.size(), scores.size()); ++i) {
        auto name = labels[i].toString().toLower();
        if (!allowed.contains(name) || !std::isfinite(scores[i])) continue;
        name = name == "rnb" ? "R&B" : name;
        for (int j = 0; j < name.size(); ++j)
            if (j == 0 || name[j - 1] == ' ' || name[j - 1] == '-') name[j] = name[j].toUpper();
        result << GenrePrediction{name, scores[i]};
    }
    // Preserve model label order for equal scores, including silent input.
    std::stable_sort(result.begin(), result.end(), [](const auto& a, const auto& b) { return a.score > b.score; });
    return result;
}
} // namespace sf
