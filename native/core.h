#pragma once
#include <QtCore>
#include <QtGui>
#include <atomic>
#include <complex>
#include <functional>
#include <memory>
#include <stdexcept>

namespace sf {
inline constexpr double LyricLead = .045;
struct Error : std::runtime_error {
    explicit Error(const QString& message) : std::runtime_error(message.toUtf8().constData()) {}
};
using Cancel = std::shared_ptr<std::atomic_bool>;
using Progress = std::function<void(QString, double)>;
void checkpoint(const Cancel& cancel);
void adoptChild(QProcess& process);
void shutdownWorkers();
class WavWriter {
    QSaveFile file;
    int rate, channels;
    bool floating;
    qint64 bytes = 0;

  public:
    WavWriter(const QString& path, int rate, int channels, bool floating = false);
    void append(const float* samples, qsizetype count);
    void finish();
};
QString executable(const QString& name);
QString cacheDirectory();
QString uniqueFile(const QString& suffix = QStringLiteral(".wav"));
QByteArray fileFingerprint(const QString& path, const Cancel& cancel = {});
QString readTextFile(const QString& path);
QString backupFile(const QString& path);
void publishFiles(const QList<QPair<QString, QString>>& files);
qint64 cleanCache(const QSet<QString>& protectedFiles = {});
void checkCacheCapacity(const QString& path, qint64 additional = 0);
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
    QByteArray fingerprint = {};
    int sampleRate = 44100, channels = 2, bits = 16;
};
struct Clip {
    QString id, source;
    int lane = 0;
    double start = 0, end = 0, position = 0, gain = 0, fadeIn = 0, fadeOut = 0;
    double volume = 1, speed = 1, bass = 0, mid = 0, treble = 0;
    QString originalSource;
    QString labelSource() const { return originalSource.isEmpty() ? source : originalSource; }
    double duration() const {
        return (end - start) / (speed > 0 ? speed : 1);
    }
};
struct Project {
    QMap<QString, Source> sources;
    QList<Clip> clips;
    QSet<int> muted;
    double duration() const;
    QString songSource() const;
    QString outputBaseName() const;
    int lanes() const;
    Clip& get(const QString& id);
    const Clip& get(const QString& id) const;
    double freePosition(int lane, double position, double duration,
                        const QString& exclude = {}) const;
    QString add(const Source& source, int lane = 0, double position = -1);
    QString split(const QString& id, double at);
    void validate() const;
    QJsonObject json() const;
    static Project fromJson(const QJsonObject& object);
};
struct RenderOptions {
    int sampleRate = 0, channels = 0, bits = 32;
    bool limiter = false;
    int quality = 0;
};
Source readSource(const QString& file, const Cancel& cancel = {}, bool withWaveform = true);
QString render(const Project& project, const QString& target, const Cancel& cancel = {},
               double start = 0, double length = -1, Progress progress = {}, RenderOptions options = {});
Source cutAudio(const Project& project, const Clip& clip, double a, double b,
                const Cancel& cancel = {});
Source crossfade(const Project& project, const Clip& first, const Clip& next,
                 const Cancel& cancel = {}, double seconds = 2);
QString timestamp(double seconds, int decimals = 2);
double parseTime(const QString& stamp);
struct Lyric {
    double start = 0, end = 0;
    QString text;
    double confidence = 1;
};
QList<Lyric> parseLyrics(const QString& text, bool strict = true);
QString lrc(const QList<Lyric>& lines);
QString plainLyrics(const QString& text);
QString scaleLyrics(const QString& text, double speed);
QString soundSpelling(const QString& text, const QString& alphabet, const QString& language);
struct Metadata {
    QMap<QString, QString> values;
    QByteArray cover;
    QString coverMime;
    QList<QByteArray> synchronizedLyrics;
    QStringList lyricLanguages;
    QMap<QString, QString> lyricTracks = {};
};
Metadata readMetadata(const QString& path, const Cancel& cancel = {});
void writeMetadata(const QString& path, const QMap<QString, QString>& values,
                   bool replaceAll = false, bool preserveLyrics = true,
                   const QByteArray& cover = {}, bool replaceCover = false,
                   const Cancel& cancel = {}, const QList<QByteArray>& synchronizedLyrics = {},
                   const QString& language = "und", const QString& description = {});
void transferLyrics(const QString& source, const QString& target, double speed = 1,
                    const Cancel& cancel = {});
QString saveLyrics(const QString& audio, const QString& text, const QString& format,
                const Cancel& cancel = {}, const QString& language = "und", const QString& description = {});
QString saveLyricsFile(const QString& path, const QString& text, const QString& format, const Cancel& cancel = {});
struct AudioOptions {
    double lufs = -14, truePeak = -1.5, lra = 11, gain = 1, bass = 0, mid = 0, treble = 0,
           width = 1;
    bool denoise = false, autoDenoise = false, limiter = true, compressor = false, highpass = false,
         lowpass = false;
    double noiseStrength = 4, highpassHz = 40, lowpassHz = 18000, threshold = -18, ratio = 3,
           attack = 20, release = 250, makeup = 0, pitch = 0, speed = 1, reverb = 0, fadeIn = 0,
           fadeOut = 0;
    int sampleRate = 0, channels = 0, quality = 0;
    QStringList filters(double duration) const;
};
QJsonObject analyze(const QString& audio, const Cancel& cancel = {});
QJsonObject analyzeCoverRhythm(const QString& audio, const Cancel& cancel = {});
QString normalize(const QString& source, const QString& target, const AudioOptions& options,
                  const Cancel& cancel = {}, Progress progress = {});
QList<QPair<double, double>> audioChanges(const QString& original, const QString& modified,
                                        const Cancel& cancel = {});
QList<std::complex<double>> fft(QList<std::complex<double>> input);
struct CoverOptions {
    int size = 1000, seed = 0, pattern = 2, colorSource = 4, detail = 50, contrast = 100,
        saturation = 100, softness = 0;
    bool title = true, artist = false, symbol = true;
    QString mood;
    QString text, fontFamily = "Unbounded";
    double textSize = 7.2, textX = 50, textY = 76;
    QColor ink; // Invalid means an automatic shared text/symbol color.
    QList<QColor> palette{QColor("#30206d"), QColor("#cc4ba0"), QColor("#ffb45d")};
    QList<double> stops{0, .5, 1};
};
struct CoverArtwork {
    QImage background;
    Metadata metadata;
    QVector<double> music;
};
struct CoverTextLayout {
    QString title, artist;
    QFont titleFont, artistFont;
    QRectF titleBounds, artistBounds, bounds;
};
CoverArtwork makeCoverArtwork(const QString& audio, const Metadata&, const CoverOptions&,
                              const Cancel& cancel = {});
CoverArtwork coverArtworkFromImage(const QImage&, const Metadata&, const CoverOptions&);
CoverTextLayout layoutCoverText(const Metadata&, const CoverOptions&);
QImage decorateCover(const CoverArtwork&, const CoverOptions&, const Cancel& cancel = {});
QImage makeCover(const QString& audio, const Metadata& metadata, const CoverOptions& options,
                 const Cancel& cancel = {});
Metadata coverMetadata(const QString& audio, const Metadata& metadata);
QIcon icon(const QString& name, const QColor& color = QColor("#6550b9"));
QString iconSvg(const QString& name, const QColor& color = QColor("#6550b9"));
QString genre(const QString& path, const Cancel& cancel = {}, Progress progress = {});
QList<Lyric> recognize(const QString& path, const QString& language, const Cancel& cancel = {},
                       Progress progress = {}, const QString& reference = {}, bool fast = false);
QList<Lyric> alignLyrics(const QString& audio, const QString& text, const QString& language,
                         const Cancel& cancel = {}, Progress progress = {},
                         const QString& reference = {}, bool fast = false);
QStringList separate(const QString& audio, bool two, const Cancel& cancel = {},
                     Progress progress = {});
int neuralWorker(const QStringList& arguments);
QString ensureModel(const QString& kind, const Cancel& cancel = {}, Progress progress = {});
} // namespace sf
