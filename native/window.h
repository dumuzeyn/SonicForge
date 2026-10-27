#pragma once
#include "core.h"
#include "timeline.h"
#include "widgets.h"
#include <QtConcurrent>
#include <QtMultimedia>
#include <QtWidgets>
#include <optional>
struct WorkResult {
    QString error, text, file;
    QStringList files;
    QList<sf::Source> sources;
    QList<sf::Lyric> lyrics;
    QImage image;
    QJsonObject data;
    QList<QPair<double, double>> changes;
    sf::CoverArtwork artwork;
};
class Window final : public QMainWindow {
    Q_OBJECT
  public:
    explicit Window();
    void openFiles(const QStringList& files);
    bool smokeTest(const QString& output);
    void playbackSmoke(const QString& file, const QString& output);
    void lyricsSaveSmoke(const QString& file, const QString& output);
    void coverExportSmoke(const QString& file, const QString& output);
    void soundSmoke(const QString& file, const QString& output);
    void closeSmoke(const QString& output);
    void reliabilitySmoke(const QString& output);
    void openProject(const QString& path = {});

  protected:
    void closeEvent(QCloseEvent*) override;
    bool eventFilter(QObject*, QEvent*) override;

  private:
    QString language = "ru";
    QJsonObject strings;
    QTranslator qtTranslator;
    QTabWidget* tabs = nullptr;
    QTabBar* navigation = nullptr;
    Timeline* timeline = nullptr;
    QLineEdit *source = nullptr, *output = nullptr;
    QCheckBox *linked = nullptr, *showTimes = nullptr, *separateVocals = nullptr,
              *overwriteLyrics = nullptr;
    QComboBox *mixFormat = nullptr, *lyricFormat = nullptr, *lyricLanguage = nullptr,
              *lyricMode = nullptr, *lyricQuality = nullptr, *lyricTrack = nullptr;
    QPlainTextEdit *lyrics = nullptr, *log = nullptr;
    QLineEdit* stamp = nullptr;
    QLabel *counter = nullptr, *status = nullptr, *analysisLabel = nullptr,
           *playerClock = nullptr;
    CoverPreview* coverPreview = nullptr;
    sf::CoverArtwork coverArtwork;
    QImage coverImage;
    QSlider* playerSeek = nullptr;
    QToolButton *playButton = nullptr, *selectButton = nullptr;
    QDoubleSpinBox *rangeStart = nullptr, *rangeEnd = nullptr;
    QProgressBar* progressBar = nullptr;
    QPushButton* cancelButton = nullptr;
    QMediaPlayer* player = nullptr;
    QAudioOutput* audioOutput = nullptr;
    QWidget* paths = nullptr;
    QFutureWatcher<WorkResult>* watcher = nullptr;
    sf::Cancel cancel = std::make_shared<std::atomic_bool>(false);
    bool busy = false, playingTimeline = false, selectionArmed = false;
    double selectionStart = 0;
    QList<sf::Project> undoHistory, redoHistory;
    sf::Project dragSnapshot;
    QList<sf::Lyric> lyricTimes;
    QMap<QString, QLineEdit*> metadataFields;
    QMap<QString, QDoubleSpinBox*> numbers;
    QMap<QString, QCheckBox*> checks;
    QMap<QString, QComboBox*> choices;
    QList<QPair<QWidget*, QString>> labels;
    QList<QAbstractButton*> controls;
    QString workingSignature, workingFile, lastCover, lastOriginal, lastProcessed, customCoverFile;
    QString playerContext;
    double playerOrigin = 0;
    std::optional<qint64> pendingSeek;
    bool seekIsTimeline = false;
    sf::CoverOptions coverOptions;
    bool audioSliders = false, audioDirty = false;
    AudioPane *originalPane = nullptr, *processedPane = nullptr;
    QTimer* comparisonTimer = nullptr;
    QFutureWatcher<WorkResult>* comparisonWatcher = nullptr;
    sf::Cancel comparisonCancel = std::make_shared<std::atomic_bool>(false);
    QJsonObject measurements;
    quint64 comparisonRevision = 0;
    QSet<QString> comparisonFiles;
    QTimer *autosaveTimer = nullptr, *coverRefreshTimer = nullptr;
    QFutureWatcher<QString>* autosaveWatcher = nullptr;
    std::unique_ptr<QLockFile> recoveryLease;
    std::unique_ptr<QLockFile> restoredRecoveryLease;
    QString projectPath, recoveryPath, restoredRecoveryPath, lyricSource, pendingOpenProject;
    bool dirty = false, restoring = false, closing = false, closeAfterSave = false;
    quint64 documentRevision = 0;
    void markDirty();
    QString lyricText() const;
    QJsonObject workspaceState() const;
    void applyWorkspace(const QJsonObject& state);
    void saveProject(const QString& path = {});
    void autosave();
    void setupRecovery();
    void disposeRecovery();
    void updateInputs(bool enabled);
    void refreshWrittenSource(const QString& path);
    void cleanWorkingCache();
    QString t(const QString& key) const;
    QString localize(const QString& text) const;
    void retranslate();
    void loadLanguage();
    QWidget* page(const QString& name);
    QGroupBox* group(QBoxLayout* parent, const QString& name);
    QPushButton* button(QBoxLayout* parent, const QString& name, std::function<void()> action,
                        bool primary = false);
    QToolButton* tool(QBoxLayout* parent, const QString& icon, const QString& name,
                      const QString& description, std::function<void()> action);
    QDoubleSpinBox* number(QFormLayout* parent, const QString& key, const QString& label,
                           double value, double low, double high, double step = .1);
    QCheckBox* check(QBoxLayout* parent, const QString& key, const QString& label, bool value);
    QComboBox* choice(QFormLayout* parent, const QString& key, const QString& label,
                      const QStringList& values, int selected = 0);
    void buildEditor(QWidget*);
    void buildMetadata(QWidget*);
    void buildAudio(QWidget*);
    void buildCover(QWidget*);
    void buildLyrics(QWidget*);
    void buildProcessing(QWidget*);
    void buildHelp(QWidget*);
    void buildSettings(QWidget*);
    void startTask(const QString& name, std::function<WorkResult(sf::Progress)> work,
                   std::function<void(const WorkResult&)> finished = {});
    void failure(const QString& message);
    void appendLog(const QString& message);
    std::function<void()> releaseAudioForWrite(const QString& file);
    void remember();
    void projectChanged();
    void history(bool redo);
    void importAudio(const QStringList& files, int lane = -1, double at = -1);
    void edit(const QString& operation);
    void fade(bool incoming);
    void transition();
    void separateSelected(bool two);
    void selectCursor();
    void updateState();
    QString prepare(const sf::Project& project, bool link, const QString& original,
                    const QString& format);
    void preview(bool editor);
    void previewRange();
    void playFile(const QString& path, bool editor = false, const QString& context = {}, double origin = 0);
    void stop();
    void exportAudio();
    void loadMetadata();
    void analyzeAudio();
    void compareAudio();
    void scheduleComparison();
    void fragmentSettings();
    void showContextHelp(QWidget*, const QString&, const QString&, QPoint = {});
    sf::AudioOptions audioOptions() const;
    QMap<QString, QString> metadataValues() const;
    sf::CoverOptions currentCoverOptions() const;
    void generateCover(bool editText = false);
    void coverTextSettings();
    void refreshCoverPreview();
    void coverSettings();
    void loadLyrics();
    void recognizeLyrics();
    void saveLyrics();
    void insertStamp(bool live, bool advance);
    void processFiles();
    void loadPreferences();
    void savePreferences();
};
