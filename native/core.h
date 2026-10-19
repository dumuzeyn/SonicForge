#pragma once
#include <QtCore>
#include <QtGui>
#include <atomic>
#include <complex>
#include <functional>
#include <memory>
#include <stdexcept>

namespace sf {
struct Error : std::runtime_error {
    explicit Error(const QString& message) : std::runtime_error(message.toUtf8().constData()) {}
};
using Cancel = std::shared_ptr<std::atomic_bool>;
using Progress = std::function<void(QString, double)>;
void checkpoint(const Cancel& cancel);
QString executable(const QString& name);
QString cacheDirectory();
QString uniqueFile(const QString& suffix = QStringLiteral(".wav"));
QByteArray process(const QString& program, const QStringList& arguments, const Cancel& cancel = {},
                   Progress progress = {}, bool captureOutput = true, bool mergeError = false);
QByteArray ffmpeg(const QStringList& arguments, const Cancel& cancel = {}, Progress progress = {});
QVector<float> decode(const QString& file, int rate = 16000, int channels = 1, double start = 0,
                      double length = -1, const Cancel& cancel = {});
void writeWav(const QString& path, const QVector<float>& samples, int rate, int channels);
struct Source {
    QString path;
    double duration = 0;
    QVector<float> peaks;
    qint64 size = 0, modified = 0;
};
struct Clip {
    QString id, source;
    int lane = 0;
    double start = 0, end = 0, position = 0, gain = 0, fadeIn = 0, fadeOut = 0;
    double duration() const {
        return end - start;
    }
};
struct Project {
    QMap<QString, Source> sources;
    QList<Clip> clips;
    QSet<int> muted;
    double duration() const;
    int lanes() const;
    Clip& get(const QString& id);
    const Clip& get(const QString& id) const;
    double freePosition(int lane, double position, double duration,
                        const QString& exclude = {}) const;
    QString add(const Source& source, int lane = 0, double position = -1);
    QString split(const QString& id, double at);
    void validate() const;
    QJsonObject json() const;
};
Source readSource(const QString& file, const Cancel& cancel = {});
QString render(const Project& project, const QString& target, const Cancel& cancel = {},
               double start = 0, double length = -1, Progress progress = {});
Source cutAudio(const Project& project, const Clip& clip, double a, double b,
                const Cancel& cancel = {});
Source crossfade(const Project& project, const Clip& first, const Clip& next,
                 const Cancel& cancel = {}, double seconds = 2);
QString timestamp(double seconds);
double parseTime(const QString& stamp);
struct Lyric {
    double start = 0, end = 0;
    QString text;
    double confidence = 1;
};
QList<Lyric> parseLyrics(const QString& text, bool strict = true);
QString lrc(const QList<Lyric>& lines);
QString plainLyrics(const QString& text);
QString soundSpelling(const QString& text, const QString& alphabet, const QString& language);
struct Metadata {
    QMap<QString, QString> values;
    QByteArray cover;
    QString coverMime;
};
Metadata readMetadata(const QString& path, const Cancel& cancel = {});
void writeMetadata(const QString& path, const QMap<QString, QString>& values,
                   bool replaceAll = false, bool preserveLyrics = true,
                   const QByteArray& cover = {}, bool replaceCover = false,
                   const Cancel& cancel = {});
void saveLyrics(const QString& audio, const QString& text, const QString& format,
                const Cancel& cancel = {});
struct AudioOptions {
    double lufs = -14, truePeak = -1.5, lra = 11, gain = 1, bass = 0, mid = 0, treble = 0,
           width = 1;
    bool denoise = false, autoDenoise = true, limiter = true, compressor = false, highpass = false,
         lowpass = false;
    double noiseStrength = 4, highpassHz = 40, lowpassHz = 18000, threshold = -18, ratio = 3,
           attack = 20, release = 250, makeup = 0, pitch = 0, speed = 1, reverb = 0, fadeIn = 0,
           fadeOut = 0;
    int sampleRate = 0, channels = 0, quality = 0;
    QStringList filters(double duration) const;
};
QJsonObject analyze(const QString& audio, const Cancel& cancel = {});
QString normalize(const QString& source, const QString& target, const AudioOptions& options,
                  const Cancel& cancel = {}, Progress progress = {});
QList<std::complex<double>> fft(QList<std::complex<double>> input);
struct CoverOptions {
    int size = 1000, seed = 0, pattern = 2, colorSource = 2, detail = 50, contrast = 100,
        saturation = 100, softness = 0;
    bool title = true, artist = false;
    QString mood;
    QList<QColor> palette{QColor("#30206d"), QColor("#cc4ba0"), QColor("#ffb45d")};
    QList<double> stops{0, .5, 1};
};
QImage makeCover(const QString& audio, const Metadata& metadata, const CoverOptions& options,
                 const Cancel& cancel = {});
QIcon icon(const QString& name, const QColor& color = QColor("#6550b9"));
QString iconSvg(const QString& name, const QColor& color = QColor("#6550b9"));
QString genre(const QString& path, const Cancel& cancel = {}, Progress progress = {});
QList<Lyric> recognize(const QString& path, const QString& language, const Cancel& cancel = {},
                       Progress progress = {});
QList<Lyric> alignLyrics(const QString& audio, const QString& text, const QString& language,
                         const Cancel& cancel = {}, Progress progress = {});
QStringList separate(const QString& audio, bool two, const Cancel& cancel = {},
                     Progress progress = {});
int neuralWorker(const QStringList& arguments);
QString ensureModel(const QString& kind, const Cancel& cancel = {}, Progress progress = {});
} // namespace sf
