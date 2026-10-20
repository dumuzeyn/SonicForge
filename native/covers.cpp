#include "core.h"
#include <algorithm>
#include <cmath>
#include <numbers>
namespace sf {
QImage restoredTexture(const QString&, const CoverOptions&, const Cancel&);
static QImage blur(QImage input, int radius) {
    if (radius <= 0)
        return input;
    QImage work(input.size(), QImage::Format_RGB32), out(input.size(), QImage::Format_RGB32);
    int width = input.width(), height = input.height();
    for (int y = 0; y < height; ++y) {
        auto* dst = reinterpret_cast<QRgb*>(work.scanLine(y));
        auto* src = reinterpret_cast<const QRgb*>(input.constScanLine(y));
        qint64 r = 0, g = 0, b = 0;
        for (int x = -radius; x <= radius; ++x) {
            QRgb v = src[qBound(0, x, width - 1)];
            r += qRed(v);
            g += qGreen(v);
            b += qBlue(v);
        }
        int count = radius * 2 + 1;
        for (int x = 0; x < width; ++x) {
            dst[x] = qRgb(r / count, g / count, b / count);
            QRgb left = src[qBound(0, x - radius, width - 1)],
                 right = src[qBound(0, x + radius + 1, width - 1)];
            r += qRed(right) - qRed(left);
            g += qGreen(right) - qGreen(left);
            b += qBlue(right) - qBlue(left);
        }
    }
    for (int x = 0; x < width; ++x) {
        qint64 r = 0, g = 0, b = 0;
        for (int y = -radius; y <= radius; ++y) {
            QRgb v = work.pixel(x, qBound(0, y, height - 1));
            r += qRed(v);
            g += qGreen(v);
            b += qBlue(v);
        }
        int count = radius * 2 + 1;
        for (int y = 0; y < height; ++y) {
            out.setPixel(x, y, qRgb(r / count, g / count, b / count));
            QRgb top = work.pixel(x, qBound(0, y - radius, height - 1)),
                 bottom = work.pixel(x, qBound(0, y + radius + 1, height - 1));
            r += qRed(bottom) - qRed(top);
            g += qGreen(bottom) - qGreen(top);
            b += qBlue(bottom) - qBlue(top);
        }
    }
    return out;
}
QImage makeCover(const QString& audio, const Metadata& metadata, const CoverOptions& options,
                 const Cancel& cancel) {
    if (options.size < 128 || options.size > 4096)
        throw Error("Размер обложки: от 128 до 4096 пикселей");
    QImage image = restoredTexture(audio, options, cancel);
    image = blur(std::move(image), qRound(options.softness * qMin(options.size, 640) / 9000.));
    image =
        image.scaled(options.size, options.size, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
    if (image.isNull())
        throw Error("Недостаточно памяти для обложки. Уменьшите размер изображения.");
    int size = options.size;
    auto digest = QCryptographicHash::hash(metadata.values.value("title").toUtf8() +
                                               QByteArray::number(options.seed),
                                           QCryptographicHash::Sha256);
    QRandomGenerator random(qFromLittleEndian<quint32>(digest.constData()));
    QPainter painter(&image);
    painter.setRenderHints(QPainter::Antialiasing | QPainter::TextAntialiasing |
                           QPainter::SmoothPixmapTransform);
    if (options.symbol) {
        painter.setCompositionMode(QPainter::CompositionMode_Screen);
        QPainterPath gesture;
        double centerX = size * (.47 + random.generateDouble() * .08), centerY = size * .35;
        gesture.moveTo(centerX - size * .22, centerY + size * .11);
        gesture.cubicTo(centerX - size * .04, centerY - size * .27, centerX + size * .08,
                        centerY + size * .24, centerX + size * .23, centerY - size * .1);
        QPen pen(QColor(255, 235, 206, 100), size * .008, Qt::SolidLine, Qt::RoundCap);
        painter.setPen(pen);
        painter.drawPath(gesture);
        pen.setColor(QColor(255, 244, 222, 180));
        pen.setWidthF(size * .002);
        painter.setPen(pen);
        painter.drawPath(gesture);
    }
    painter.setCompositionMode(QPainter::CompositionMode_SourceOver);
    QString title = metadata.values.value("title", QFileInfo(audio).completeBaseName());
    if (title.isEmpty())
        title = QFileInfo(audio).completeBaseName();
    title.remove(QRegularExpression("\\s*\\[[A-Za-z0-9_-]{8,}\\]"));
    QString artist = metadata.values.value("artist");
    QStringList text;
    if (options.title)
        text << title;
    if (options.artist && !artist.isEmpty())
        text << artist;
    if (!text.isEmpty()) {
        QLinearGradient shade(0, size * .5, 0, size);
        shade.setColorAt(0, QColor(0, 0, 0, 0));
        shade.setColorAt(.65, QColor(0, 0, 0, 155));
        shade.setColorAt(1, QColor(0, 0, 0, 205));
        painter.fillRect(QRectF(0, size * .45, size, size * .55), shade);
        double left = size * .075, width = size * .85, y = size * .64;
        QFont font("Unbounded");
        font.setWeight(QFont::DemiBold);
        int pixels = qRound(size * .072);
        QString headline = text.first();
        for (; pixels > size * .025; --pixels) {
            font.setPixelSize(pixels);
            QFontMetrics metrics(font);
            auto rect =
                metrics.boundingRect(QRect(0, 0, int(width), size), Qt::TextWordWrap, headline);
            if (rect.height() <= size * .235)
                break;
        }
        font.setPixelSize(pixels);
        painter.setFont(font);
        painter.setPen(QColor(252, 250, 247));
        QRectF bounds(left, y, width, size * .25);
        painter.drawText(bounds, Qt::AlignLeft | Qt::AlignVCenter | Qt::TextWordWrap, headline);
        if (text.size() > 1) {
            QFont second("Noto Sans");
            second.setPixelSize(qRound(size * .029));
            second.setLetterSpacing(QFont::AbsoluteSpacing, size * .001);
            painter.setFont(second);
            painter.setPen(QColor(245, 235, 229, 220));
            painter.drawText(
                QRectF(left, size * .9, width, size * .055), Qt::AlignLeft | Qt::AlignVCenter,
                QFontMetrics(second).elidedText(text.last(), Qt::ElideRight, int(width)));
        }
    }
    painter.end();
    checkpoint(cancel);
    return image;
}
} // namespace sf
