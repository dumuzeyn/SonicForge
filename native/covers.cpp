#include "core.h"
#include <algorithm>
#include <cmath>
#include <numbers>
namespace sf {
static double mix(double a, double b, double t) {
    return a + (b - a) * t;
}
static QColor blend(const QColor& a, const QColor& b, double t) {
    return QColor::fromRgbF(mix(a.redF(), b.redF(), t), mix(a.greenF(), b.greenF(), t),
                            mix(a.blueF(), b.blueF(), t));
}
static QColor paletteColor(const QList<QColor>& colors, const QList<double>& positions, double at) {
    at = qBound(0., at, 1.);
    if (colors.size() == 1)
        return colors.first();
    for (int i = 1; i < colors.size(); ++i) {
        double left = positions.value(i - 1, double(i - 1) / (colors.size() - 1)),
               right = positions.value(i, double(i) / (colors.size() - 1));
        if (at <= right) {
            double t = right > left ? qBound(0., (at - left) / (right - left), 1.) : 1;
            return blend(colors[i - 1], colors[i], t);
        }
    }
    return colors.last();
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
QImage makeCover(const QString& audio, const Metadata& metadata, const CoverOptions& options,
                 const Cancel& cancel) {
    if (options.size < 128 || options.size > 4096)
        throw Error("Размер обложки: от 128 до 4096 пикселей");
    auto samples = decode(audio, 4000, 1, 0, 120, cancel);
    if (samples.isEmpty())
        throw Error("В аудио нет звука");
    QVector<double> activity(600), low(600);
    double total = 0, changes = 0;
    for (int i = 0; i < 600; ++i) {
        qsizetype begin = i * samples.size() / 600, end = (i + 1) * samples.size() / 600;
        double energy = 0, previous = 0;
        for (qsizetype j = begin; j < end; ++j) {
            double value = samples[j];
            energy += value * value;
            changes += std::abs(value - previous);
            previous = value;
        }
        activity[i] = std::sqrt(energy / qMax(qsizetype(1), end - begin));
        total += activity[i];
    }
    double max = *std::max_element(activity.begin(), activity.end());
    for (auto& x : activity)
        x /= qMax(.0001, max);
    for (int i = 0; i < 600; ++i) {
        double sum = 0;
        int count = 0;
        for (int j = qMax(0, i - 8); j <= qMin(599, i + 8); ++j) {
            sum += activity[j];
            count++;
        }
        low[i] = sum / count;
    }
    quint32 hash = qHash(QFileInfo(audio).completeBaseName());
    for (qsizetype i = 0; i < samples.size(); i += qMax(qsizetype(1), samples.size() / 300))
        hash = hash * 16777619u ^ quint32((samples[i] + 1) * 32768);
    QRandomGenerator random(hash ^ quint32(options.seed));
    double phase = random.generateDouble() * 6.28318530718;
    double brightness = total / 600, edge = changes / qMax(qsizetype(1), samples.size());
    QList<QColor> colors = options.palette;
    QList<double> stops = options.stops;
    if (options.colorSource != 3) {
        double hue = options.colorSource == 2 ? std::fmod(240 + edge * 800 + brightness * 70, 360.)
                     : options.colorSource == 1 ? std::fmod(260 + phase * 35, 360.)
                                                : std::fmod(195 + phase * 20, 360.);
        colors = {QColor::fromHslF(std::fmod(hue / 360 + .2, 1.), .55, .12),
                  QColor::fromHslF(hue / 360, .65, .45),
                  QColor::fromHslF(std::fmod(hue / 360 + .38, 1.), .85, .72)};
        stops = {0, .58, 1};
    }
    if (colors.isEmpty())
        colors = {QColor("#30206d"), QColor("#f9a46a")};
    QImage image(options.size, options.size, QImage::Format_RGB32);
    int size = options.size;
    double detail = options.detail / 100., contrast = options.contrast / 100.;
    for (int y = 0; y < size; ++y) {
        checkpoint(cancel);
        auto* pixels = reinterpret_cast<QRgb*>(image.scanLine(y));
        double py = (y + .5) / size;
        for (int x = 0; x < size; ++x) {
            double px = (x + .5) / size;
            int index = qBound(0, int(px * 599), 599);
            double amp = low[index], u = px - .5, v = py - .5;
            double value = 0;
            if (options.pattern == 0) {
                double r = std::hypot(u, v), angle = std::atan2(v, u);
                double warp = std::sin(angle * 3 + phase) * .16 + std::sin(v * 12 + phase) * .06;
                value = .5 + .26 * std::sin((r + warp) * (13 + detail * 22) - phase) +
                        .16 * std::sin(u * 8 + v * 5 + phase);
            } else if (options.pattern == 1) {
                double bend = u + std::sin(v * 5 + phase) * .2 + std::sin(v * 11 - phase) * .04;
                double fold = std::sin(bend * (16 + detail * 26) + std::sin(v * 8) * 1.5);
                value =
                    .43 + .26 * fold + .16 * std::sin(v * 5 + phase) + .12 * std::cos((u - v) * 6);
            } else {
                double horizontal =
                    px + .028 * std::sin(py * 5 + phase) + .012 * std::sin(py * 11 + px * 3);
                double frequency = 11 + amp * 9 + detail * 10;
                double fold =
                    std::sin(horizontal * frequency + std::sin(py * 6 + phase) * 1.5 + py * 2);
                double ridge = std::exp(
                    -std::pow((py - .48 - .12 * std::sin(px * 5 + phase)) * (3 + amp * 3), 2));
                value = .28 + .2 * fold + .28 * ridge + .16 * amp;
            }
            double vignette = 1 - .3 * std::pow(std::hypot(u, v) / .71, 1.7);
            value = qBound(0., ((value - .5) * contrast + .5) * vignette, 1.);
            QColor color = paletteColor(colors, stops, value);
            float h, s, l, a;
            color.getHslF(&h, &s, &l, &a);
            color = QColor::fromHslF(h, qBound(0., s * options.saturation / 100., 1.), l);
            pixels[x] = color.rgb();
        }
    }
    image = blur(std::move(image), qRound(options.softness * size / 9000.));
    QPainter painter(&image);
    painter.setRenderHints(QPainter::Antialiasing | QPainter::TextAntialiasing |
                           QPainter::SmoothPixmapTransform);
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
