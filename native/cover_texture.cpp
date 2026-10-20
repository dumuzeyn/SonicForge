#include "core.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <numbers>
namespace sf {
namespace {
constexpr double pi = std::numbers::pi;
double unit(double x) {
    return qBound(0., x, 1.);
}
double lerp(double a, double b, double t) {
    return a + (b - a) * t;
}
struct Structure {
    static constexpr int columns = 600, bands = 64;
    QVector<double> level = QVector<double>(columns), attack = level, speed = level, counts = level;
    QVector<double> spectrum = QVector<double>(columns * bands);
    QByteArray fingerprint;
    double energy = 0, bass = 0, brightness = 0, drive = 0, regularity = 0;
    double curve(const QVector<double>& values, double x) const {
        double p = unit(x) * (columns - 1);
        int a = int(p);
        return lerp(values[a], values[qMin(a + 1, columns - 1)], p - a);
    }
    double spec(double x, double y) const {
        double row = unit(y) * (bands - 1), col = unit(x) * (columns - 1);
        int r = int(row), c = int(col);
        return lerp(lerp(spectrum[r * columns + c],
                         spectrum[r * columns + qMin(c + 1, columns - 1)], col - c),
                    lerp(spectrum[qMin(r + 1, bands - 1) * columns + c],
                         spectrum[qMin(r + 1, bands - 1) * columns + qMin(c + 1, columns - 1)],
                         col - c),
                    row - r);
    }
};
Structure analyzeStructure(const QString& audio, const Cancel& cancel) {
    const auto source = readSource(audio, cancel);
    Structure out;
    QProcess decoder;
    decoder.setProgram(executable("ffmpeg"));
    decoder.setArguments({"-hide_banner", "-nostdin", "-v", "error", "-i", audio, "-vn", "-ac", "1",
                          "-ar", "11025", "-f", "f32le", "pipe:1"});
#ifdef Q_OS_WIN
    decoder.setCreateProcessArgumentsModifier(
        [](QProcess::CreateProcessArguments* a) { a->flags |= 0x08000000; });
#endif
    decoder.start();
    if (!decoder.waitForStarted(15000))
        throw Error(decoder.errorString());
    adoptChild(decoder);
    std::array<float, 512> frame{};
    int filled = 0;
    qint64 total = 0, frames = 0;
    double previousDb = -60, previousMagnitude = 0;
    QVector<double> onsets;
    onsets.reserve(350);
    double currentSpeed = 0;
    QCryptographicHash hash(QCryptographicHash::Sha256);
    QByteArray pending, errors;
    do {
        checkpoint(cancel);
        decoder.waitForReadyRead(30);
        errors = (errors + decoder.readAllStandardError()).right(4096);
        pending += decoder.read(65536);
        int consumed = 0;
        for (; consumed + 4 <= pending.size(); consumed += 4) {
            float value;
            std::memcpy(&value, pending.constData() + consumed, 4);
            if (!std::isfinite(value))
                value = 0;
            frame[filled++] = value;
            ++total;
            if (filled != 512)
                continue;
            QList<std::complex<double>> signal(512);
            double rms = 0;
            for (int i = 0; i < 512; ++i) {
                rms += frame[i] * frame[i];
                signal[i] = frame[i] * (.5 - .5 * std::cos(2 * pi * i / 511));
            }
            auto bins = fft(signal);
            double db = 20 * std::log10(qMax(1e-6, std::sqrt(rms / 512)));
            double level = unit((db + 60) / 54), attack = unit(qMax(0., db - previousDb) / 12);
            previousDb = db;
            int column =
                qBound(0, int((total - 256) / 11025. / source.duration * Structure::columns),
                       Structure::columns - 1);
            out.level[column] += level;
            out.attack[column] = qMax(out.attack[column], attack);
            out.counts[column]++;
            double magnitude = 0, low = 0, high = 0;
            for (int k = 0; k < 257; ++k) {
                double v = std::abs(bins[k]);
                magnitude += v;
                if (k < 12)
                    low += v;
                if (k > 100)
                    high += v;
            }
            double onset =
                attack * .9 + qMax(0., magnitude - previousMagnitude) / qMax(.01, magnitude) * .3;
            previousMagnitude = magnitude;
            onsets << onset;
            if (onsets.size() > 345)
                onsets.removeFirst();
            if (++frames % 43 == 0 && onsets.size() > 100) {
                auto sorted = onsets;
                std::sort(sorted.begin(), sorted.end());
                double median = sorted[sorted.size() / 2];
                double threshold = qMax(
                    .012,
                    median + (sorted[sorted.size() * 3 / 4] - sorted[sorted.size() / 4]) * .75);
                int peaks = 0, last = -10;
                for (int i = 1; i + 1 < onsets.size(); ++i)
                    if (onsets[i] > threshold && onsets[i] > onsets[i - 1] &&
                        onsets[i] >= onsets[i + 1] && i - last >= 4) {
                        ++peaks;
                        last = i;
                    }
                double best = 0;
                int lag = 43;
                double mean = 0;
                for (auto v : onsets)
                    mean += v;
                mean /= onsets.size();
                for (int l = 13; l <= 57; ++l) {
                    double a = 0, b = 0, c = 0;
                    for (int i = l; i < onsets.size(); ++i) {
                        double x = onsets[i] - mean, y = onsets[i - l] - mean;
                        a += x * y;
                        b += x * x;
                        c += y * y;
                    }
                    double score = a / std::sqrt(qMax(1e-20, b * c));
                    if (score > best) {
                        best = score;
                        lag = l;
                    }
                }
                double tempo = 60 * (11025. / 256) / lag;
                currentSpeed =
                    peaks < 3 || db < -55
                        ? 0
                        : unit((tempo - 45) / 155) * unit(best) * .75 +
                              unit((peaks / (onsets.size() * 256. / 11025) - .25) / 5) * .25;
                out.regularity = qMax(out.regularity, best);
            }
            out.speed[column] += currentSpeed;
            for (int band = 0; band < Structure::bands; ++band) {
                double k = std::pow(double(band) / (Structure::bands - 1), 1.65) * 255.4;
                int lo = int(k);
                double value = lerp(std::abs(bins[lo]), std::abs(bins[qMin(256, lo + 1)]), k - lo);
                out.spectrum[band * Structure::columns + column] +=
                    unit(std::log1p(value) / std::log1p(512 * .25));
            }
            out.bass += low / qMax(.001, magnitude);
            out.brightness += high / qMax(.001, magnitude);
            std::copy(frame.begin() + 256, frame.end(), frame.begin());
            filled = 256;
        }
        hash.addData(QByteArrayView(pending.constData(), consumed));
        pending.remove(0, consumed);
    } while (decoder.state() != QProcess::NotRunning || decoder.bytesAvailable() > 0);
    if (decoder.exitCode() != 0)
        throw Error(QString::fromUtf8(errors));
    out.fingerprint = hash.result();
    out.bass /= qMax(qint64(1), frames);
    out.brightness /= qMax(qint64(1), frames);
    for (int c = 0; c < Structure::columns; ++c)
        if (out.counts[c]) {
            out.level[c] /= out.counts[c];
            out.speed[c] /= out.counts[c];
            for (int b = 0; b < Structure::bands; ++b)
                out.spectrum[b * Structure::columns + c] /= out.counts[c];
        }
    int previous = -1;
    for (int c = 0; c < Structure::columns; ++c)
        if (out.counts[c]) {
            for (int gap = previous + 1; gap < c; ++gap) {
                double t = previous < 0 ? 1 : double(gap - previous) / (c - previous);
                int a = qMax(0, previous);
                out.level[gap] = lerp(out.level[a], out.level[c], t);
                out.attack[gap] = lerp(out.attack[a], out.attack[c], t);
                out.speed[gap] = lerp(out.speed[a], out.speed[c], t);
                for (int b = 0; b < Structure::bands; ++b)
                    out.spectrum[b * Structure::columns + gap] =
                        lerp(out.spectrum[b * Structure::columns + a],
                             out.spectrum[b * Structure::columns + c], t);
            }
            previous = c;
        }
    for (int c = previous + 1; c < Structure::columns; ++c)
        if (previous >= 0) {
            out.level[c] = out.level[previous];
            out.speed[c] = out.speed[previous];
            for (int b = 0; b < Structure::bands; ++b)
                out.spectrum[b * Structure::columns + c] =
                    out.spectrum[b * Structure::columns + previous];
        }
    for (int c = 0; c < Structure::columns; ++c) {
        out.energy += out.level[c];
        out.drive += out.speed[c];
    }
    out.energy /= Structure::columns;
    out.drive = unit(out.drive / Structure::columns * 1.8);
    return out;
}
struct Field {
    int size;
    QVector<float> values;
    explicit Field(int size) : size(size), values(size * size) {}
    double at(double x, double y) const {
        double px = std::fmod((x + 1) * .5, 1.);
        if (px < 0)
            px += 1;
        double py = std::fmod((y + 1) * .5, 1.);
        if (py < 0)
            py += 1;
        px *= size;
        py *= size;
        int a = int(px), b = int(py);
        return lerp(lerp(values[b * size + a], values[b * size + (a + 1) % size], px - a),
                    lerp(values[((b + 1) % size) * size + a],
                         values[((b + 1) % size) * size + (a + 1) % size], px - a),
                    py - b);
    }
    void normalize() {
        auto sorted = values;
        std::sort(sorted.begin(), sorted.end());
        double low = sorted[sorted.size() / 100], high = sorted[sorted.size() * 99 / 100];
        for (auto& value : values)
            value = float(unit((value - low) / qMax(1e-6, high - low)));
    }
};
Field fbm(int size, int cells, int octaves, QRandomGenerator& random, double persistence = .42) {
    Field result(size);
    double amplitude = 1, total = 0;
    for (int octave = 0; octave < octaves; ++octave) {
        QVector<double> grid(cells * cells);
        for (auto& v : grid)
            v = random.generateDouble();
        for (int y = 0; y < size; ++y)
            for (int x = 0; x < size; ++x) {
                double px = double(x) * cells / size, py = double(y) * cells / size;
                int a = int(px), b = int(py);
                double u = px - a, v = py - b;
                u = u * u * u * (u * (u * 6 - 15) + 10);
                v = v * v * v * (v * (v * 6 - 15) + 10);
                double n = lerp(lerp(grid[(b % cells) * cells + a % cells],
                                     grid[(b % cells) * cells + (a + 1) % cells], u),
                                lerp(grid[((b + 1) % cells) * cells + a % cells],
                                     grid[((b + 1) % cells) * cells + (a + 1) % cells], u),
                                v);
                result.values[y * size + x] += float(n * amplitude);
            }
        total += amplitude;
        amplitude *= persistence;
        cells = qMin(size / 2, cells * 2);
    }
    for (auto& v : result.values)
        v /= total;
    result.normalize();
    return result;
}
QColor palette(const QList<QColor>& colors, const QList<double>& stops, double value) {
    value = unit(value);
    if (colors.size() == 1)
        return colors[0];
    for (int i = 1; i < colors.size(); ++i) {
        double a = stops.value(i - 1, double(i - 1) / (colors.size() - 1)),
               b = stops.value(i, double(i) / (colors.size() - 1));
        if (value <= b) {
            double t = unit((value - a) / qMax(1e-9, b - a));
            return QColor::fromRgbF(lerp(colors[i - 1].redF(), colors[i].redF(), t),
                                    lerp(colors[i - 1].greenF(), colors[i].greenF(), t),
                                    lerp(colors[i - 1].blueF(), colors[i].blueF(), t));
        }
    }
    return colors.last();
}
} // namespace
QImage restoredTexture(const QString& audio, const CoverOptions& options, const Cancel& cancel) {
    const auto structure = analyzeStructure(audio, cancel);
    auto digest = QCryptographicHash::hash(structure.fingerprint + QByteArray::number(options.seed),
                                           QCryptographicHash::Sha256);
    QRandomGenerator random(qFromLittleEndian<quint32>(digest.constData()));
    const int n = qBound(192, options.size, 640);
    double drive = structure.drive, detail = options.detail / 100.;
    auto warpX = fbm(n, 2 + int(drive * 2), 3, random),
         warpY = fbm(n, 3 + int(drive * 2), 3, random);
    auto macro = fbm(n, 3 + int(structure.bass * 3), 3, random, .4),
         macroB = fbm(n, 4 + int(structure.bass * 3), 2, random, .35);
    auto meso = fbm(n, 5 + int((.28 + drive * .4) * 8), 3, random),
         micro = fbm(n, 15 + int(detail * 22), 2, random, .45);
    Field base(n), current(n), mesoMap(n);
    double phase = random.generateDouble() * 2 * pi;
    int composition = structure.bass > .6 && drive < .45 ? 2 : drive > .65 ? 0 : drive > .4 ? 1 : 4;
    for (int y = 0; y < n; ++y) {
        checkpoint(cancel);
        for (int x = 0; x < n; ++x) {
            int i = y * n + x;
            double u = double(x) / (n - 1) * 2 - 1, v = double(y) / (n - 1) * 2 - 1;
            double strength = .12 + (.08 + drive * .42) * .36;
            double wx = warpX.values[i] * 2 - 1, wy = warpY.values[i] * 2 - 1;
            double xw = u + wx * strength, yw = v + wy * strength;
            double radius = std::hypot(xw, yw), angle = std::atan2(yw, xw);
            if (composition == 1) {
                angle += (1.1 + drive * 3.6) * std::exp(-radius * .72) + wx * .35;
                xw = std::cos(angle) * radius;
                yw = std::sin(angle) * radius;
            } else if (composition == 2) {
                double pulse = std::sin(radius * pi * (2 + drive * 3.2) + wy * 2.5);
                xw += xw / qMax(.001, radius) * pulse * strength * .42;
                yw += yw / qMax(.001, radius) * pulse * strength * .42;
            } else if (composition == 4) {
                double fold = std::sin((xw + yw) * pi * (1.2 + structure.regularity * 2.2));
                xw += fold * strength * .38;
                yw -= fold * strength * .22;
            }
            double a = macro.at(xw, yw), b = macroB.at(xw * .92, yw * .92),
                   m = meso.at(xw * 1.10, yw * 1.10);
            double directional = xw * std::cos(phase) + yw * std::sin(phase),
                   cross = -xw * std::sin(phase) + yw * std::cos(phase);
            double flow = directional * pi * (.72 + drive * 1.6) +
                          (b - .5) * pi * (1.2 + drive * 2) + (m - .5) * (.25 + drive * .5) +
                          std::sin(cross * pi * 1.4) * (.28 + drive * .55);
            if (options.pattern == 2)
                flow += (m - .5) * structure.curve(structure.speed, double(x) / (n - 1)) * 1.8;
            double currents = .5 + .5 * std::sin(flow),
                   folds = .5 + .5 * std::sin(flow * 1.05 + b * 1.8), field = folds;
            if (composition == 0)
                field = unit(directional * .35 + .5 + (b - .5) * .46);
            else if (composition == 1)
                field =
                    .5 + .5 * std::sin(angle * 3 + radius * (3.4 + drive * 2.4) + (m - .5) * 1.2);
            else if (composition == 2)
                field = unit(1 - radius / 1.5 + std::cos(angle * 5) * .1 + (b - .5) * .18);
            if (options.pattern == 0) {
                double stripe = std::sin((double(x) * (.016 + drive * .01) +
                                          y * (.006 + drive * .008) + a * 4.2 + m * 2.4 - b * 3) *
                                         pi);
                field = unit(structure.spec(unit((n - 1 - y + (a - .5) * 100) / n),
                                            unit((x + (m - .5) * 130) / n)) *
                                 .65 +
                             std::pow(std::abs(stripe), .34) * .25 + micro.values[i] * .1);
            }
            base.values[i] = float(a * .1 + b * .1 + field * .46 + currents * .34);
            current.values[i] = float(currents);
            mesoMap.values[i] = float(m);
        }
    }
    base.normalize();
    QList<QColor> colors = options.palette;
    QList<double> stops = options.stops;
    if (options.colorSource == 2) {
        colors = {QColor("#21103F"), QColor("#5E2A92"), QColor("#173D87"),
                  QColor("#157FAF"), QColor("#40C8B0"), QColor("#EDD96B"),
                  QColor("#EF743D"), QColor("#DB283D"), QColor("#870D24")};
        stops = {0, .12, .24, .35, .45, .55, .65, .75, 1};
    } else if (options.colorSource == 1) {
        colors = {QColor("#17224b"), QColor("#3f4b91"), QColor("#83929e"),
                  QColor("#e9bb76"), QColor("#c65e4c"), QColor("#761f42")};
        stops = {0, .18, .4, .56, .75, 1};
    } else if (options.colorSource == 0) {
        colors = {QColor("#101050"), QColor("#3235a5"), QColor("#be207c"), QColor("#ff4575"),
                  QColor("#ffc181")};
        stops = {0, .25, .5, .75, 1};
    }
    if (colors.isEmpty())
        colors = {QColor("#30206d"), QColor("#f9a46a")};
    QImage image(n, n, QImage::Format_RGB32);
    for (int y = 0; y < n; ++y) {
        checkpoint(cancel);
        auto* pixels = reinterpret_cast<QRgb*>(image.scanLine(y));
        for (int x = 0; x < n; ++x) {
            int i = y * n + x;
            double t = double(x) / (n - 1), py = double(y) / (n - 1);
            t = unit(t + std::pow(std::sin(t * pi), 2) * (.026 * std::sin(py * 2 * pi + phase) +
                                                          .010 * std::sin(py * 4 * pi - phase)));
            double level = structure.curve(structure.level, t),
                   localDrive = options.pattern == 2
                                    ? unit(structure.curve(structure.speed, t) * 1.8)
                                    : drive;
            double field = base.values[i];
            if (options.pattern == 2)
                field = unit(field * .90 + structure.spec(t, 1 - py) * .07 + level * .03);
            double width = .38, center = qBound(width * .5, drive, 1 - width * .5);
            double position = center + (field - .5) * width;
            if (options.pattern == 2)
                position =
                    unit(position * .70 + (.18 + localDrive * .64) * .30 + (field - .5) * .08);
            if (options.colorSource == 2)
                position =
                    unit(.10 + structure.curve(structure.speed, t) * .78 + (field - .5) * .38);
            QColor color = palette(colors, stops, position);
            double strata = .5 + .5 * std::sin(field * pi * (2 + localDrive * 6) +
                                               (mesoMap.values[i] - .5) * .18);
            double depth = (.52 + .52 * field) * (.86 + .14 * strata);
            if (options.pattern == 2)
                depth *= (.88 + level * .12) * (.94 + structure.spec(t, 1 - py) * .08);
            double vein = .06 + structure.brightness * .25 + drive * .48;
            vein *= .5 + detail;
            double ribbonWidth = .028 + (1 - vein) * .040;
            double ribbon = std::exp(-std::pow((current.values[i] - .56) / ribbonWidth, 2)) *
                            (.08 + vein * .18);
            if (options.pattern == 2)
                ribbon *= .35 + localDrive * .65 + structure.curve(structure.attack, t) * .20;
            double shadow =
                1 - std::exp(-std::pow((current.values[i] - .47) / (ribbonWidth * 1.8), 2)) *
                        (.08 + localDrive * .12);
            double glow =
                (std::exp(-std::hypot(double(x) / n - .5, double(y) / n - .45) * 3) - .35) * 20;
            double grain = (micro.values[i] - .5) * (.8 + detail * 1.8);
            auto channel = [&](int value) {
                double v = lerp(value * depth, value * .65 + 140, ribbon) * shadow + glow + grain;
                return qBound(0, qRound((v - 127.5) * options.contrast / 100. + 127.5), 255);
            };
            color = QColor(channel(color.red()), channel(color.green()), channel(color.blue()));
            float h, s, l, a;
            color.getHslF(&h, &s, &l, &a);
            color = QColor::fromHslF(h, unit(s * options.saturation / 100.), l);
            pixels[x] = color.rgb();
        }
    }
    return image;
}
} // namespace sf
