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
    QVector<double> pace = level, pulse = level, confidence = level, density = level;
    double duration = 0;
    QByteArray fingerprint;
    double energy = 0, bass = 0, brightness = 0, drive = 0, regularity = 0;
    double flatness = 0, flux = 0, attackStrength = 0, harmonic = 0, dynamic = 0;
    int key = 9;
    QVector<double> chroma = QVector<double>(12);
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
void rhythmicTimeline(Structure& out, const QVector<double>& novelty, const QVector<double>& db,
                      const QVector<double>& bassDb, const Cancel& cancel) {
    if (novelty.isEmpty()) return;
    constexpr double rate = 11025. / 256;
    QVector<double> onset(novelty.size());
    for (int i = 0; i < onset.size(); ++i)
        onset[i] = (novelty[qMax(0,i-1)] + novelty[i]*2 + novelty[qMin(i+1,int(onset.size()-1))])*.25;
    for (int column = 0; column < Structure::columns; ++column) {
        checkpoint(cancel);
        const int center = qMin(int(onset.size()-1), qRound(double(column)/(Structure::columns-1)*(onset.size()-1)));
        // Several beats of context distinguish the accented pulse from melody
        // subdivisions, without averaging separate sections of the whole song.
        const int left = qMax(0,center-qRound(rate*4)), right = qMin(int(onset.size()),center+qRound(rate*4)+1);
        const int count = right-left;
        double localLevel=-120;
        for (int i=qMax(left,center-qRound(rate*.8));i<=qMin(right-1,center+qRound(rate*.8));++i)
            localLevel=qMax(localLevel,db[i]);
        if (count < 8 || localLevel < -55) continue;
        QVector<double> sorted(onset.begin()+left,onset.begin()+right);
        std::sort(sorted.begin(),sorted.end());
        // Stationary noise has spectral fluctuations but no distinct attacks.
        const double contrast=(sorted[count*9/10]-sorted[count/10])/qMax(.012,sorted[count/2]);
        if (contrast < .35) continue;
        const double threshold = std::max({.012, sorted[count/2]+(sorted[count*3/4]-sorted[count/4])*.75,
                                          sorted[count*9/10]*.2});
        double mean = 0;
        for (int i = left; i < right; ++i) mean += onset[i];
        mean /= count;
        int peaks = 0, localPeaks = 0, last = left-10;
        for (int i = left+1; i+1 < right; ++i)
            if (onset[i] > threshold && onset[i] > onset[i-1] && onset[i] >= onset[i+1] && i-last >= 4) {
                ++peaks;
                if (std::abs(i-center) <= qRound(rate*.8)) ++localPeaks;
                last = i;
            }
        if (peaks < 3 || localPeaks == 0 || sorted.last() < .012) continue;
        auto correlation = [&](int lag) {
            if (lag < 1 || lag >= count-3) return 0.;
            double xy=0,xx=0,yy=0;
            for (int i=left+lag;i<right;++i) {
                const double x=onset[i]-mean,y=onset[i-lag]-mean;
                xy+=x*y;xx+=x*x;yy+=y*y;
            }
            return xy/std::sqrt(qMax(1e-20,xx*yy));
        };
        struct Pulse { double lag, score; };
        QList<Pulse> candidates;
        for (int lag=qRound(rate*60/210);lag<=qRound(rate*60/45);++lag) {
            const double before=correlation(lag-1), at=correlation(lag), after=correlation(lag+1);
            if (at<before || at<after) continue;
            // Sub-frame peaks avoid preferring a 60 BPM sampling alias over a
            // genuine 180 BPM pulse whose period falls between analysis frames.
            const double curvature=before-2*at+after;
            const double offset=curvature< -1e-9 ? qBound(-.5,.5*(before-after)/curvature,.5) : 0.;
            candidates << Pulse{lag+offset, at-.25*(before-after)*offset};
        }
        if (candidates.isEmpty()) continue;
        auto best=*std::max_element(candidates.begin(),candidates.end(),
                                   [](const auto& a,const auto& b) { return a.score<b.score; });
        // Only clearly separated, percussive attacks justify a faster reading
        // when autocorrelation is ambiguous. Sustained overlapping notes retain
        // the strongest accented pulse. This measure is independent of volume.
        QVector<double> levels(db.begin()+left,db.begin()+right);
        std::sort(levels.begin(),levels.end());
        QVector<double> bassLevels(bassDb.begin()+left,bassDb.begin()+right);
        std::sort(bassLevels.begin(),bassLevels.end());
        const double release=std::max(levels[count*9/10]-levels[count/10],
                                      bassLevels[count*9/10]-bassLevels[count/10]);
        const double separation=unit((release-12)/18);
        Pulse selected=best;
        for (const auto& candidate:candidates) {
            const double ratio=best.lag/candidate.lag;
            const int subdivision=qRound(ratio);
            if (separation>=.5 && candidate.lag<selected.lag && subdivision>=2 && subdivision<=4 &&
                std::abs(ratio-subdivision)<.12 && candidate.score>=best.score-(.025+separation*.10))
                selected=candidate;
            // For legato music, a well-supported slower octave represents the
            // accented beat; fast notes between those accents are subdivisions.
            if (separation<.5 && candidate.lag>selected.lag &&
                std::abs(candidate.lag/best.lag-2)<.12 && candidate.score>=best.score-.10*(1-separation))
                selected=candidate;
        }
        const double confidence=unit(selected.score);
        const double bpm=rate*60/selected.lag;
        const double localSeconds=(qMin(right-1,center+qRound(rate*.8))-qMax(left,center-qRound(rate*.8))+1)/rate;
        const double localDensity=localPeaks/qMax(.1,localSeconds);
        out.pulse[column]=confidence>=.30 ? bpm : 0;
        out.confidence[column]=confidence;
        out.regularity=qMax(out.regularity,confidence>=.30 ? confidence : 0.);
        out.density[column]=localDensity;
        // Note density adds small variations within the tempo's color range;
        // it cannot turn a slow piano melody into a fast red section on its own.
        const double density=unit((localDensity-.5)/4);
        out.pace[column]=confidence>=.30 ? unit(bpm/200)*.95+density*.05 : density*.05;
    }
    // Reject isolated octave jumps without averaging over entire song sections.
    const auto measured=out.pace;
    const int medianRadius=qMax(1,qRound(.8/qMax(.001,out.duration)*(Structure::columns-1)));
    for (int i=0;i<measured.size();++i) {
        QVector<double> local;
        for (int k=-medianRadius;k<=medianRadius;++k) local<<measured[qBound(0,i+k,int(measured.size()-1))];
        std::sort(local.begin(),local.end());
        out.pace[i]=local[local.size()/2];
    }
    const auto raw=out.pace;
    const double sigma=qMax(.2,.60/qMax(.001,out.duration)*(Structure::columns-1));
    const int radius=qMax(1,int(std::ceil(sigma*3)));
    for (int i=0;i<raw.size();++i) {
        double total=0,weight=0;
        for (int k=-radius;k<=radius;++k) {
            double w=std::exp(-.5*k*k/(sigma*sigma));
            total+=raw[qBound(0,i+k,int(raw.size()-1))]*w;weight+=w;
        }
        out.pace[i]=total/weight;
    }
}
Structure analyzeStructure(const QString& audio, const Cancel& cancel) {
    const auto source = readSource(audio, cancel, false);
    Structure out;
    out.duration = source.duration;
    QProcess decoder;
    decoder.setProgram(executable("ffmpeg"));
    decoder.setArguments({"-hide_banner", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", audio, "-map", "0:a:0", "-vn", "-ac", "1",
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
    QVector<double> rhythmicNovelty, rhythmicDb, rhythmicBassDb;
    std::array<double,257> previousPeaks{};
    QCryptographicHash hash(QCryptographicHash::Sha256);
    QByteArray pending, errors;
    QElapsedTimer idle, elapsed; idle.start(); elapsed.start();
    do {
        checkpoint(cancel);
        decoder.waitForReadyRead(30);
        if (idle.elapsed() > 60000 || elapsed.elapsed() > 6 * 60 * 60 * 1000) { decoder.kill(); decoder.waitForFinished(5000); throw Error("Превышено время анализа обложки"); }
        errors = (errors + decoder.readAllStandardError()).right(4096);
        const auto bytes = decoder.read(65536); if (!bytes.isEmpty()) idle.restart(); pending += bytes;
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
            double magnitude = 0, low = 0, high = 0, bassPower = 0;
            double logarithm = 0;
            std::array<double,3> rhythmicFlux{};
            for (int k = 0; k < 257; ++k) {
                double v = std::abs(bins[k]);
                // A nearby-frequency maximum suppresses pitch drift/vibrato.
                // Log compression and balanced bands retain beat accents even
                // when a sustained bass or fast melody dominates the spectrum.
                if (frames>0 && k>0) {
                    const double increase=qMax(0.,std::log1p(v)-std::log1p(previousPeaks[k]));
                    rhythmicFlux[k<12 ? 0 : k<80 ? 1 : 2]+=increase;
                }
                magnitude += v;
                if (k > 0) {
                    logarithm += std::log(qMax(1e-12, v));
                    double hz = k * 11025. / 512;
                    int note = qRound(69 + 12 * std::log2(hz / 440));
                    out.chroma[(note % 12 + 12) % 12] += std::sqrt(v);
                }
                if (k < 12)
                    low += v;
                if (k>0 && k<12) bassPower+=std::norm(bins[k]);
                if (k > 100)
                    high += v;
            }
            for (int k=0;k<257;++k)
                previousPeaks[k]=std::max({std::abs(bins[qMax(0,k-1)]),std::abs(bins[k]),std::abs(bins[qMin(256,k+1)])});
            double onset =
                attack * .9 + qMax(0., magnitude - previousMagnitude) / qMax(.01, magnitude) * .3;
            previousMagnitude = magnitude;
            out.flatness += unit(std::exp(logarithm / 256) / qMax(1e-12, magnitude / 256));
            out.attackStrength += attack;
            out.flux += onset;
            rhythmicNovelty << rhythmicFlux[0]/11*.3+rhythmicFlux[1]/68*.5+rhythmicFlux[2]/177*.2;
            rhythmicDb << db;
            rhythmicBassDb << 10*std::log10(qMax(1e-12,bassPower));
            ++frames;
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
    rhythmicTimeline(out,rhythmicNovelty,rhythmicDb,rhythmicBassDb,cancel);
    out.bass /= qMax(qint64(1), frames);
    out.brightness /= qMax(qint64(1), frames);
    out.flatness /= qMax(qint64(1), frames);
    out.attackStrength = unit(out.attackStrength / qMax(qint64(1), frames) * 4);
    out.flux = unit(out.flux / qMax(qint64(1), frames) * 3);
    for (int c = 0; c < Structure::columns; ++c)
        if (out.counts[c]) {
            out.level[c] /= out.counts[c];
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
            for (int b = 0; b < Structure::bands; ++b)
                out.spectrum[b * Structure::columns + c] =
                    out.spectrum[b * Structure::columns + previous];
        }
    for (int c = 0; c < Structure::columns; ++c) {
        out.speed[c] = out.pace[c] * .65;
        out.energy += out.level[c];
        out.drive += out.speed[c];
    }
    out.energy /= Structure::columns;
    out.drive = unit(out.drive / Structure::columns * 1.8);
    auto sorted = out.level;
    std::sort(sorted.begin(), sorted.end());
    out.dynamic = unit((sorted[sorted.size()*9/10] - sorted[sorted.size()/10]) * 3);
    out.harmonic = unit((1 - out.flatness) * .45 + out.brightness * .35 + out.flux * .2);
    constexpr double major[12]{6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88};
    double best = -1;
    for (int root = 0; root < 12; ++root) {
        double score = 0;
        for (int note = 0; note < 12; ++note) score += out.chroma[note] * major[(note-root+12)%12];
        if (score > best) { best = score; out.key = root; }
    }
    double maximum = *std::max_element(out.spectrum.begin(), out.spectrum.end());
    if (maximum > 1e-9) for (auto& value : out.spectrum) value /= maximum;
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
#include "cover_rendering.inc"
} // namespace
QJsonObject analyzeCoverRhythm(const QString& audio, const Cancel& cancel) {
    const auto s=analyzeStructure(audio,cancel);
    QJsonArray points;
    for (int i=0;i<Structure::columns;++i)
        points.append(QJsonObject{{"seconds",s.duration*i/(Structure::columns-1)},
                                  {"pulse_bpm",s.pulse[i]}, {"pace",s.pace[i]},
                                  {"confidence",s.confidence[i]}, {"attacks_per_second",s.density[i]}});
    return {{"duration",s.duration},{"timeline",points}};
}
QImage restoredTexture(const QString& audio, const CoverOptions& options, const Cancel& cancel,
                       QVector<double>* music) {
    auto structure = analyzeStructure(audio, cancel);
    const QByteArray version = options.pattern == 0 ? "classic-crisp-v2" :
                               options.pattern == 1 ? "contour-character-v5" : "chronological-organic-v3";
    auto digest = QCryptographicHash::hash(version + structure.fingerprint + QByteArray::number(options.seed),
                                          QCryptographicHash::Sha256);
    quint32 seed = qFromLittleEndian<quint32>(digest.constData());
    if (music) *music = {structure.drive, structure.bass, structure.brightness, structure.regularity, double(seed)};
    QRandomGenerator random(seed);
    return options.pattern == 0 ? renderClassic(structure, options, random, cancel)
                                : renderOrganic(structure, options, random, cancel);
}
} // namespace sf
