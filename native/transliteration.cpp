#include "core.h"
#include <algorithm>
namespace sf {
QString soundSpelling(const QString& original, const QString& alphabet, const QString& language) {
    QFile file(":/transliteration.json");
    if (!file.open(QIODevice::ReadOnly))
        throw Error("Не найдены данные фонетической записи");
    const auto data = QJsonDocument::fromJson(file.readAll()).object();
    if (alphabet == "ru" && language == "ka") {
        auto mapping = data["ka"].toObject();
        QString result;
        for (auto ch : original)
            result += mapping.value(QString(ch).toLower()).toString(QString(ch));
        return result;
    }
    QString text = original;
    if (language == "es") {
        text.replace("ñ", "ny");
        text.replace("Ñ", "Ny");
    }
    const auto blocks = data["blocks"].toObject();
    QHash<uint, QStringList> cache;
    QString latin;
    for (char32_t point : text.toUcs4()) {
        if (point < 128) {
            latin += QChar(ushort(point));
            continue;
        }
        uint block = uint(point) >> 8;
        if (!cache.contains(block))
            cache[block] =
                blocks[QString::number(block, 16).rightJustified(3, '0')].toString().split('\t');
        latin += cache[block].value(uint(point) & 255);
    }
    if (alphabet == "en")
        return latin;
    using Rules = QList<QPair<QString, QString>>;
    const QMap<QString, Rules> rules{
        {"es",
         {{"h", ""},
          {"ll", "й"},
          {"ny", "нь"},
          {"j", "х"},
          {"g(?=[ei])", "х"},
          {"c(?=[ei])", "с"},
          {"z", "с"},
          {"qu(?=[ei])", "к"}}},
        {"de",
         {{"tsch", "ч"},
          {"sch", "ш"},
          {"ch", "х"},
          {"z", "ц"},
          {"w", "в"},
          {"j", "й"},
          {"v", "ф"},
          {"ei", "ай"}}},
        {"it",
         {{"gli(?=[aeou])", "ль"},
          {"gn", "нь"},
          {"ch(?=[ei])", "к"},
          {"c(?=[ei])", "ч"},
          {"g(?=[ei])", "дж"},
          {"qu", "ку"}}},
        {"fr",
         {{"eaux?\\b", "о"},
          {"ou", "у"},
          {"oi", "уа"},
          {"ch", "ш"},
          {"j", "ж"},
          {"g(?=[ei])", "ж"},
          {"h", ""}}},
        {"pt",
         {{"nh", "нь"}, {"lh", "ль"}, {"ch", "ш"}, {"j", "ж"}, {"h", ""}, {"qu(?=[ei])", "к"}}}};
    for (const auto& rule : rules.value(language))
        latin.replace(QRegularExpression(rule.first, QRegularExpression::CaseInsensitiveOption),
                      rule.second);
    auto mapping = data["ru"].toObject();
    auto keys = mapping.keys();
    std::sort(keys.begin(), keys.end(),
              [](const QString& a, const QString& b) { return a.size() > b.size(); });
    QString result;
    for (qsizetype at = 0; at < latin.size();) {
        bool found = false;
        for (const auto& key : keys) {
            if (latin.mid(at, key.size()).compare(key, Qt::CaseInsensitive) == 0) {
                QString value = mapping[key].toString();
                if (latin[at].isUpper() && !value.isEmpty())
                    value[0] = value[0].toUpper();
                result += value;
                at += key.size();
                found = true;
                break;
            }
        }
        if (!found)
            result += latin[at++];
    }
    return result;
}
} // namespace sf
