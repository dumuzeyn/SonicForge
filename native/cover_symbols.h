#pragma once
#include "core.h"

namespace sf {
QStringList coverSymbolNames();
QString coverSymbolFamily(const QString& title, double drive, double bass, double brightness,
                          quint32 variation = 0);
QPainterPath coverSymbolPath(const QString& family, double drive);
struct CoverColors {
    QColor symbol, highlight, shadow, title, artist;
};
CoverColors coverColors(const QImage& background);
void paintCoverSymbol(QPainter&, int size, const QString& title, const QVector<double>& music,
                      const CoverColors& colors);
}
