#include "core.h"
#include "cover_symbols.h"
#include <algorithm>
#include <cmath>
#include <numbers>
namespace sf {
QImage restoredTexture(const QString&, const CoverOptions&, const Cancel&, QVector<double>*);
Metadata coverMetadata(const QString& audio, const Metadata& metadata) {
    auto result = metadata;
    if (result.values.value("title").trimmed().isEmpty())
        result.values["title"] = QFileInfo(audio).completeBaseName();
    return result;
}
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
CoverArtwork makeCoverArtwork(const QString& audio, const Metadata& metadata, const CoverOptions& options,
                              const Cancel& cancel) {
    if (options.size < 128 || options.size > 4096)
        throw Error("Размер обложки: от 128 до 4096 пикселей");
    QVector<double> music;
    QImage image = restoredTexture(audio, options, cancel, &music);
    image = blur(std::move(image), qRound(options.softness * qMin(options.size, 640) / 9000.));
    image =
        image.scaled(options.size, options.size, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
    if (image.isNull())
        throw Error("Недостаточно памяти для обложки. Уменьшите размер изображения.");
    return {image, coverMetadata(audio, metadata), music};
}
CoverArtwork coverArtworkFromImage(const QImage& image, const Metadata& metadata,
                                   const CoverOptions& options) {
    if (image.isNull())
        throw Error("Не удалось прочитать свою обложку");
    QImage background = image.scaled(options.size, options.size, Qt::KeepAspectRatioByExpanding,
                                     Qt::SmoothTransformation);
    background = background.copy((background.width() - options.size) / 2,
                                  (background.height() - options.size) / 2,
                                  options.size, options.size).convertToFormat(QImage::Format_RGB32);
    auto small = image.scaled(32, 32, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
    auto digest = QCryptographicHash::hash(
        QByteArrayView(reinterpret_cast<const char*>(small.constBits()), small.sizeInBytes()),
        QCryptographicHash::Sha256);
    return {background, metadata, {.4, .4, .3, .4, double(qFromLittleEndian<quint32>(digest.constData()))}};
}
CoverTextLayout layoutCoverText(const Metadata& metadata, const CoverOptions& options) {
    CoverTextLayout layout;
    int size = options.size;
    if (options.title) {
        layout.title = options.text.trimmed().isEmpty() ? metadata.values.value("title") : options.text;
        layout.title.remove(QRegularExpression("\\s*\\[[A-Za-z0-9_-]{8,}\\]"));
    }
    if (options.artist)
        layout.artist = metadata.values.value("artist");
    layout.titleFont = QFont(options.fontFamily);
    layout.titleFont.setStyleStrategy(QFont::StyleStrategy(QFont::PreferAntialias | QFont::NoSubpixelAntialias));
    layout.titleFont.setHintingPreference(QFont::PreferNoHinting);
    layout.titleFont.setWeight(QFont::DemiBold);
    layout.titleFont.setPixelSize(qMax(1, qRound(size * options.textSize / 100)));
    layout.artistFont = QFont(options.fontFamily);
    layout.artistFont.setStyleStrategy(layout.titleFont.styleStrategy());
    layout.artistFont.setHintingPreference(QFont::PreferNoHinting);
    layout.artistFont.setPixelSize(qMax(1, qRound(size * options.textSize / 100 * .45)));
    auto measure = [&](const QString& text, const QFont& font) {
        if (text.isEmpty()) return QSizeF();
        QRectF bounds = QFontMetricsF(font).boundingRect(QRectF(0, 0, size * .9, size * 20),
                                                       Qt::TextWordWrap, text);
        return QSizeF(qMin(size * .9, bounds.width() + 2), bounds.height() + 2);
    };
    QSizeF titleSize = measure(layout.title, layout.titleFont),
           artistSize = measure(layout.artist, layout.artistFont);
    double gap = !layout.title.isEmpty() && !layout.artist.isEmpty() ? size * .015 : 0;
    double width = qMax(titleSize.width(), artistSize.width());
    double height = titleSize.height() + artistSize.height() + gap;
    if (width <= 0 || height <= 0) return layout;
    double x = qBound(0., size * options.textX / 100 - width / 2, qMax(0., size - width)),
           y = qBound(0., size * options.textY / 100 - height / 2, qMax(0., size - height));
    layout.titleBounds = QRectF(x, y, width, titleSize.height());
    layout.artistBounds = QRectF(x, y + titleSize.height() + gap, width, artistSize.height());
    layout.bounds = QRectF(x, y, width, height);
    return layout;
}
QImage decorateCover(const CoverArtwork& artwork, const CoverOptions& options, const Cancel& cancel) {
    checkpoint(cancel);
    QImage image = artwork.background.scaled(options.size, options.size, Qt::IgnoreAspectRatio,
                                             Qt::SmoothTransformation);
    if (image.isNull()) throw Error("Сначала создайте обложку или выберите изображение");
    image = image.convertToFormat(QImage::Format_RGB32);
    const int size = options.size;
    auto colors = coverColors(image);
    if (options.ink.isValid()) {
        QColor ink = options.ink;
        ink.setAlpha(255);
        colors.symbol = colors.title = colors.artist = colors.highlight = ink;
    }
    if (!options.symbol && !options.title && !options.artist) return image;
    // Rasterize lettering and vector edges above the export resolution. Keep the
    // texture untouched, and bound the temporary layer to 4096 pixels per side.
    const int supersampling = qBound(1, 4096 / size, 4);
    QImage decoration(size * supersampling, size * supersampling, QImage::Format_ARGB32_Premultiplied);
    if (decoration.isNull()) throw Error("Недостаточно памяти для оформления обложки");
    decoration.fill(Qt::transparent);
    QPainter painter(&decoration);
    painter.scale(supersampling, supersampling);
    painter.setRenderHints(QPainter::Antialiasing | QPainter::TextAntialiasing |
                           QPainter::SmoothPixmapTransform);
    if (options.symbol)
        paintCoverSymbol(painter, size, artwork.metadata.values.value("title"), artwork.music, colors);
    const auto text = layoutCoverText(artwork.metadata, options);
    QColor shadow = colors.title.lightnessF() > .5 ? QColor(0,0,0,190) : QColor(255,255,255,190);
    auto draw = [&](const QString& value, const QFont& font, const QRectF& bounds) {
        if (value.isEmpty()) return;
        painter.setFont(font);
        painter.setPen(shadow);
        painter.drawText(bounds.translated(size * .0015, size * .002),
                         Qt::AlignHCenter | Qt::AlignTop | Qt::TextWordWrap, value);
        painter.setPen(colors.title);
        painter.drawText(bounds, Qt::AlignHCenter | Qt::AlignTop | Qt::TextWordWrap, value);
    };
    draw(text.title, text.titleFont, text.titleBounds);
    draw(text.artist, text.artistFont, text.artistBounds);
    painter.end();
    checkpoint(cancel);
    if (supersampling > 1)
        decoration = decoration.scaled(size, size, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
    QPainter composite(&image);
    composite.drawImage(0, 0, decoration);
    composite.end();
    return image;
}
QImage makeCover(const QString& audio, const Metadata& metadata, const CoverOptions& options,
                 const Cancel& cancel) {
    return decorateCover(makeCoverArtwork(audio, metadata, options, cancel), options, cancel);
}
} // namespace sf
