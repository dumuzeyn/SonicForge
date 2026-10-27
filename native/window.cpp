#include "window.h"
#include "palette.h"
#include <QDesktopServices>
#include <algorithm>
#include <cmath>
#include <thread>
#include <utility>
#ifdef Q_OS_WIN
#include <windows.h>
#endif

namespace {
void enableAction(QAbstractButton* control, bool enabled) {
    auto* tool = qobject_cast<QToolButton*>(control);
    if (!tool) {
        control->setEnabled(enabled);
        return;
    }
    if (tool->property("sfActionEnabled").isValid() &&
        tool->property("sfActionEnabled").toBool() == enabled)
        return;
    tool->setProperty("sfActionEnabled", enabled);
    tool->setIcon(sf::icon(tool->property("sfIconName").toString(),
                           enabled ? QColor("#6550b9") : QColor("#b0a7c3")));
    tool->style()->unpolish(tool);
    tool->style()->polish(tool);
    tool->update();
}
QStringList audioExtensions() {
    return {"*.mp3", "*.wav", "*.flac", "*.m4a", "*.aac", "*.ogg", "*.opus", "*.wma"};
}
QString audioFilter() {
    return "Аудио (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma)";
}
QHBoxLayout* row(QBoxLayout* layout) {
    auto* result = new QHBoxLayout;
    result->setSpacing(8);
    layout->addLayout(result);
    return result;
}
QWidget* scrollContent(QWidget* page, QVBoxLayout*& layout) {
    auto* outer = new QVBoxLayout(page);
    outer->setContentsMargins(0, 0, 0, 0);
    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    auto* content = new QWidget;
    layout = new QVBoxLayout(content);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(12);
    scroll->setWidget(content);
    outer->addWidget(scroll);
    return content;
}
} // namespace
QString Window::t(const QString& key) const {
    return strings.value(key).toString(key);
}
QString Window::localize(const QString& text) const {
    if (language != "en" || text.isEmpty())
        return text;
    static const QHash<QString, QString> dictionary = [] {
        QHash<QString, QString> result;
        auto load = [](const QString& path) {
            QFile file(path);
            return file.open(QIODevice::ReadOnly) ? QJsonDocument::fromJson(file.readAll()).object()
                                                  : QJsonObject();
        };
        auto ru = load(":/ru.json"), en = load(":/en.json");
        for (auto it = ru.begin(); it != ru.end(); ++it)
            if (it.value().isString() && en[it.key()].isString())
                result[it.value().toString()] = en[it.key()].toString();
        auto native = load(":/en-native.json");
        for (auto it = native.begin(); it != native.end(); ++it)
            result[it.key()] = it.value().toString();
        const auto reliable = load(":/en-reliability.json");
        for (auto it = reliable.begin(); it != reliable.end(); ++it) result[it.key()] = it.value().toString();
        return result;
    }();
    if (dictionary.contains(text))
        return dictionary.value(text);
    struct Pattern { QRegularExpression expression; QString translation; QList<QString> placeholders; };
    static const QList<Pattern> patterns = [&] {
        QList<Pattern> result;
        const QRegularExpression placeholder("%L?[1-9][0-9]?");
        for (auto it = dictionary.begin(); it != dictionary.end(); ++it) {
            auto matches = placeholder.globalMatch(it.key()); QString expression = "^"; qsizetype previous = 0; QList<QString> keys;
            while (matches.hasNext()) { const auto match = matches.next(); expression += QRegularExpression::escape(it.key().mid(previous, match.capturedStart()-previous)) + "(.*?)"; keys << match.captured(); previous = match.capturedEnd(); }
            if (keys.isEmpty()) continue;
            expression += QRegularExpression::escape(it.key().mid(previous)) + "$";
            result << Pattern{QRegularExpression(expression, QRegularExpression::DotMatchesEverythingOption), it.value(), keys};
        }
        return result;
    }();
    for (const auto& pattern : patterns) { const auto match = pattern.expression.match(text); if (match.hasMatch()) { auto result = pattern.translation; for (int i = pattern.placeholders.size()-1; i >= 0; --i) result.replace(pattern.placeholders[i], match.captured(i+1)); return result; } }
    for (auto it = dictionary.begin(); it != dictionary.end(); ++it)
        if (it.key().size() > 4 && it.key().endsWith(' ') && text.startsWith(it.key()))
            return it.value() + text.mid(it.key().size());
    return text;
}
void Window::retranslate() {
    const QStringList keys{"tab_editor", "tab_metadata",   "tab_audio", "tab_cover",
                           "tab_lyrics", "tab_processing", "tab_help",  "tab_settings"};
    for (int i = 0; i < keys.size(); ++i) {
        tabs->setTabText(i, t(keys[i]));
        if (navigation)
            navigation->setTabText(i, t(keys[i]));
    }
    auto translated = [this](QObject* object, const QString& current, const char* field) {
        QByteArray original = QByteArray("sfOriginal_") + field;
        QByteArray rendered = QByteArray("sfRendered_") + field;
        if (!object->property(original).isValid() ||
            current != object->property(rendered).toString())
            object->setProperty(original, current);
        QString text = localize(object->property(original).toString());
        object->setProperty(rendered, text);
        return text;
    };
    for (auto* widget : findChildren<QWidget*>()) {
        widget->setLocale(QLocale(language));
        if (!widget->accessibleName().isEmpty()) widget->setAccessibleName(translated(widget, widget->accessibleName(), "accessibleName"));
        if (!widget->accessibleDescription().isEmpty()) widget->setAccessibleDescription(translated(widget, widget->accessibleDescription(), "accessibleDescription"));
        if (!widget->toolTip().isEmpty()) widget->setToolTip(translated(widget, widget->toolTip(), "tooltip"));
        if (auto* label = qobject_cast<QLabel*>(widget)) {
            if (label->pixmap().isNull())
                label->setText(translated(label, label->text(), "text"));
        } else if (auto* button = qobject_cast<QAbstractButton*>(widget)) {
            button->setText(translated(button, button->text(), "text"));
        } else if (auto* group = qobject_cast<QGroupBox*>(widget)) {
            group->setTitle(translated(group, group->title(), "title"));
        } else if (auto* edit = qobject_cast<QLineEdit*>(widget)) {
            edit->setPlaceholderText(translated(edit, edit->placeholderText(), "placeholder"));
        } else if (auto* edit = qobject_cast<QPlainTextEdit*>(widget)) {
            edit->setPlaceholderText(translated(edit, edit->placeholderText(), "placeholder"));
        } else if (auto* combo = qobject_cast<QComboBox*>(widget)) {
            for (int i = 0; i < combo->count(); ++i) {
                int role = Qt::UserRole + 79;
                if (!combo->itemData(i, role).isValid())
                    combo->setItemData(i, combo->itemText(i), role);
                combo->setItemText(i, localize(combo->itemData(i, role).toString()));
            }
        } else if (auto* browser = qobject_cast<QTextBrowser*>(widget);
                   browser && browser->property("sfHelp").toBool()) {
            if (language == "en") {
                QFile file(":/help-en.html");
                if (file.open(QIODevice::ReadOnly))
                    browser->setHtml(QString::fromUtf8(file.readAll()));
            } else
                browser->setHtml(browser->property("sfRussianHtml").toString());
        }
    }
    for (auto* action : findChildren<QAction*>()) if (!action->text().isEmpty()) action->setText(translated(action, action->text(), "action"));
    timeline->setProperty("english", language == "en");
    source->setPlaceholderText(t("source"));
    output->setPlaceholderText(t("output"));
    for (const auto& label : labels)
        if (auto* text = qobject_cast<QLabel*>(label.first))
            text->setText(t(label.second));
    timeline->viewport()->update();
}
void Window::loadLanguage() {
    QLocale::setDefault(QLocale(language));
    qApp->removeTranslator(&qtTranslator);
    if (qtTranslator.load("qt_" + language,
                          QCoreApplication::applicationDirPath() + "/translations"))
        qApp->installTranslator(&qtTranslator);
    QFile file(":/" + language + ".json");
    if (file.open(QIODevice::ReadOnly))
        strings = QJsonDocument::fromJson(file.readAll()).object();
}
QWidget* Window::page(const QString& name) {
    auto* widget = new QWidget;
    tabs->addTab(widget, t(name));
    widget->setProperty("sfHelpTitle", t(name));
    widget->setProperty("sfHelpKey", name);
    if (navigation)
        navigation->addTab(t(name));
    return widget;
}
QGroupBox* Window::group(QBoxLayout* parent, const QString& name) {
    auto* box = new QGroupBox(name);
    parent->addWidget(box);
    return box;
}
QPushButton* Window::button(QBoxLayout* parent, const QString& name, std::function<void()> action,
                            bool primary) {
    auto* b = new QPushButton(name);
    b->setProperty("primary", primary);
    b->setMinimumHeight(34);
    b->setProperty("sfHelpTitle", name);
    b->setProperty("sfHelpKey", name);
    parent->addWidget(b);
    if (b->window() == this)
        controls << b;
    connect(b, &QPushButton::clicked, this, [this, action] {
        try {
            action();
        } catch (const std::exception& e) {
            failure(QString::fromUtf8(e.what()));
        }
    });
    return b;
}
QToolButton* Window::tool(QBoxLayout* parent, const QString& name, const QString& title,
                          const QString& description, std::function<void()> action) {
    auto* b = new QToolButton;
    b->setIcon(sf::icon(name));
    b->setIconSize(QSize(24, 24));
    b->setFixedSize(44, 38);
    b->setAccessibleName(title);
    b->setProperty("sfAction", title);
    b->setProperty("sfDescription", description);
    b->setProperty("sfIconName", name);
    b->setProperty("sfActionEnabled", true);
    b->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(b, &QWidget::customContextMenuRequested, this,
            [this, b, title, description](QPoint point) {
                QMenu menu(b);
                auto* action = new QWidgetAction(&menu);
                auto* text = new QLabel("<b>" + localize(title).toHtmlEscaped() + "</b><br><br>" +
                                        localize(description).toHtmlEscaped());
                text->setWordWrap(true);
                text->setMaximumWidth(340);
                text->setMargin(14);
                action->setDefaultWidget(text);
                menu.addAction(action);
                menu.exec(b->mapToGlobal(point));
            });
    connect(b, &QToolButton::clicked, this, [this, b, action] {
        if (!b->property("sfActionEnabled").toBool())
            return;
        try {
            action();
        } catch (const std::exception& e) {
            failure(QString::fromUtf8(e.what()));
        }
    });
    parent->addWidget(b);
    controls << b;
    return b;
}
QDoubleSpinBox* Window::number(QFormLayout* layout, const QString& key, const QString& label,
                               double value, double low, double high, double step) {
    auto* spin = new QDoubleSpinBox;
    spin->setRange(low, high);
    spin->setDecimals(step < .01 ? 3 : step < 1 ? 2 : 0);
    spin->setSingleStep(step);
    spin->setValue(value);
    spin->setMinimumHeight(30);
    numbers[key] = spin;
    spin->setAccessibleName(label);
    spin->setProperty("sfHelpTitle", label);
    spin->setProperty("sfHelpKey", key);
    if (audioSliders || QStringList{"cover_detail", "cover_contrast", "cover_saturation",
                                    "cover_softness"}.contains(key)) {
        double scale = QStringList{"gain", "width", "speed", "reverb"}.contains(key) ? 100 : 1;
        auto* panel = valueSlider(spin, scale == 100 ? "%" : QString(), scale);
        panel->setProperty("sfHelpTitle", label);
        panel->setProperty("sfHelpKey", key);
        layout->addRow(label, panel);
    } else
        layout->addRow(label, spin);
    return spin;
}
QCheckBox* Window::check(QBoxLayout* parent, const QString& key, const QString& label, bool value) {
    auto* box = new QCheckBox(label);
    box->setChecked(value);
    parent->addWidget(box);
    checks[key] = box;
    box->setProperty("sfHelpTitle", label);
    box->setProperty("sfHelpKey", key);
    return box;
}
QComboBox* Window::choice(QFormLayout* layout, const QString& key, const QString& label,
                          const QStringList& values, int selected) {
    auto* combo = new QComboBox;
    combo->addItems(values);
    combo->setCurrentIndex(selected);
    combo->setMinimumHeight(30);
    layout->addRow(label, combo);
    choices[key] = combo;
    combo->setProperty("sfHelpTitle", label);
    combo->setProperty("sfHelpKey", key);
    return combo;
}
Window::Window() {
    QCoreApplication::setOrganizationName("Dumuzeyn");
    QCoreApplication::setApplicationName("SonicForge");
    loadPreferences();
    loadLanguage();
    setWindowTitle("Sonic Forge[*]");
    resize(1120, 760);
    setMinimumSize(760, 500);
    setWindowIcon(QIcon(":/assets/sonic_forge_mark.ico"));
    setStyleSheet(
        "QMainWindow,QWidget{background:#f7f6fb;color:#272232;font-family:'Segoe "
        "UI','Noto "
        "Sans';font-size:10pt;}QTabWidget::pane{border:0;background:white;}QTabBar::tab{padding:"
        "12px "
        "14px;background:#6650b7;color:white;border:0;}QTabBar::tab:selected{background:white;"
        "color:#5940a6;}QGroupBox{background:white;border:1px solid "
        "#e1dcec;border-radius:8px;margin-top:12px;padding-top:14px;font-weight:600;}QGroupBox::"
        "title{subcontrol-origin:margin;left:12px;padding:0 "
        "5px;background:white;}QLabel,QCheckBox{background:transparent;}QPushButton,QToolButton{"
        "background:#eee9fb;border:1px solid transparent;border-radius:8px;padding:6px "
        "12px;}QToolButton{padding:5px;}QPushButton:hover,QToolButton:hover{background:#e0d7f6;"
        "border-color:#cbbce9;}QPushButton[primary=true]{background:#6750bd;color:white;}"
        "QPushButton:disabled,QToolButton:disabled{background:#f2eff7;color:#aba4b9;}QLineEdit,"
        "QPlainTextEdit,QDoubleSpinBox,QSpinBox,QComboBox{background:#fbfaff;border:1px solid "
        "#d8d0e9;border-radius:5px;padding:5px;selection-background-color:#8a74ce;}QSlider::groove:"
        "horizontal{height:5px;background:#e1daef;border-radius:2px;}QSlider::handle:horizontal{"
        "background:#7259c1;width:13px;margin:-4px "
        "0;border-radius:6px;}QScrollArea{border:0;}QProgressBar{border:0;background:#eeeaf5;"
        "height:5px;}QProgressBar::chunk{background:#7960c5;border-radius:2px;}QMenu{background:"
        "white;border:1px solid #d5cce8;}QMenu::item:selected{background:#ede7f8;}"
        "QComboBox{padding-right:24px;}QComboBox::drop-down{border:0;width:24px;}"
        "QComboBox::down-arrow{image:url(:/chevron-down.svg);width:12px;height:12px;}"
        "QDoubleSpinBox::up-button,QDoubleSpinBox::down-button{border:0;width:18px;background:#"
        "eee9fb;}"
        "QDoubleSpinBox::up-arrow{image:url(:/chevron-up.svg);width:10px;height:10px;}"
        "QDoubleSpinBox::down-arrow{image:url(:/chevron-down.svg);width:10px;height:10px;}"
        "QToolButton[sfActionEnabled=false]{background:#f2eff7;border-color:transparent;}"
        "QCheckBox::indicator{width:18px;height:18px;border:2px solid "
        "#a395c5;border-radius:4px;background:white;}"
        "QCheckBox::indicator:checked{border-color:#6750bd;background:#6750bd;image:url(:/"
        "check.svg);}"
        "QTabBar{background:#6650b7;}QTabBar::tab{padding:12px 10px;}");
    auto* root = new QWidget;
    setCentralWidget(root);
    auto* layout = new QVBoxLayout(root);
    layout->setContentsMargins(18, 12, 18, 12);
    layout->setSpacing(10);
    navigation = new QTabBar;
    navigation->setExpanding(true);
    navigation->setDrawBase(false);
    navigation->setUsesScrollButtons(true);
    navigation->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    layout->addWidget(navigation);
    paths = new QWidget;
    auto* pathLayout = new QGridLayout(paths);
    pathLayout->setContentsMargins(0, 0, 0, 0);
    source = new QLineEdit;
    output = new QLineEdit;
    source->setPlaceholderText(t("source"));
    output->setPlaceholderText(t("output"));
    auto* sourceLabel = new QLabel(t("source"));
    labels << qMakePair(sourceLabel, QString("source"));
    pathLayout->addWidget(sourceLabel, 0, 0);
    pathLayout->addWidget(source, 0, 1);
    auto* outputLabel = new QLabel(t("output"));
    labels << qMakePair(outputLabel, QString("output"));
    pathLayout->addWidget(outputLabel, 1, 0);
    pathLayout->addWidget(output, 1, 1);
    auto* files = new QPushButton("Файл");
    auto* folder = new QPushButton("Папка");
    auto* target = new QPushButton("Выбрать");
    pathLayout->addWidget(files, 0, 2);
    pathLayout->addWidget(folder, 0, 3);
    pathLayout->addWidget(target, 1, 2, 1, 2);
    controls << files << folder << target;
    connect(files, &QPushButton::clicked, this, [this] {
        QString path = QFileDialog::getOpenFileName(this, "Аудиофайл", {}, audioFilter());
        if (!path.isEmpty()) {
            source->setText(path);
            if (output->text().isEmpty())
                output->setText(QFileInfo(path).absolutePath() + "/SonicForgeProgect");
        }
    });
    connect(folder, &QPushButton::clicked, this, [this] {
        QString path = QFileDialog::getExistingDirectory(this, "Папка с музыкой");
        if (!path.isEmpty()) {
            source->setText(path);
            if (output->text().isEmpty())
                output->setText(path + "/SonicForgeProgect");
        }
    });
    connect(target, &QPushButton::clicked, this, [this] {
        auto path = QFileDialog::getExistingDirectory(this, "Папка результата");
        if (!path.isEmpty())
            output->setText(path);
    });
    layout->addWidget(paths);
    auto* mode = row(layout);
    linked = new QCheckBox("Связь с редактором");
    linked->setProperty("sfHelpTitle", "Связь с редактором");
    linked->setProperty("sfHelpKey", "Связь с редактором");
    mode->addWidget(linked);
    mode->addSpacing(12);
    mode->addWidget(new QLabel("Формат монтажа"));
    mixFormat = new QComboBox;
    mixFormat->setProperty("sfHelpTitle", "Формат монтажа");
    mixFormat->setProperty("sfHelpKey", "Формат монтажа");
    mixFormat->addItems({"MP3", "WAV", "M4A"});
    mode->addWidget(mixFormat);
    mode->addStretch();
    auto* native = new QLabel(QCoreApplication::applicationVersion());
    native->setStyleSheet("color:#90869f;font-size:9pt;");
    mode->addWidget(native);
    tabs = new QTabWidget;
    tabs->tabBar()->hide();
    layout->addWidget(tabs, 1);
    buildEditor(page("tab_editor"));
    buildMetadata(page("tab_metadata"));
    buildAudio(page("tab_audio"));
    buildCover(page("tab_cover"));
    buildLyrics(page("tab_lyrics"));
    buildProcessing(page("tab_processing"));
    buildHelp(page("tab_help"));
    buildSettings(page("tab_settings"));
    auto* footer = row(layout);
    status = new QLabel("Готово");
    status->setWordWrap(true);
    footer->addWidget(status, 1);
    cancelButton = new QPushButton("Остановить задачу");
    cancelButton->setEnabled(false);
    connect(cancelButton, &QPushButton::clicked, this, [this] { cancel->store(true); });
    footer->addWidget(cancelButton);
    progressBar = new QProgressBar;
    progressBar->setRange(0, 1000);
    progressBar->setValue(0);
    progressBar->setTextVisible(false);
    progressBar->setFixedHeight(5);
    layout->addWidget(progressBar);
    player = new QMediaPlayer(this);
    audioOutput = new QAudioOutput(this);
    audioOutput->setVolume(.8);
    player->setAudioOutput(audioOutput);
    connect(player, &QMediaPlayer::positionChanged, this, [this](qint64 position) {
        QSignalBlocker blocker(playerSeek);
        playerSeek->setValue(int(position));
        playerClock->setText(sf::timestamp(position / 1000.) + " / " +
                             sf::timestamp(player->duration() / 1000.));
        if (playingTimeline) {
            timeline->cursor = qMin(timeline->project.duration(), playerOrigin + position / 1000.);
            if (selectionArmed)
                timeline->selection = qMakePair(selectionStart, timeline->cursor);
            timeline->viewport()->update();
            updateState();
        }
    });
    connect(player, &QMediaPlayer::durationChanged, this,
            [this](qint64 duration) { playerSeek->setRange(0, int(duration)); });
    connect(player, &QMediaPlayer::mediaStatusChanged, this,
            [this](QMediaPlayer::MediaStatus state) {
                if (pendingSeek &&
                    (state == QMediaPlayer::LoadedMedia || state == QMediaPlayer::BufferedMedia)) {
                    qint64 position = *pendingSeek;
                    pendingSeek.reset();
                    playingTimeline = seekIsTimeline;
                    player->setPosition(position);
                    player->play();
                }
            });
    connect(player, &QMediaPlayer::errorOccurred, this,
            [this](QMediaPlayer::Error, const QString& message) {
                if (!message.isEmpty())
                    status->setText(localize(message));
            });
    connect(playerSeek, &QSlider::sliderMoved, player, &QMediaPlayer::setPosition);
    connect(linked, &QCheckBox::toggled, this, [this](bool value) {
        stop();
        playingTimeline = false;
        player->stop();
        player->setSource({});
        playerContext.clear();
        source->setEnabled(!value);
        mixFormat->setEnabled(!busy);
        workingSignature.clear();
    });
    mixFormat->setEnabled(true);
    connect(mixFormat, &QComboBox::currentIndexChanged, this, [this] { audioDirty = true; scheduleComparison(); markDirty(); });
    connect(navigation, &QTabBar::currentChanged, tabs, &QTabWidget::setCurrentIndex);
    connect(tabs, &QTabWidget::currentChanged, navigation, &QTabBar::setCurrentIndex);
    connect(tabs, &QTabWidget::currentChanged, this,
            [this](int index) { paths->setVisible(index != 0); });
    paths->setVisible(false);
    qApp->installEventFilter(this);
    auto* helpShortcut = new QShortcut(QKeySequence(Qt::Key_F1), this);
    connect(helpShortcut, &QShortcut::activated, this, [this] { tabs->setCurrentIndex(6); });
    source->setProperty("sfHelpTitle", "Источник");
    output->setProperty("sfHelpTitle", "Папка назначения");
    for (auto* widget : findChildren<QWidget*>()) {
        if (widget->property("sfHelpTitle").isValid() || widget->property("sfAction").isValid())
            continue;
        QString title;
        if (auto* button = qobject_cast<QAbstractButton*>(widget))
            title = button->text();
        else if (auto* label = qobject_cast<QLabel*>(widget))
            title = label->text();
        if (!title.isEmpty() && title.size() < 100 && !title.contains('<'))
            widget->setProperty("sfHelpTitle", title);
    }
    retranslate();
    updateState();
    setupRecovery();
    auto* fileMenu = menuBar()->addMenu("Проект");
    fileMenu->addAction("Открыть проект…", QKeySequence::Open, this, [this] { openProject(); });
    fileMenu->addAction("Сохранить проект", QKeySequence::Save, this, [this] { saveProject(); });
    fileMenu->addAction("Сохранить проект как…", QKeySequence::SaveAs, this, [this] { const auto path = QFileDialog::getSaveFileName(this, localize("Сохранить проект как…"), projectPath, "Sonic Forge (*.sfproject)"); if (!path.isEmpty()) saveProject(path); });
    connect(lyrics, &QPlainTextEdit::textChanged, this, &Window::markDirty);
    for (auto* field : metadataFields) connect(field, &QLineEdit::textEdited, this, &Window::markDirty);
    for (auto* field : numbers) connect(field, qOverload<double>(&QDoubleSpinBox::valueChanged), this, &Window::markDirty);
    for (auto* field : checks) connect(field, &QCheckBox::toggled, this, &Window::markDirty);
    for (auto* field : choices) connect(field, &QComboBox::currentIndexChanged, this, &Window::markDirty);
    const auto preferences = QJsonDocument::fromJson(QSettings().value("workspace/preferences").toByteArray()).object();
    restoring = true;
    for (auto it = numbers.begin(); it != numbers.end(); ++it) if (preferences["numbers"].toObject().contains(it.key())) { QSignalBlocker block(it.value()); it.value()->setValue(preferences["numbers"].toObject()[it.key()].toDouble()); }
    for (auto it = choices.begin(); it != choices.end(); ++it) if (preferences["choices"].toObject().contains(it.key())) { QSignalBlocker block(it.value()); it.value()->setCurrentIndex(qBound(0, preferences["choices"].toObject()[it.key()].toInt(), it.value()->count()-1)); }
    for (auto it = checks.begin(); it != checks.end(); ++it) if (preferences["checks"].toObject().contains(it.key()) && !it.key().startsWith("cover_")) { QSignalBlocker block(it.value()); it.value()->setChecked(preferences["checks"].toObject()[it.key()].toBool()); }
    restoreGeometry(QSettings().value("window/geometry").toByteArray());
    for (auto* field : numbers) syncValueControls(field);
    retranslate();
    restoring = false;
    connect(source, &QLineEdit::textChanged, this, [this] {
        if (restoring || busy) return;
        if (!QFileInfo(source->text()).isFile()) { markDirty(); return; }
        stop(); player->setSource({}); playerContext.clear(); pendingSeek.reset();
        if (!lyricSource.isEmpty() && lyricSource != source->text() && !lyrics->toPlainText().isEmpty()) {
            const auto root = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/lyric-drafts";
            if (!QDir().mkpath(root)) throw sf::Error("Не удалось сохранить черновик текста");
            const auto key = QString::fromLatin1(QCryptographicHash::hash(lyricSource.toUtf8(), QCryptographicHash::Sha256).toHex());
            QSaveFile draft(root + "/" + key + ".json");
            if (!draft.open(QIODevice::WriteOnly) || draft.write(QJsonDocument(QJsonObject{{"source", lyricSource}, {"text", lyricText()}}).toJson()) < 0 || !draft.commit()) throw sf::Error("Не удалось сохранить черновик текста");
            lyrics->clear(); lyricTimes.clear();
            status->setText(localize("Источник изменён. Предыдущий текст сохранён в черновике этой песни."));
        }
        if (lyricSource != source->text()) {
            QSignalBlocker block(lyricTrack); lyricTrack->clear(); lyricTrack->addItem(localize("Основная (und)"), "und|");
            const auto key = QString::fromLatin1(QCryptographicHash::hash(source->text().toUtf8(), QCryptographicHash::Sha256).toHex());
            QFile draft(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/lyric-drafts/" + key + ".json");
            if (draft.open(QIODevice::ReadOnly)) { const auto text = QJsonDocument::fromJson(draft.readAll()).object()["text"].toString(); lyricTimes = sf::parseLyrics(text, false); lyrics->setPlainText(showTimes->isChecked() ? text : sf::plainLyrics(text)); }
        }
        lyricSource = source->text(); workingSignature.clear(); markDirty();
    });
}
void Window::buildEditor(QWidget* page) {
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(12, 14, 12, 12);
    layout->setSpacing(10);
    auto* title = new QLabel("Аудиоредактор");
    title->setStyleSheet("font-size:17pt;font-weight:600;");
    layout->addWidget(title);
    auto* imports = row(layout);
    tool(imports, "add", "Добавить аудио", "Ctrl+I. Добавить аудиофайлы. Исходники не изменяются.",
         [this] {
             auto files = QFileDialog::getOpenFileNames(this, "Добавить аудио", {}, audioFilter());
             if (!files.isEmpty())
                 importAudio(files);
         });
    tool(imports, "undo", "Отменить", "Ctrl+Z. Отменить последнюю правку.",
         [this] { history(false); });
    tool(imports, "redo", "Повторить", "Ctrl+Y. Вернуть отменённую правку.",
         [this] { history(true); });
    tool(imports, "stems", "Вокал и инструменты", "Разделить выбранный фрагмент на составляющие.",
         [this] {
             QMenu menu;
             auto* two = menu.addAction("Вокал + инструменты");
             auto* four = menu.addAction("Вокал / ударные / бас / остальное");
             auto* action = menu.exec(QCursor::pos());
             if (action == two)
                 separateSelected(true);
             else if (action == four)
                 separateSelected(false);
         });
    imports->addStretch();
    tool(imports, "settings", "Действия с фрагментом",
         "Громкость, обрезка, положение, копирование и новый проект.", [this] {
             QMenu menu;
             auto* gain = menu.addAction(localize("Громкость, скорость и эквалайзер…"));
             auto* trim = menu.addAction(localize("Оставить выделение"));
             auto* position = menu.addAction(localize("Положение фрагмента…"));
             auto* duplicate = menu.addAction(localize("Дублировать"));
             for (auto* action : {gain, trim, position, duplicate})
                 action->setEnabled(!timeline->selected.isEmpty());
             menu.addSeparator();
             auto* fresh = menu.addAction(localize("Новый проект"));
             auto* chosen = menu.exec(QCursor::pos());
             if (!chosen)
                 return;
             if (chosen == fresh) {
                 remember();
                 timeline->project = {};
                 timeline->selected.clear();
                 timeline->cursor = 0;
                 projectChanged();
                 return;
             }
             if (chosen == duplicate) {
                 edit("duplicate");
                 return;
             }
             if (chosen == gain) {
                 fragmentSettings();
                 return;
             }
             auto clip = timeline->project.get(timeline->selected);
             if (chosen == trim) {
                 if (!timeline->selection)
                     return;
                 double a = qMax(clip.position,
                                 qMin(timeline->selection->first, timeline->selection->second));
                 double b = qMin(clip.position + clip.duration(),
                                 qMax(timeline->selection->first, timeline->selection->second));
                 if (b - a < .01)
                     return;
                 remember();
                 auto& current = timeline->project.get(clip.id);
                 double rate = clip.speed > 0 ? clip.speed : 1;
                 current.start += (a - clip.position) * rate;
                 current.end = clip.start + (b - clip.position) * rate;
                 current.position = a;
                 current.fadeIn = qMin(current.fadeIn, current.duration());
                 current.fadeOut = qMin(current.fadeOut, current.duration() - current.fadeIn);
             } else {
                 bool ok = false;
                 double value = QInputDialog::getDouble(
                     this, localize(chosen->text()), chosen == gain ? "dB" : localize("Позиция, с"),
                     chosen == gain ? clip.gain : clip.position, chosen == gain ? -60 : 0,
                     chosen == gain ? 24 : 86400, 3, &ok);
                 if (!ok)
                     return;
                 if (chosen == position)
                     value =
                         timeline->project.freePosition(clip.lane, value, clip.duration(), clip.id);
                 remember();
                 auto& current = timeline->project.get(clip.id);
                 if (chosen == gain)
                     current.gain = value;
                 else
                     current.position = value;
             }
             projectChanged();
         });
    auto* hint = new QLabel("Правая кнопка + движение — выделение   ·   Ctrl + колесо — масштаб");
    hint->setStyleSheet("color:#8b819c;font-size:9pt;");
    layout->addWidget(hint);
    timeline = new Timeline;
    timeline->setMinimumHeight(160);
    timeline->setMaximumHeight(420);
    layout->addWidget(timeline);
    auto* navigation = row(layout);
    counter = new QLabel;
    navigation->addWidget(counter);
    navigation->addStretch();
    tool(navigation, "zoom-out", "Уменьшить масштаб", "Ctrl + колесо вниз.",
         [this] { timeline->zoomBy(1 / 1.5); });
    tool(navigation, "zoom-in", "Увеличить масштаб", "Ctrl + колесо вверх.",
         [this] { timeline->zoomBy(1.5); });
    tool(navigation, "fit", "Весь проект", "Показать всю длину проекта.",
         [this] { timeline->fit(); });
    auto* tools = row(layout);
    tool(tools, "fade-in", "Плавное начало",
         "Плавно увеличивает громкость начала выбранного фрагмента.", [this] { fade(true); });
    tool(tools, "fade-out", "Плавный конец",
         "Плавно уменьшает громкость конца выбранного фрагмента.", [this] { fade(false); });
    tool(tools, "crossfade", "Плавный переход",
         "Соединяет выбранную песню со следующей на той же дорожке: перекрытие до 2 секунд и "
         "выравнивание громкости у стыка.",
         [this] { transition(); });
    selectButton = tool(tools, "select", "Выделение",
                        "Первое нажатие отмечает начало у курсора, второе — конец. Также можно "
                        "удерживать правую кнопку мыши и вести по дорожке.",
                        [this] { selectCursor(); });
    tool(tools, "split", "Разделить", "Ctrl+K. Разделить выбранный фрагмент в позиции курсора.",
         [this] { edit("split"); });
    tool(tools, "delete", "Удалить",
         "Delete. Вырезает выделенный участок; без выделения удаляет фрагмент. Ctrl+Z отменяет "
         "действие.",
         [this] { edit("delete"); });
    tools->addStretch();
    auto* range = row(layout);
    range->addWidget(new QLabel("Выделение, с"));
    rangeStart = new QDoubleSpinBox;
    rangeEnd = new QDoubleSpinBox;
    for (auto* spin : {rangeStart, rangeEnd}) {
        spin->setRange(0, 14400);
        spin->setDecimals(3);
        spin->setSingleStep(.001);
        spin->setFixedWidth(116);
        range->addWidget(spin);
    }
    tool(range, "check", "Подтвердить выделение", "Время относительно начала выбранного фрагмента.",
         [this] {
             if (timeline->selected.isEmpty())
                 return;
             auto c = timeline->project.get(timeline->selected);
             double a = rangeStart->value(), b = rangeEnd->value();
             if (a < 0 || b > c.duration() || b - a < .01)
                 throw sf::Error("Границы должны находиться внутри фрагмента");
             timeline->selection = qMakePair(c.position + a, c.position + b);
             timeline->refresh();
         });
    range->addStretch();
    auto* transport = row(layout);
    playButton = tool(transport, "play", "Прослушать",
                      "Пробел. Прослушать монтаж с красного курсора.", [this] { preview(true); });
    button(transport, "Слушать выделение / 30 с", [this] { previewRange(); });
    tool(transport, "stop", "Остановить", "Остановить звук, сохранив позицию курсора.",
         [this] { stop(); });
    transport->addStretch();
    tool(transport, "export", "Экспорт", "Ctrl+E. Сохранить монтаж в новый WAV, MP3 или M4A.",
         [this] { exportAudio(); });
    layout->addStretch(1);
    connect(timeline, &Timeline::imported, this, &Window::importAudio);
    connect(timeline, &Timeline::editStarted, this, [this] { dragSnapshot = timeline->project; });
    connect(timeline, &Timeline::changed, this, [this] {
        undoHistory << dragSnapshot;
        if (undoHistory.size() > 100) undoHistory.removeFirst();
        redoHistory.clear();
        projectChanged();
    });
    connect(timeline, &Timeline::stateChanged, this, &Window::updateState);
    connect(timeline, &Timeline::cursorChanged, this, [this](double value) {
        if (player && (playerContext == "editor" || playerContext == "excerpt") && !player->source().isEmpty())
            player->setPosition(qRound64(qMax(0., value - playerOrigin) * 1000));
        if (selectionArmed)
            timeline->selection = qMakePair(selectionStart, value);
        updateState();
    });
    auto shortcut = [this, page](const QKeySequence& key, std::function<void()> action) {
        auto* s = new QShortcut(key, page);
        s->setContext(Qt::WidgetWithChildrenShortcut);
        connect(s, &QShortcut::activated, this, [this, action] {
            if (!busy)
                try {
                    action();
                } catch (const std::exception& e) {
                    failure(QString::fromUtf8(e.what()));
                }
        });
    };
    shortcut(QKeySequence("Ctrl+I"), [this] {
        auto f = QFileDialog::getOpenFileNames(this, "Аудио", {}, audioFilter());
        if (!f.isEmpty())
            importAudio(f);
    });
    shortcut(QKeySequence("Ctrl+Z"), [this] { history(false); });
    shortcut(QKeySequence("Ctrl+Y"), [this] { history(true); });
    shortcut(QKeySequence("Ctrl+Shift+Z"), [this] { history(true); });
    shortcut(QKeySequence("Ctrl+K"), [this] { edit("split"); });
    shortcut(QKeySequence("Ctrl+D"), [this] { edit("duplicate"); });
    shortcut(QKeySequence("Ctrl+E"), [this] { exportAudio(); });
    auto* del = new QShortcut(QKeySequence::Delete, timeline);
    del->setContext(Qt::WidgetShortcut);
    connect(del, &QShortcut::activated, this, [this] {
        if (!busy)
            edit("delete");
    });
    auto* space = new QShortcut(QKeySequence(Qt::Key_Space), timeline);
    space->setContext(Qt::WidgetShortcut);
    connect(space, &QShortcut::activated, this, [this] { preview(true); });
    shortcut(QKeySequence(Qt::Key_Escape), [this] {
        stop();
        selectionArmed = false;
        timeline->selection.reset();
        timeline->refresh();
    });
}
void Window::buildMetadata(QWidget* page) {
    QVBoxLayout* layout;
    scrollContent(page, layout);
    auto* actions = row(layout);
    button(actions, "Прочитать", [this] { loadMetadata(); }, true);
    button(actions, "Очистить поля", [this] {
        for (auto* field : metadataFields) { field->clear(); field->setModified(true); }
    });
    check(actions, "overwrite_genre", "Перезаписать жанр", false);
    auto* automaticGenre = check(actions, "auto_genre", "Определять жанр автоматически · MSD", false);
    automaticGenre->setToolTip("MSD musicnn: Rock, Pop, Jazz, Metal и другие жанры обученной модели. Это вероятностная подсказка; редкие жанры могут не определяться.");
    check(actions, "overwrite_metadata", "Перезаписать все метаданные", false);
    actions->addStretch();
    auto* box = group(layout, "Метаданные");
    auto* form = new QFormLayout(box);
    form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    for (auto pair : QList<QPair<QString, QString>>{{"title", "Название"},
                                                    {"artist", "Исполнитель"},
                                                    {"album", "Альбом"},
                                                    {"album_artist", "Исполнитель альбома"},
                                                    {"composer", "Композитор"},
                                                    {"genre", "Жанр"},
                                                    {"date", "Год"},
                                                    {"track", "Трек"},
                                                    {"disc", "Диск"},
                                                    {"comment", "Комментарий"},
                                                    {"publisher", "Издатель"},
                                                    {"copyright", "Авторские права"}}) {
        auto* field = new QLineEdit;
        metadataFields[pair.first] = field;
        field->setProperty("sfHelpTitle", pair.second);
        field->setProperty("sfHelpKey", pair.first);
        if (pair.first == "title")
            field->setPlaceholderText("Если пусто — название из тегов, иначе имя файла");
        if (pair.first == "genre")
            field->setPlaceholderText(
                "Если пусто — сохранится жанр из тегов или определится по звуку");
        form->addRow(pair.second, field);
    }
    auto* preserved =
        new QLabel("Текст песни и таймкоды всегда сохраняются при изменении метаданных.");
    preserved->setWordWrap(true);
    preserved->setStyleSheet("color:#8b819c;");
    layout->addWidget(preserved);
    layout->addStretch();
}
void Window::buildAudio(QWidget* page) {
    QVBoxLayout* layout;
    scrollContent(page, layout);
    audioSliders = true;
    auto* actions = row(layout);
    button(actions, "Анализировать", [this] { analyzeAudio(); }, true);
    button(actions, "Применить пресет публикации", [this] {
        numbers["lufs"]->setValue(measurements.value("suggestedLufs").toDouble(-14));
        numbers["peak"]->setValue(measurements.value("suggestedTruePeak").toDouble(-1.5));
        checks["limiter"]->setChecked(true);
        checks["auto_noise"]->setChecked(false);
        numbers["highpass"]->setValue(measurements["bassFraction"].toDouble() > .8 ? 30 : 0);
    });
    actions->addStretch();
    analysisLabel = new QLabel("Анализ ещё не выполнен");
    analysisLabel->setWordWrap(true);
    layout->addWidget(analysisLabel);
    auto* main = group(layout, "Звук");
    auto* form = new QFormLayout(main);
    auto* profile = choice(form, "profile", "Характер",
                           {"Сбалансированный", "Тёплый", "Яркий", "Плотный", "Мягкий", "Вокал"});
    number(form, "intensity", "Интенсивность, %", 50, 0, 100, 1);
    number(form, "lufs", "Громкость, LUFS", -14, -30, -5, .1);
    number(form, "peak", "Пиковый уровень, dBTP", -1.5, -9, 0, .1);
    number(form, "lra", "Диапазон громкости, LU", 11, 1, 20, .1);
    number(form, "gain", "Итоговая громкость", 1, 0, 4, .01);
    number(form, "bass", "Бас, dB", 0, -18, 18, .1);
    number(form, "mid", "Средние частоты, dB", 0, -18, 18, .1);
    number(form, "treble", "Высокие частоты, dB", 0, -18, 18, .1);
    number(form, "width", "Ширина стерео", 1, 0, 2, .05);
    auto applyProfile = [this, profile] {
        int index = profile->currentIndex();
        double intensity = numbers["intensity"]->value() / 100;
        static const double values[][3]{{0, 0, 0}, {3, -.5, -1.5}, {-1, 0, 3},
                                        {2, 1, 1}, {1, -1, -2},    {-1, 2, 1}};
        numbers["bass"]->setValue(values[index][0] * intensity);
        numbers["mid"]->setValue(values[index][1] * intensity);
        numbers["treble"]->setValue(values[index][2] * intensity);
    };
    connect(profile, &QComboBox::currentIndexChanged, this,
            [applyProfile](int) { applyProfile(); });
    connect(numbers["intensity"], qOverload<double>(&QDoubleSpinBox::valueChanged), this,
            [applyProfile](double) { applyProfile(); });
    auto* advanced = disclosure(layout, "Фильтры и эффекты · дополнительные настройки");
    advanced->setObjectName("audioAdvanced");
    auto* effects = new QVBoxLayout(advanced);
    auto* flags = row(effects);
    check(flags, "denoise", "Убирать шум", false);
    check(flags, "auto_noise", "Автоматический шумоподавитель · экспериментальный", false);
    check(flags, "limiter", "Ограничитель пиков", true);
    check(flags, "compressor", "Компрессор", false);
    auto* columns = row(effects);
    auto* left = new QFormLayout;
    auto* right = new QFormLayout;
    columns->addLayout(left, 1);
    columns->addLayout(right, 1);
    number(left, "noise_strength", "Шумоподавление, dB", 4, 0, 30, .5);
    number(left, "pitch", "Тональность, полутона", 0, -12, 12, .1);
    number(left, "speed", "Скорость", 1, .25, 4, .05);
    number(left, "reverb", "Реверберация", 0, 0, .8, .01);
    number(left, "fade_in", "Плавное начало, с", 0, 0, 60, .1);
    number(left, "fade_out", "Плавный конец, с", 0, 0, 60, .1);
    number(right, "threshold", "Порог компрессора, dB", -18, -60, 0, .5);
    number(right, "ratio", "Сжатие", 3, 1, 20, .1);
    number(right, "attack", "Атака, мс", 20, .01, 200, .5);
    number(right, "release", "Восстановление, мс", 250, 1, 2000, 1);
    number(right, "makeup", "Усиление компрессора, dB", 0, 0, 24, .5);
    number(right, "highpass", "Срез снизу, Hz", 0, 0, 500, 1);
    number(right, "lowpass", "Срез сверху, Hz", 0, 0, 22000, 1);
    choice(right, "rate", "Частота дискретизации", {"Как в оригинале", "44100", "48000", "96000"});
    choice(right, "channels", "Каналы", {"Как в оригинале", "Моно", "Стерео"});
    choice(right, "quality", "Качество MP3", {"Максимальное", "Высокое", "Стандартное"});
    choice(right, "output_format", "Формат обработанных файлов", {"MP3", "WAV", "FLAC", "M4A", "Opus"});
    number(right, "preview_seconds", "Предпросмотр, с · 0 весь файл", 30, 0, 120, 1);
    number(right, "preview_start", "Начало предпросмотра, с", 0, 0, 86400, .1);
    audioSliders = false;
    originalPane = new AudioPane("Оригинал");
    layout->addWidget(originalPane);
    originalPane->message->setText("Выберите песню или включите связь с редактором");
    processedPane = new AudioPane("Изменённый");
    layout->addWidget(processedPane);
    processedPane->hide();
    comparisonTimer = new QTimer(this);
    comparisonTimer->setSingleShot(true);
    comparisonTimer->setInterval(650);
    connect(comparisonTimer, &QTimer::timeout, this, &Window::compareAudio);
    for (auto it = numbers.begin(); it != numbers.end(); ++it)
        connect(it.value(), qOverload<double>(&QDoubleSpinBox::valueChanged), this, [this] {
            audioDirty = true;
            scheduleComparison();
        });
    for (auto it = checks.begin(); it != checks.end(); ++it)
        if (QStringList{"denoise", "auto_noise", "limiter", "compressor"}.contains(it.key()))
            connect(it.value(), &QCheckBox::toggled, this, [this] {
                audioDirty = true;
                scheduleComparison();
            });
    for (const auto& key : {"rate", "channels", "quality"})
        connect(choices[key], &QComboBox::currentIndexChanged, this, [this] {
            audioDirty = true;
            scheduleComparison();
        });
    connect(source, &QLineEdit::textChanged, this, [this] { scheduleComparison(); });
    connect(linked, &QCheckBox::toggled, this, [this] { scheduleComparison(); });
    connect(tabs, &QTabWidget::currentChanged, this, [this](int i) {
        if (i == 2)
            scheduleComparison();
    });
    for (auto* pane : {originalPane, processedPane})
        connect(pane->media, &QMediaPlayer::playbackStateChanged, this,
                [this, pane](QMediaPlayer::PlaybackState state) {
                    if (state == QMediaPlayer::PlayingState) {
                        player->pause();
                        (pane == originalPane ? processedPane : originalPane)->media->pause();
                    }
                });
    layout->addStretch();
}
void Window::buildCover(QWidget* page) {
    QVBoxLayout* layout;
    scrollContent(page, layout);
    auto* actions = row(layout);
    button(actions, "Предпросмотр обложки", [this] { generateCover(); }, true);
    auto* textButton = button(actions, "Текст и оформление…", [this] {
        if (coverArtwork.background.isNull()) generateCover(true);
        else coverTextSettings();
    });
    textButton->setObjectName("coverTextButton");
    button(actions, "Выбрать изображение", [this] {
        QString file = QFileDialog::getOpenFileName(this, "Обложка", {},
                                                    "Изображения (*.png *.jpg *.jpeg *.webp)");
        if (!file.isEmpty()) {
            customCoverFile = file;
            auto metadata = metadataValues();
            QString song = linked->isChecked() && !timeline->project.clips.isEmpty()
                               ? timeline->project.clips.first().labelSource() : source->text();
            sf::Metadata tags;
            if (QFileInfo(song).isFile()) tags = sf::readMetadata(song);
            tags = sf::coverMetadata(song, tags);
            for (auto i = metadata.begin(); i != metadata.end(); ++i)
                if (!i.value().isEmpty()) tags.values[i.key()] = i.value();
            coverArtwork = sf::coverArtworkFromImage(QImage(file), tags, currentCoverOptions());
            // Keep an imported picture intact until its lettering is enabled.
            checks["cover_title"]->setChecked(false);
            checks["cover_artist"]->setChecked(false);
            checks["cover_symbol"]->setChecked(false);
            refreshCoverPreview();
        }
    });
    button(actions, "Сохранить PNG", [this] {
        if (coverImage.isNull())
            return;
        QString target =
            QFileDialog::getSaveFileName(this, "Сохранить обложку", "cover.png", "PNG (*.png)");
        if (!target.isEmpty() && !coverImage.save(target, "PNG"))
            throw sf::Error("Не удалось сохранить обложку");
    });
    actions->addStretch();
    auto* columns = row(layout);
    auto* box = new QGroupBox("Генерация");
    columns->addWidget(box, 1);
    auto* form = new QFormLayout(box);
    choice(form, "cover_pattern", "Узор",
           {"M2Pv1 — классический", "M2Pv2 — органический", "M2Pv3 — структура песни"},
           coverOptions.pattern);
    choice(form, "cover_color", "Цвет",
           {"M2Pv1", "M2Pv2", "M2Pv3 — скорость ритма", "Своя палитра", "Оригинальная палитра узора"}, coverOptions.colorSource);
    auto* paletteActions = new QHBoxLayout;
    form->addRow(paletteActions);
    auto* paletteButton = button(paletteActions, "Настроить палитру…", [this] { coverSettings(); });
    paletteButton->setObjectName("coverPaletteButton");
    paletteActions->addStretch();
    paletteButton->setVisible(coverOptions.colorSource == 3);
    connect(choices["cover_color"], &QComboBox::currentIndexChanged, paletteButton,
            [paletteButton](int index) { paletteButton->setVisible(index == 3); });
    number(form, "cover_size", "Размер, px", coverOptions.size, 128, 4096, 1);
    number(form, "cover_seed", "Seed", coverOptions.seed, 0, 2147483647, 1);
    auto* advancedLayout = new QVBoxLayout;
    form->addRow(advancedLayout);
    auto* advanced = disclosure(advancedLayout, "Дополнительные настройки обложки");
    advanced->setObjectName("coverAdvanced");
    form = new QFormLayout(advanced);
    number(form, "cover_detail", "Детализация", coverOptions.detail, 0, 100, 1);
    number(form, "cover_contrast", "Контраст, %", coverOptions.contrast, 50, 150, 1);
    number(form, "cover_saturation", "Насыщенность, %", coverOptions.saturation, 0, 150, 1);
    number(form, "cover_softness", "Мягкость, %", coverOptions.softness, 0, 100, 1);
    auto* flags = new QVBoxLayout;
    form->addRow(flags);
    check(flags, "cover_title", "Писать название", coverOptions.title);
    check(flags, "cover_artist", "Писать исполнителя", coverOptions.artist);
    check(flags, "cover_symbol", "Показывать символ", coverOptions.symbol);
    coverPreview = new CoverPreview;
    coverPreview->setMinimumSize(320, 320);
    coverPreview->setMaximumSize(440, 440);
    columns->addWidget(coverPreview, 1, Qt::AlignTop);
    for (const auto& key : {"cover_title", "cover_artist", "cover_symbol"})
        connect(checks[key], &QCheckBox::toggled, this, [this] {
            if (!coverArtwork.background.isNull()) {
                try { refreshCoverPreview(); } catch (const std::exception& error) { failure(QString::fromUtf8(error.what())); }
            }
        });
    auto invalidateTexture = [this] {
        if (customCoverFile.isEmpty()) { coverArtwork.background = {}; coverImage = {}; lastCover.clear(); coverPreview->setImage({}); }
    };
    for (const auto& key : {"cover_pattern", "cover_color"})
        connect(choices[key], &QComboBox::currentIndexChanged, this, [invalidateTexture](int) { invalidateTexture(); });
    for (const auto& key : {"cover_size", "cover_seed", "cover_detail", "cover_contrast", "cover_saturation", "cover_softness"})
        connect(numbers[key], qOverload<double>(&QDoubleSpinBox::valueChanged), this, [invalidateTexture](double) { invalidateTexture(); });
    layout->addStretch();
}
void Window::buildLyrics(QWidget* page) {
    QVBoxLayout* layout;
    scrollContent(page, layout);
    layout->setContentsMargins(12, 14, 12, 12);
    auto* actions = row(layout);
    button(actions, "Открыть готовый", [this] { loadLyrics(); });
    button(actions, "Распознать / исправить тайминги", [this] { recognizeLyrics(); }, true);
    button(actions, "Сохранить текст", [this] { saveLyrics(); });
    button(actions, "Импорт TXT/LRC", [this] {
        auto file = QFileDialog::getOpenFileName(this, "Текст песни", {}, "Текст (*.txt *.lrc)");
        if (!file.isEmpty()) {
            QFile input(file);
            if (!input.open(QIODevice::ReadOnly))
                throw sf::Error(input.errorString());
            QString text = sf::readTextFile(file);
            text.remove(QChar(0xfeff));
            lyrics->setPlainText(text);
            lyricTimes = sf::parseLyrics(text, false);
            showTimes->setChecked(!lyricTimes.isEmpty());
        }
    });
    tool(actions, "copy", "Скопировать текст", "Копирует весь текст песни в буфер обмена.",
         [this] { QApplication::clipboard()->setText(lyrics->toPlainText()); });
    actions->addStretch();
    auto* options = row(layout);
    lyricFormat = new QComboBox;
    lyricFormat->addItems({"В песню (MP3, USLT)", "LRC", "TXT"});
    lyricFormat->setMinimumContentsLength(23);
    lyricFormat->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    auto updateLyricFormat = [this] {
        const bool available = linked->isChecked() || QFileInfo(source->text()).suffix().compare("mp3", Qt::CaseInsensitive) == 0;
        if (auto* model = qobject_cast<QStandardItemModel*>(lyricFormat->model())) model->item(0)->setEnabled(available);
        if (!available && lyricFormat->currentIndex() == 0) lyricFormat->setCurrentIndex(2);
    };
    connect(source, &QLineEdit::textChanged, lyricFormat, updateLyricFormat);
    connect(linked, &QCheckBox::toggled, lyricFormat, updateLyricFormat);
    options->addWidget(lyricFormat);
    lyricLanguage = new QComboBox;
    lyricLanguage->setMinimumContentsLength(22);
    lyricLanguage->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    for (auto pair : QList<QPair<QString, QString>>{{"Авто — русский звук", "other_ru"},
                                                    {"Авто — латиница", "other_en"},
                                                    {"Русский", "ru"},
                                                    {"English", "en"},
                                                    {"Español", "es"},
                                                    {"Deutsch", "de"},
                                                    {"Français", "fr"},
                                                    {"Italiano", "it"},
                                                    {"Português", "pt"},
                                                    {"ქართული", "ka"},
                                                    {"Авто — исходный текст", "auto"}})
        lyricLanguage->addItem(pair.first, pair.second);
    options->addWidget(lyricLanguage);
    lyricMode = new QComboBox;
    lyricMode->addItems({"Распознавание", "Коррекция таймингов"});
    options->addWidget(lyricMode);
    lyricQuality = new QComboBox;
    lyricQuality->addItems({"Точнее", "Быстрее"});
    lyricQuality->setProperty("sfHelpTitle", "Качество распознавания");
    lyricQuality->setProperty("sfHelpKey", "speech_quality");
    lyricQuality->setCurrentIndex(QSettings().value("lyrics/quality", 0).toInt() == 1 ? 1 : 0);
    connect(lyricQuality, &QComboBox::currentIndexChanged, this,
            [](int value) { QSettings().setValue("lyrics/quality", value); });
    options->addWidget(lyricQuality);
    options->addStretch();
    auto* tracks = row(layout);
    tracks->addWidget(new QLabel(localize("Версия встроенного текста")));
    lyricTrack = new QComboBox; lyricTrack->addItem(localize("Основная (und)"), "und|"); tracks->addWidget(lyricTrack, 1);
    connect(lyricTrack, &QComboBox::currentIndexChanged, this, [this](int index) {
        const int previous = lyricTrack->property("sfPreviousTrack").toInt();
        if (previous >= 0 && previous < lyricTrack->count() && previous != index) lyricTrack->setItemData(previous, lyricText(), Qt::UserRole + 1);
        lyricTrack->setProperty("sfPreviousTrack", index);
        const auto text = lyricTrack->itemData(index, Qt::UserRole + 1).toString();
        lyricTimes = sf::parseLyrics(text, false); lyrics->setPlainText(showTimes->isChecked() ? text : sf::plainLyrics(text)); markDirty();
    });
    auto* flags = row(layout);
    overwriteLyrics = check(flags, "overwrite_lyrics", "Перезаписать готовый текст", false);
    showTimes = check(flags, "show_times", "Показывать таймкоды", true);
    separateVocals = check(flags, "vocals_first", "Отделять вокал перед распознаванием", true);
    flags->addStretch();
    auto* timing = row(layout);
    timing->addWidget(new QLabel("Время mm:ss.xxx"));
    stamp = new QLineEdit("00:00.00");
    stamp->setFixedWidth(110);
    timing->addWidget(stamp);
    button(timing, "Вставить таймкод", [this] { insertStamp(false, false); });
    button(timing, "Метка сейчас · F8", [this] { insertStamp(true, true); });
    timing->addStretch();
    lyrics = new QPlainTextEdit;
    lyrics->setPlaceholderText("Текст сохраняется при переключении вкладок и правках дорожек.");
    lyrics->setMinimumHeight(160);
    layout->addWidget(lyrics, 1);
    auto* transport = row(layout);
    tool(transport, "play", "Слушать / пауза",
         "Слушать исходную песню или монтаж редактора. Повторное нажатие — пауза.",
         [this] { preview(false); });
    tool(transport, "stop", "Остановить", "Остановить прослушивание.", [this] { stop(); });
    playerSeek = new QSlider(Qt::Horizontal);
    playerSeek->setRange(0, 0);
    transport->addWidget(playerSeek, 1);
    playerClock = new QLabel("00:00.00 / 00:00.00");
    transport->addWidget(playerClock);
    auto* f8 = new QShortcut(QKeySequence(Qt::Key_F8), page);
    f8->setContext(Qt::WidgetWithChildrenShortcut);
    connect(f8, &QShortcut::activated, this, [this] {
        if (!busy)
            insertStamp(true, true);
    });
    connect(showTimes, &QCheckBox::toggled, this, [this](bool timed) {
        QString text = lyrics->toPlainText();
        auto cursor = lyrics->textCursor();
        if (!timed) {
            auto parsed = sf::parseLyrics(text, false);
            if (!parsed.isEmpty())
                lyricTimes = parsed;
            lyrics->setPlainText(sf::plainLyrics(text));
        } else {
            QSignalBlocker block(showTimes); showTimes->setChecked(false);
            const auto canonical = lyricText(); showTimes->setChecked(true);
            lyrics->setPlainText(canonical);
        }
        cursor.setPosition(qMin(cursor.position(), lyrics->toPlainText().size()));
        lyrics->setTextCursor(cursor);
    });
}
void Window::buildProcessing(QWidget* page) {
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(12, 14, 12, 12);
    auto* actions = row(layout);
    check(actions, "process_metadata", "Метаданные", true);
    check(actions, "process_audio", "Звук", false);
    check(actions, "process_lyrics", "Текст", true);
    check(actions, "process_cover", "Обложка", true);
    actions->addStretch();
    button(actions, "Запустить", [this] { processFiles(); }, true);
    log = new QPlainTextEdit;
    log->setReadOnly(true);
    log->setPlaceholderText("Здесь появится журнал обработки.");
    layout->addWidget(log, 1);
    auto* bottom = row(layout);
    button(bottom, "Скопировать журнал",
           [this] { QApplication::clipboard()->setText(log->toPlainText()); });
    button(bottom, "Очистить журнал", [this] { log->clear(); });
    bottom->addStretch();
}
void Window::buildHelp(QWidget* page) {
    auto* layout = new QVBoxLayout(page);
    auto* help = new QTextBrowser;
    help->setOpenExternalLinks(true);
    help->setStyleSheet(
        "QTextBrowser{background:white;border:1px solid #e1dcec;border-radius:12px;padding:20px;}");
    help->document()->setDefaultStyleSheet(
        "body{color:#393047;font-size:11pt;line-height:1.5} h2{color:#6550b9;font-size:24pt} "
        "h3{color:#6550b9;font-size:14pt;margin-top:24px;} "
        "p{margin-top:16px;margin-bottom:18px} a{color:#6750bd} b{color:#6550b9}");
    help->setHtml(
        "<h2>SonicForge · Справка</h2><p>Монтаж, обработка и оформление вашей "
        "музыки.</p><h3>Монтаж на дорожках</h3><p>Добавьте аудио, выберите фрагмент. Удерживайте "
        "правую кнопку мыши для выделения. Ctrl + колесо меняет масштаб. Основные инструменты: "
        "плавное начало, плавный конец, переход к следующей песне той же дорожки, выделение, "
        "разделение, удаление. Правый клик по иконке или настройке показывает название и "
        "описание.</p><p>Ctrl+Z "
        "— отмена, Ctrl+Y — повтор, Ctrl+K — разделение, Delete — удалить, Ctrl+E — экспорт. "
        "Пробел на дорожке — воспроизведение. Перемещение красной линии сразу перематывает "
        "звук.</p><h3>Один источник для всех разделов</h3><p>Связь с редактором включает текущий "
        "монтаж как "
        "источник для остальных разделов. Текст и вручную изменённые таймкоды при правках не "
        "стираются.</p><h3>Текст и таймкоды</h3><p>В разделе текста слушайте песню и нажимайте F8 "
        "в начале строки: метка "
        "ставится на 45 мс раньше звука, затем курсор переходит на следующую строку. Ручной "
        "ввод времени сохраняется точно. Коррекция таймингов сохраняет ваши слова и "
        "повторы.</p><h3>Звук и оформление</h3><p>Ползунки меняют звук; ниже настроек можно "
        "послушать оригинал и обновлённый результат. Свёрнутые фильтры продолжают работать. "
        "Дополнительные настройки обложки позволяют отключить надпись и "
        "символ.</p><h3>Сохранение</h3><p>Метаданные, звук, текст и обложка применяются к копиям в "
        "разделе "
        "«Выполнение». Исходные аудиофайлы не изменяются. Запись текста отдельной кнопкой изменяет "
        "текстовый тег выбранной песни.</p><p>Модели работают локально и включены в выпуск. "
        "При отсутствии Whisper или HTDemucs модель загружается с проверкой контрольной суммы. "
        "Распознавание может ошибаться; "
        "прослушайте и проверьте текст перед сохранением.</p><p><a "
        "href='https://github.com/dumuzeyn/SonicForge'>Репозиторий и обновления</a></p>");
    help->setProperty("sfHelp", true);
    help->setProperty("sfRussianHtml", help->toHtml());
    layout->addWidget(help);
}
void Window::buildSettings(QWidget* page) {
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(20, 20, 20, 20);
    layout->setSpacing(18);
    auto* appearance = group(layout, "Интерфейс");
    auto* form = new QFormLayout(appearance);
    auto* languageBox = new QComboBox;
    languageBox->setObjectName("interfaceLanguage");
    languageBox->setProperty("sfIgnoreWheel", true);
    languageBox->addItems({"Русский", "English"});
    languageBox->setCurrentIndex(language == "en" ? 1 : 0);
    form->addRow("Язык интерфейса", languageBox);
    auto* quota = new QSpinBox; quota->setRange(1, 128); quota->setValue(QSettings().value("cache/maxGiB", 8).toInt()); quota->setSuffix(" GiB");
    form->addRow(localize("Квота рабочего кэша"), quota);
    connect(quota, &QSpinBox::valueChanged, this, [](int value) { QSettings().setValue("cache/maxGiB", value); });
    auto* cacheActions = row(layout);
    button(cacheActions, "Очистить неиспользуемый кэш", [this] { cleanWorkingCache(); sf::cleanCache(); });
    button(cacheActions, "Очистить историю отмены", [this] { undoHistory.clear(); redoHistory.clear(); cleanWorkingCache(); updateState(); });
    connect(languageBox, &QComboBox::currentIndexChanged, this, [this](int i) {
        language = i ? "en" : "ru";
        loadLanguage();
        QStringList keys{"tab_editor", "tab_metadata",   "tab_audio", "tab_cover",
                         "tab_lyrics", "tab_processing", "tab_help",  "tab_settings"};
        for (int j = 0; j < keys.size(); ++j)
            tabs->setTabText(j, t(keys[j]));
        retranslate();
        savePreferences();
    });
    auto* about =
        new QLabel("<h1 style='color:#6550b9'>SonicForge</h1><p>Музыка, монтаж и оформление — в "
                   "одном месте.</p><p style='color:#8b819c'>Обработка выполняется на вашем "
                   "компьютере. Аудиозаписи не отправляются на сервер.</p>");
    about->setWordWrap(true);
    layout->addWidget(about);
    auto* resources = group(layout, "Проект и поддержка");
    auto* card = new QVBoxLayout(resources);
    auto* links = row(card);
    button(links, "GitHub",
           [] { QDesktopServices::openUrl(QUrl("https://github.com/dumuzeyn/SonicForge")); });
    button(links, "Обновления", [] {
        QDesktopServices::openUrl(QUrl("https://github.com/dumuzeyn/SonicForge/releases"));
    });
    button(
        links, "Поддержать автора",
        [] { QDesktopServices::openUrl(QUrl("https://pay.cloudtips.ru/p/53cc3806")); }, true);
    auto* notice = new QLabel(
        "Поддержка автора добровольная. Все возможности приложения доступны без пожертвования.");
    notice->setWordWrap(true);
    notice->setStyleSheet("color:#8b819c;");
    card->addWidget(notice);
    links->addStretch();
    layout->addStretch();
}

void Window::failure(const QString& message) {
    if (status)
        status->setText(localize(message));
    if (log)
        appendLog("Ошибка: " + message);
    QMessageBox::warning(this, "SonicForge", localize(message));
}
void Window::appendLog(const QString& message) {
    if (log)
        log->appendPlainText(localize(message));
}
void Window::startTask(const QString& name, std::function<WorkResult(sf::Progress)> work,
                       std::function<void(const WorkResult&)> finished) {
    if (busy)
        return;
    comparisonTimer->stop();
    comparisonCancel->store(true);
    stop();
    busy = true;
    cancel = std::make_shared<std::atomic_bool>(false);
    timeline->busy = true;
    status->setText(localize(name));
    appendLog(name);
    progressBar->setRange(0, 0);
    cancelButton->setEnabled(true);
    for (auto* control : controls)
        enableAction(control, false);
    linked->setEnabled(false);
    mixFormat->setEnabled(false);
    lyrics->setReadOnly(true);
    updateInputs(false);
    watcher = new QFutureWatcher<WorkResult>(this);
    QPointer<Window> safe(this);
    sf::Progress progress = [safe](QString message, double fraction) {
        if (!safe)
            return;
        QMetaObject::invokeMethod(
            safe,
            [safe, message, fraction] {
                if (!safe)
                    return;
                if (!message.isEmpty())
                    safe->status->setText(safe->localize(message));
                if (fraction >= 0) {
                    safe->progressBar->setRange(0, 1000);
                    safe->progressBar->setValue(qRound(fraction * 1000));
                }
            },
            Qt::QueuedConnection);
    };
    connect(watcher, &QFutureWatcher<WorkResult>::finished, this, [this, finished] {
        auto result = watcher->result();
        watcher->deleteLater();
        watcher = nullptr;
        busy = false;
        timeline->busy = false;
        for (auto* control : controls)
            enableAction(control, true);
        linked->setEnabled(true);
        mixFormat->setEnabled(true);
        lyrics->setReadOnly(false);
        updateInputs(true);
        cancelButton->setEnabled(false);
        progressBar->setRange(0, 1000);
        progressBar->setValue(result.error.isEmpty() ? 1000 : 0);
        if (!result.error.isEmpty()) {
            status->setText(localize(result.error));
            appendLog(result.error);
            if (!cancel->load())
                QMessageBox::warning(this, "SonicForge", localize(result.error));
        } else {
            status->setText(localize("Готово"));
            if (finished)
                try {
                    finished(result);
                } catch (const std::exception& e) {
                    failure(QString::fromUtf8(e.what()));
                }
        }
        updateState();
        cleanWorkingCache();
    });
    auto previousComparison =
        comparisonWatcher ? comparisonWatcher->future() : QFuture<WorkResult>();
    watcher->setFuture(QtConcurrent::run([work, progress, previousComparison]() mutable {
        try {
            previousComparison.waitForFinished();
            return work(progress);
        } catch (const std::exception& e) {
            WorkResult result;
            result.error = QString::fromUtf8(e.what());
            return result;
        } catch (...) {
            WorkResult result;
            result.error = "Не удалось завершить операцию";
            return result;
        }
    }));
}
void Window::remember() {
    undoHistory << timeline->project;
    if (undoHistory.size() > 100)
        undoHistory.removeFirst();
    redoHistory.clear();
}
void Window::projectChanged() {
    markDirty();
    scheduleComparison();
    stop();
    if (player) {
        playingTimeline = false;
        player->stop();
        player->setSource({});
        playerContext.clear();
    }
    workingSignature.clear();
    timeline->selection.reset();
    selectionArmed = false;
    timeline->refresh();
    updateState();
}
void Window::history(bool redo) {
    if (busy)
        return;
    auto& from = redo ? redoHistory : undoHistory;
    auto& to = redo ? undoHistory : redoHistory;
    if (from.isEmpty())
        return;
    to << timeline->project;
    timeline->project = from.takeLast();
    if (!timeline->selected.isEmpty()) {
        bool exists = false;
        for (auto& c : timeline->project.clips)
            exists |= c.id == timeline->selected;
        if (!exists)
            timeline->selected.clear();
    }
    projectChanged();
}
void Window::updateState() {
    if (!timeline || !counter)
        return;
    counter->setText(sf::timestamp(timeline->cursor) + " / " +
                     sf::timestamp(timeline->project.duration()));
    for (auto* control : controls) {
        auto* tool = qobject_cast<QToolButton*>(control);
        if (!tool)
            continue;
        QString name = tool->property("sfAction").toString();
        if (name == "Отменить")
            enableAction(tool, !busy && !undoHistory.isEmpty());
        else if (name == "Повторить")
            enableAction(tool, !busy && !redoHistory.isEmpty());
        else if (QStringList{"Плавное начало", "Плавный конец", "Плавный переход", "Выделение",
                             "Разделить", "Удалить", "Вокал и инструменты"}
                     .contains(name))
            enableAction(tool, !busy && !timeline->selected.isEmpty());
    }
    if (selectButton)
        selectButton->setIcon(sf::icon(selectionArmed ? "check" : "select",
                                       selectButton->property("sfActionEnabled").toBool()
                                           ? QColor("#6550b9")
                                           : QColor("#b0a7c3")));
    if (rangeStart && rangeEnd) {
        QSignalBlocker a(rangeStart), b(rangeEnd);
        if (!timeline->selected.isEmpty()) {
            try {
                auto c = timeline->project.get(timeline->selected);
                rangeStart->setMaximum(c.duration());
                rangeEnd->setMaximum(c.duration());
                if (timeline->selection) {
                    rangeStart->setValue(
                        qMax(0., qMin(timeline->selection->first, timeline->selection->second) -
                                     c.position));
                    rangeEnd->setValue(qMin(c.duration(), qMax(timeline->selection->first,
                                                               timeline->selection->second) -
                                                              c.position));
                }
                rangeStart->setEnabled(!busy);
                rangeEnd->setEnabled(!busy);
            } catch (...) {
            }
        } else {
            rangeStart->setEnabled(false);
            rangeEnd->setEnabled(false);
        }
    }
}
void Window::openFiles(const QStringList& files) {
    if (files.isEmpty())
        return;
    tabs->setCurrentIndex(0);
    if (source->text().isEmpty())
        source->setText(files.first());
    if (output->text().isEmpty())
        output->setText(QFileInfo(files.first()).absolutePath() + "/SonicForgeProgect");
    importAudio(files);
}
void Window::importAudio(const QStringList& files, int lane, double at) {
    if (files.isEmpty() || busy)
        return;
    startTask(
        "Читаю аудио и строю волну…",
        [this, files](sf::Progress progress) {
            WorkResult result;
            for (int i = 0; i < files.size(); ++i) {
                sf::checkpoint(cancel);
                result.sources << sf::readSource(files[i], cancel);
                progress("Читаю " + QFileInfo(files[i]).fileName(), double(i + 1) / files.size());
            }
            return result;
        },
        [this, lane, at](const WorkResult& result) {
            remember();
            int target =
                lane < 0 ? timeline->project.clips.isEmpty() ? 0 : timeline->project.lanes() : lane;
            double position = at;
            for (auto& s : result.sources) {
                timeline->selected = timeline->project.add(s, target, position);
                if (lane < 0)
                    target++;
                else if (position >= 0)
                    position += s.duration;
            }
            if (source->text().isEmpty() && !result.sources.isEmpty())
                source->setText(result.sources.first().path);
            if (output->text().isEmpty() && !result.sources.isEmpty())
                output->setText(QFileInfo(result.sources.first().path).absolutePath() +
                                "/SonicForgeProgect");
            projectChanged();
            timeline->fit();
        });
}
void Window::edit(const QString& operation) {
    if (busy || timeline->selected.isEmpty())
        return;
    const auto clip = timeline->project.get(timeline->selected);
    if (operation == "delete" && timeline->selection) {
        double a = qMax(clip.position,
                        qMin(timeline->selection->first, timeline->selection->second)),
               b = qMin(clip.position + clip.duration(),
                        qMax(timeline->selection->first, timeline->selection->second));
        if (b - a < .01)
            throw sf::Error("Выделение должно пересекать выбранный фрагмент");
        if (b - a >= .01 && clip.duration() - (b - a) >= .01) {
            auto snapshot = timeline->project;
            startTask(
                "Вырезаю выделение…",
                [this, snapshot, clip, a, b](sf::Progress) {
                    WorkResult result;
                    result.sources << sf::cutAudio(snapshot, clip, a, b, cancel);
                    return result;
                },
                [this, clip](const WorkResult& result) {
                    remember();
                    auto replacement = result.sources.first();
                    timeline->project.sources[replacement.path] = replacement;
                    auto& c = timeline->project.get(clip.id);
                    c.source = replacement.path;
                    c.start = 0;
                    c.end = replacement.duration;
                    c.speed = 1;
                    c.originalSource = clip.labelSource();
                    double total = c.fadeIn + c.fadeOut;
                    if (total > c.duration()) {
                        c.fadeIn *= c.duration() / total;
                        c.fadeOut *= c.duration() / total;
                    }
                    projectChanged();
                });
            return;
        }
    }
    remember();
    if (operation == "split")
        timeline->selected = timeline->project.split(clip.id, timeline->cursor);
    else if (operation == "duplicate") {
        auto duplicate = clip;
        duplicate.id = QUuid::createUuid().toString(QUuid::Id128);
        duplicate.position = timeline->project.freePosition(
            duplicate.lane, clip.position + clip.duration(), duplicate.duration());
        timeline->project.clips << duplicate;
        timeline->selected = duplicate.id;
    } else if (operation == "delete") {
        timeline->project.clips.removeIf([&](const sf::Clip& c) { return c.id == clip.id; });
        timeline->selected.clear();
    }
    projectChanged();
}
void Window::fade(bool incoming) {
    if (timeline->selected.isEmpty() || busy)
        return;
    auto clip = timeline->project.get(timeline->selected);
    double maximum = clip.duration() - (incoming ? clip.fadeOut : clip.fadeIn);
    bool ok = false;
    double value = QInputDialog::getDouble(
        this, incoming ? "Плавное начало" : "Плавный конец", "Длительность, с · 0 отключает",
        (incoming ? clip.fadeIn : clip.fadeOut) > 0 ? (incoming ? clip.fadeIn : clip.fadeOut)
                                                    : qMin(2., maximum),
        0, maximum, 3, &ok, {}, .05);
    if (!ok)
        return;
    remember();
    auto& c = timeline->project.get(clip.id);
    if (incoming)
        c.fadeIn = value;
    else
        c.fadeOut = value;
    projectChanged();
}
void Window::transition() {
    if (timeline->selected.isEmpty() || busy)
        return;
    auto first = timeline->project.get(timeline->selected);
    QList<sf::Clip> next;
    for (auto& c : timeline->project.clips)
        if (c.lane == first.lane && c.position >= first.position + first.duration() - 1e-8)
            next << c;
    std::sort(next.begin(), next.end(), [](auto& a, auto& b) { return a.position < b.position; });
    if (next.isEmpty())
        throw sf::Error("Добавьте следующую песню на ту же дорожку");
    auto second = next.first();
    auto snapshot = timeline->project;
    startTask(
        "Создаю плавный переход…",
        [this, snapshot, first, second](sf::Progress) {
            WorkResult result;
            result.sources << sf::crossfade(snapshot, first, second, cancel);
            return result;
        },
        [this, first, second](const WorkResult& result) {
            remember();
            auto source = result.sources.first();
            timeline->project.sources[source.path] = source;
            auto joined = first;
            joined.source = source.path;
            joined.start = 0;
            joined.end = source.duration;
            joined.gain = joined.fadeIn = joined.fadeOut = 0;
            joined.volume = joined.speed = 1;
            joined.bass = joined.mid = joined.treble = 0;
            joined.originalSource = first.labelSource();
            timeline->project.clips.removeIf(
                [&](const sf::Clip& c) { return c.id == first.id || c.id == second.id; });
            timeline->project.clips << joined;
            timeline->selected = joined.id;
            projectChanged();
            timeline->fit();
        });
}
void Window::separateSelected(bool two) {
    if (timeline->selected.isEmpty() || busy)
        return;
    auto clip = timeline->project.get(timeline->selected);
    auto snapshot = timeline->project;
    startTask(
        "Разделяю вокал и инструменты…",
        [this, snapshot, clip, two](sf::Progress p) {
            sf::Project single = snapshot;
            auto c = clip;
            c.position = 0;
            single.clips = {c};
            single.muted.clear();
            auto input = sf::render(single, sf::uniqueFile(), cancel);
            WorkResult result;
            result.files = sf::separate(input, two, cancel, p);
            for (auto& file : result.files)
                result.sources << sf::readSource(file, cancel);
            QFile::remove(input);
            return result;
        },
        [this, clip](const WorkResult& result) {
            remember();
            int nextLane = timeline->project.lanes();
            timeline->project.clips.removeIf([&](const sf::Clip& c) { return c.id == clip.id; });
            for (int i = 0; i < result.sources.size(); ++i) {
                QString id = timeline->project.add(
                    result.sources[i], i == 0 ? clip.lane : nextLane + i - 1, clip.position);
                auto& stem = timeline->project.get(id);
                stem.originalSource = clip.labelSource();
                if (i == 0)
                    timeline->selected = id;
            }
            projectChanged();
        });
}
void Window::selectCursor() {
    if (timeline->selected.isEmpty())
        return;
    auto clip = timeline->project.get(timeline->selected);
    if (!selectionArmed) {
        if (timeline->cursor < clip.position || timeline->cursor > clip.position + clip.duration())
            throw sf::Error("Курсор должен быть внутри фрагмента");
        selectionStart = timeline->cursor;
        selectionArmed = true;
        timeline->selection = qMakePair(selectionStart, selectionStart);
    } else {
        timeline->selection = qMakePair(selectionStart, timeline->cursor);
        selectionArmed = false;
    }
    timeline->refresh();
}
QString Window::prepare(const sf::Project& project, bool link, const QString& original,
                        const QString&) {
    if (!link) {
        if (!QFileInfo(original).isFile())
            throw sf::Error("Выберите один аудиофайл или включите связь с редактором");
        return original;
    }
    if (project.clips.isEmpty())
        throw sf::Error("В редакторе нет аудио");
    QByteArray revisions;
    for (auto it = project.sources.begin(); it != project.sources.end(); ++it) {
        QFileInfo info(it.key());
        revisions += it.key().toUtf8() + '\0' + QByteArray::number(info.size()) + ':' +
                     QByteArray::number(info.lastModified().toMSecsSinceEpoch()) + '\n';
    }
    QString signature = QString::fromLatin1(
        QCryptographicHash::hash(QJsonDocument(project.json()).toJson(QJsonDocument::Compact) +
                                      revisions,
                                 QCryptographicHash::Sha256)
            .toHex());
    if (workingSignature == signature && QFile::exists(workingFile))
        return workingFile;
    const auto previousFile = workingFile;
    workingFile = sf::render(project, sf::uniqueFile(".wav"), cancel);
    // The rendered mix has a temporary UUID filename. Carry the original song's
    // tags and fallback title so every consumer, including artwork, sees its name.
    if (!previousFile.isEmpty() && previousFile != workingFile) QFile::remove(previousFile);
    workingSignature = signature;
    return workingFile;
}
void Window::playFile(const QString& file, bool editor, const QString& context, double origin) {
    playerOrigin = origin;
    pendingSeek = editor ? qRound64(qMax(0., timeline->cursor - origin) * 1000) : 0;
    seekIsTimeline = editor;
    playingTimeline = false;
    playerContext = context.isEmpty() ? (editor ? "editor" : "lyrics") : context;
    const QUrl url = QUrl::fromLocalFile(file);
    if (player->source() == url && player->mediaStatus() != QMediaPlayer::InvalidMedia) {
        qint64 position = *pendingSeek;
        pendingSeek.reset();
        playingTimeline = editor;
        player->setPosition(position);
        player->play();
    } else
        player->setSource(url);
}
void Window::preview(bool editor) {
    if (busy)
        return;
    QString desired = editor ? "editor" : "lyrics";
    if (player->playbackState() == QMediaPlayer::PlayingState && playerContext == desired) {
        player->pause();
        return;
    }
    if (!player->source().isEmpty() && playerContext == desired &&
        player->playbackState() == QMediaPlayer::PausedState) {
        player->play();
        return;
    }
    auto snapshot = timeline->project;
    bool link = editor || linked->isChecked();
    QString original = source->text(), format = "wav";
    startTask(
        "Подготавливаю прослушивание…",
        [this, snapshot, link, original, format](sf::Progress) {
            WorkResult result;
            result.file = prepare(snapshot, link, original, format);
            return result;
        },
        [this, editor](const WorkResult& result) { playFile(result.file, editor); });
}
void Window::stop() {
    if (originalPane)
        originalPane->media->pause();
    if (processedPane)
        processedPane->media->pause();
    pendingSeek.reset();
    if (player)
        player->pause();
}
void Window::previewRange() {
    if (busy || timeline->project.clips.isEmpty()) return;
    const auto snapshot = timeline->project;
    const double start = timeline->selection ? qMin(timeline->selection->first, timeline->selection->second) : timeline->cursor;
    const double duration = timeline->selection ? std::abs(timeline->selection->second - timeline->selection->first) : 30;
    startTask("Подготавливаю фрагмент…", [=, this](sf::Progress progress) {
        WorkResult result; result.file = sf::render(snapshot, sf::uniqueFile(), cancel, start, duration, progress); return result;
    }, [this, start](const WorkResult& result) { timeline->cursor = start; playFile(result.file, true, "excerpt", start); });
}
void Window::exportAudio() {
    if (busy || timeline->project.clips.isEmpty())
        return;
    QString target = QFileDialog::getSaveFileName(this, "Экспорт монтажа", "SonicForge-edit.wav",
                                                  "WAV (*.wav);;MP3 (*.mp3);;M4A (*.m4a);;FLAC (*.flac);;Opus (*.opus)");
    if (target.isEmpty())
        return;
    QDialog dialog(this); dialog.setWindowTitle(localize("Параметры экспорта"));
    auto* layout = new QVBoxLayout(&dialog); auto* form = new QFormLayout; layout->addLayout(form);
    auto* rate = new QComboBox; rate->addItems({localize("Как в исходниках"), "44100", "48000", "96000", "192000"}); form->addRow(localize("Частота, Hz"), rate);
    auto* channels = new QComboBox; channels->addItems({localize("Как в исходниках"), localize("Моно"), localize("Стерео"), "5.1", "7.1"}); form->addRow(localize("Каналы"), channels);
    auto* bits = new QComboBox; bits->addItems({"32-bit float", "24-bit PCM", "16-bit PCM"}); form->addRow(localize("Битность WAV"), bits); bits->setEnabled(QFileInfo(target).suffix().compare("wav", Qt::CaseInsensitive) == 0);
    auto* limit = new QCheckBox(localize("Ограничивать пики до −0,45 dBFS")); form->addRow(limit);
    auto* hint = new QLabel(localize("MP3 и M4A поддерживают до двух каналов. Внутренняя обработка использует float PCM; кодирование с потерями выполняется один раз.")); hint->setWordWrap(true); layout->addWidget(hint);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel); layout->addWidget(buttons); connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept); connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    if (dialog.exec() != QDialog::Accepted) return;
    sf::RenderOptions renderOptions;
    renderOptions.sampleRate = rate->currentIndex() ? rate->currentText().toInt() : 0;
    renderOptions.channels = QList<int>{0, 1, 2, 6, 8}[channels->currentIndex()];
    renderOptions.bits = QList<int>{32, 24, 16}[bits->currentIndex()]; renderOptions.limiter = limit->isChecked(); renderOptions.quality = audioOptions().quality;
    auto snapshot = timeline->project;
    for (const auto& source : snapshot.sources) if (QFileInfo(source.path).absoluteFilePath().compare(QFileInfo(target).absoluteFilePath(), Qt::CaseInsensitive) == 0) { failure(localize("Экспорт не должен заменять исходный файл проекта. Выберите другое имя.")); return; }
    startTask(
        "Экспортирую монтаж…",
        [this, snapshot, target, renderOptions](sf::Progress p) {
            WorkResult result;
            if (!QFileInfo::exists(target)) result.file = sf::render(snapshot, target, cancel, 0, -1, p, renderOptions);
            else {
                QTemporaryDir stage(QFileInfo(target).absolutePath() + "/.sf-export-XXXXXX");
                if (!stage.isValid()) throw sf::Error("Не удалось подготовить экспорт");
                const auto rendered = sf::render(snapshot, stage.filePath(QFileInfo(target).fileName()), cancel, 0, -1, p, renderOptions);
                sf::backupFile(target); sf::checkpoint(cancel);
                QFile input(rendered); QSaveFile output(target);
                if (!input.open(QIODevice::ReadOnly) || !output.open(QIODevice::WriteOnly)) throw sf::Error("Не удалось заменить файл экспорта");
                while (!input.atEnd()) { sf::checkpoint(cancel); const auto bytes = input.read(1024 * 1024); if (bytes.isEmpty() && input.error() != QFile::NoError) throw sf::Error(input.errorString()); if (output.write(bytes) != bytes.size()) throw sf::Error(output.errorString()); }
                if (!output.commit()) throw sf::Error(output.errorString());
                result.file = target;
            }
            return result;
        },
        [this](const WorkResult& result) {
            appendLog("Сохранено: " + result.file);
            status->setText("Сохранено: " + result.file);
        });
}
QMap<QString, QString> Window::metadataValues() const {
    QMap<QString, QString> values;
    for (auto i = metadataFields.begin(); i != metadataFields.end(); ++i)
        if (!i.value()->text().trimmed().isEmpty() || i.value()->isModified()) values[i.key()] = i.value()->text().trimmed();
    return values;
}
void Window::loadMetadata() {
    auto snapshot = timeline->project;
    bool link = linked->isChecked();
    QString original = source->text(), format = mixFormat->currentText().toLower();
    startTask(
        "Читаю метаданные…",
        [this, snapshot, link, original, format](sf::Progress) {
            WorkResult result;
            auto metadata = sf::readMetadata(link && !snapshot.clips.isEmpty() ? snapshot.clips.first().labelSource() : prepare(snapshot, link, original, format), cancel);
            for (auto i = metadata.values.begin(); i != metadata.values.end(); ++i)
                result.data[i.key()] = i.value();
            return result;
        },
        [this](const WorkResult& result) {
            for (auto i = metadataFields.begin(); i != metadataFields.end(); ++i)
                i.value()->setText(result.data[i.key()].toString());
        });
}
sf::AudioOptions Window::audioOptions() const {
    sf::AudioOptions o;
    o.lufs = numbers["lufs"]->value();
    o.truePeak = numbers["peak"]->value();
    o.lra = numbers["lra"]->value();
    o.gain = numbers["gain"]->value();
    o.bass = numbers["bass"]->value();
    o.mid = numbers["mid"]->value();
    o.treble = numbers["treble"]->value();
    o.width = numbers["width"]->value();
    o.denoise = checks["denoise"]->isChecked();
    o.autoDenoise = checks["auto_noise"]->isChecked();
    o.limiter = checks["limiter"]->isChecked();
    o.compressor = checks["compressor"]->isChecked();
    o.noiseStrength = numbers["noise_strength"]->value();
    o.pitch = numbers["pitch"]->value();
    o.speed = numbers["speed"]->value();
    o.reverb = numbers["reverb"]->value();
    o.fadeIn = numbers["fade_in"]->value();
    o.fadeOut = numbers["fade_out"]->value();
    o.threshold = numbers["threshold"]->value();
    o.ratio = numbers["ratio"]->value();
    o.attack = numbers["attack"]->value();
    o.release = numbers["release"]->value();
    o.makeup = numbers["makeup"]->value();
    o.highpassHz = numbers["highpass"]->value();
    o.highpass = o.highpassHz > 0;
    o.lowpassHz = numbers["lowpass"]->value();
    o.lowpass = o.lowpassHz > 0;
    o.sampleRate = choices["rate"]->currentIndex() ? choices["rate"]->currentText().toInt() : 0;
    o.channels = choices["channels"]->currentIndex();
    o.quality = choices["quality"]->currentIndex() * 2;
    return o;
}
void Window::analyzeAudio() {
    auto snapshot = timeline->project;
    bool link = linked->isChecked();
    QString original = source->text(), format = mixFormat->currentText().toLower();
    const auto options = audioOptions();
    startTask(
        "Измеряю звук…",
        [this, snapshot, link, original, format, options](sf::Progress) {
            WorkResult result;
            auto input = prepare(snapshot, link, original, format);
            result.data = sf::analyze(input, cancel);
            const QString edited = sf::uniqueFile();
            try {
                sf::normalize(input, edited, options, cancel);
                result.data["modified"] = sf::analyze(edited, cancel);
                QFile::remove(edited);
            } catch (...) {
                QFile::remove(edited);
                throw;
            }
            return result;
        },
        [this](const WorkResult& result) {
            measurements = result.data;
            analysisLabel->setText(
                QString("Средняя энергия: %1 dBFS  ·  Пики: %2 dBFS  ·  Тихие участки: "
                        "%3%\nОригинал: %4 LUFS  →  С настройками: %5 LUFS")
                    .arg(result.data["rmsDb"].toDouble(), 0, 'f', 1)
                    .arg(result.data["peakDb"].toDouble(), 0, 'f', 1)
                    .arg(result.data["quietFraction"].toDouble() * 100, 0, 'f', 1)
                    .arg(result.data["integratedLufs"].toString())
                    .arg(result.data["modified"].toObject()["integratedLufs"].toString()));
        });
}
void Window::generateCover(bool editText) {
    auto snapshot = timeline->project;
    bool link = linked->isChecked();
    QString original = source->text(), format = mixFormat->currentText().toLower();
    auto metadata = metadataValues();
    auto options = currentCoverOptions();
    startTask(
        "Создаю обложку…",
        [this, snapshot, link, original, format, metadata, options](sf::Progress) {
            QString input = prepare(snapshot, link, original, format);
            const auto tagSource = link && !snapshot.clips.isEmpty() ? snapshot.clips.first().labelSource() : input;
            auto tags = sf::coverMetadata(tagSource, sf::readMetadata(tagSource, cancel));
            for (auto i = metadata.begin(); i != metadata.end(); ++i)
                if (!i.value().isEmpty())
                    tags.values[i.key()] = i.value();
            WorkResult result;
            result.artwork = sf::makeCoverArtwork(input, tags, options, cancel);
            result.image = sf::decorateCover(result.artwork, options, cancel);
            return result;
        },
        [this, editText](const WorkResult& result) {
            lastCover = result.file;
            coverArtwork = result.artwork;
            coverImage = result.image;
            customCoverFile.clear();
            coverPreview->setImage(coverImage, sf::layoutCoverText(coverArtwork.metadata, currentCoverOptions()).bounds);
            markDirty();
            if (editText) coverTextSettings();
        });
}
void Window::coverSettings() {
    QDialog dialog(this);
    dialog.setWindowTitle("Своя палитра");
    auto* layout = new QVBoxLayout(&dialog);
    auto* list = new QListWidget;
    layout->addWidget(list);
    auto colors = coverOptions.palette;
    auto stops = coverOptions.stops;
    auto* gradient = new PaletteEditor(colors, stops, &dialog);
    layout->insertWidget(0, gradient);
    auto refresh = [&] {
        int selected = list->currentRow();
        list->clear();
        for (int i = 0; i < colors.size(); ++i) {
            auto* item = new QListWidgetItem(
                colors[i].name() + "  ·  " +
                    QString::number(stops.value(i, double(i) / qMax(1, colors.size() - 1)) * 100,
                                    'f', 1) +
                    "%",
                list);
            item->setBackground(colors[i]);
            item->setForeground(colors[i].lightness() < 128 ? Qt::white : Qt::black);
        }
        list->setCurrentRow(qBound(0, selected, int(colors.size()) - 1));
        gradient->update();
    };
    refresh();
    auto* actions = row(layout);
    button(actions, "Добавить", [&] {
        QColor color = QColorDialog::getColor(Qt::white, &dialog);
        if (color.isValid()) {
            colors << color;
            stops << 1.;
            refresh();
        }
    });
    auto editColor = [&] {
        int at = list->currentRow();
        if (at < 0)
            return;
        QColor color = QColorDialog::getColor(colors[at], &dialog);
        if (color.isValid()) {
            colors[at] = color;
            refresh();
        }
    };
    button(actions, "Изменить", editColor);
    connect(list, &QListWidget::itemDoubleClicked, &dialog,
            [&](QListWidgetItem*) { editColor(); });
    button(actions, "Удалить", [&] {
        int at = list->currentRow();
        if (at >= 0 && colors.size() > 1) {
            colors.removeAt(at);
            stops.removeAt(at);
            refresh();
        }
    });
    auto* position = new QDoubleSpinBox;
    position->setRange(0, 100);
    position->setDecimals(1);
    position->setSuffix(" %");
    auto* positionRow = new QFormLayout;
    positionRow->addRow(localize("Позиция цвета"), position);
    layout->addLayout(positionRow);
    position->setValue(stops.value(list->currentRow()) * 100);
    connect(list, &QListWidget::currentRowChanged, &dialog, [&](int i) {
        QSignalBlocker blocker(position);
        if (i >= 0)
            position->setValue(stops.value(i) * 100);
    });
    connect(position, qOverload<double>(&QDoubleSpinBox::valueChanged), &dialog, [&](double value) {
        int i = list->currentRow();
        if (i >= 0) {
            stops[i] = value / 100;
            gradient->update();
        }
    });
    gradient->changed = [&](int i) {
        refresh();
        list->setCurrentRow(i);
        QSignalBlocker blocker(position);
        position->setValue(stops[i] * 100);
    };
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel);
    layout->addWidget(buttons);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    dialog.resize(500, 400);
    if (dialog.exec() == QDialog::Accepted) {
        QList<int> indices;
        for (int i = 0; i < colors.size(); ++i)
            indices << i;
        std::stable_sort(indices.begin(), indices.end(),
                         [&](int a, int b) { return stops[a] < stops[b]; });
        coverOptions.palette.clear();
        coverOptions.stops.clear();
        for (int i : indices) {
            coverOptions.palette << colors[i];
            coverOptions.stops << stops[i];
        }
        choices["cover_color"]->setCurrentIndex(3);
        if (customCoverFile.isEmpty()) coverArtwork.background = {};
        markDirty();
        savePreferences();
    }
}
void Window::loadLyrics() {
    auto snapshot = timeline->project;
    bool link = linked->isChecked();
    QString original = source->text(), format = mixFormat->currentText().toLower();
    startTask(
        "Читаю текст песни…",
        [this, snapshot, link, original, format](sf::Progress) {
            QString input = link && !snapshot.clips.isEmpty() ? snapshot.clips.first().labelSource() : prepare(snapshot, link, original, format);
            WorkResult result;
            result.text = sf::readMetadata(input, cancel).values.value("lyrics");
            const auto metadata = sf::readMetadata(input, cancel);
            QJsonObject tracks; for (auto it = metadata.lyricTracks.cbegin(); it != metadata.lyricTracks.cend(); ++it) tracks[it.key()] = it.value(); result.data["tracks"] = tracks;
            if (result.text.isEmpty()) {
                for (auto ext : {".lrc", ".txt"}) {
                    QFile file(QFileInfo(input).absolutePath() + "/" +
                               QFileInfo(input).completeBaseName() + ext);
                    if (file.open(QIODevice::ReadOnly)) {
                        result.text = QString::fromUtf8(file.readAll());
                        break;
                    }
                }
            }
            if (result.text.isEmpty())
                throw sf::Error("Готовый текст не найден");
            if (link && !snapshot.clips.isEmpty()) {
                const auto clip = snapshot.clips.first();
                if (!clip.originalSource.isEmpty() || snapshot.clips.size() > 1) {
                    result.text = sf::plainLyrics(result.text); result.data["needsAlignment"] = true;
                } else {
                    auto lines = sf::parseLyrics(result.text, false);
                    if (!lines.isEmpty()) {
                        lines.removeIf([&](const sf::Lyric& line) { return line.start < clip.start || line.start >= clip.end; });
                        for (auto& line : lines) { line.start = clip.position + (line.start - clip.start) / (clip.speed > 0 ? clip.speed : 1); }
                        result.text = sf::lrc(lines);
                    }
                }
            }
            return result;
        },
        [this](const WorkResult& result) {
            QSignalBlocker block(lyricTrack); lyricTrack->clear();
            const auto tracks = result.data["tracks"].toObject(); for (auto it = tracks.begin(); it != tracks.end(); ++it) { lyricTrack->addItem(it.key().replace('|', " · "), it.key()); lyricTrack->setItemData(lyricTrack->count()-1, it.value().toString(), Qt::UserRole+1); }
            if (!lyricTrack->count()) { lyricTrack->addItem(localize("Основная (und)"), "und|"); lyricTrack->setItemData(0, result.text, Qt::UserRole + 1); }
            for (int i = 0; i < lyricTrack->count(); ++i) if (lyricTrack->itemData(i, Qt::UserRole + 1).toString() == result.text) { lyricTrack->setCurrentIndex(i); break; }
            lyricTrack->setProperty("sfPreviousTrack", lyricTrack->currentIndex());
            lyricTimes = sf::parseLyrics(result.text, false);
            lyrics->setPlainText(showTimes->isChecked() ? result.text
                                                        : sf::plainLyrics(result.text));
            if (result.data["needsAlignment"].toBool()) { lyricMode->setCurrentIndex(1); status->setText(localize("Текст взят из первой песни. Для изменённого монтажа выполните коррекцию таймингов.")); }
        });
}
void Window::recognizeLyrics() {
    auto snapshot = timeline->project;
    bool link = linked->isChecked(), vocals = separateVocals->isChecked(),
         align = lyricMode->currentIndex() == 1, fast = lyricQuality->currentIndex() == 1;
    QString original = source->text(), format = mixFormat->currentText().toLower(),
            lang = lyricLanguage->currentData().toString(), text = lyricText();
    if (align && sf::plainLyrics(text).isEmpty())
        throw sf::Error("Сначала введите или импортируйте текст");
    startTask(
        align ? "Исправляю тайминги готового текста…" : "Распознаю текст…",
        [this, snapshot, link, vocals, align, fast, original, format, lang, text](sf::Progress p) {
            QString input = prepare(snapshot, link, original, format);
            QString reference = vocals ? input : QString();
            if (vocals) {
                p("Выделяю вокал…", 0);
                input = sf::separate(input, true, cancel, p).first();
            }
            WorkResult result;
            result.lyrics = align ? sf::alignLyrics(input, text, lang, cancel, p, reference, fast)
                                  : sf::recognize(input, lang, cancel, p, reference, fast);
            return result;
        },
        [this](const WorkResult& result) {
            lyricTimes = result.lyrics;
            if (lyricTimes.isEmpty()) {
                status->setText("Уверенно распознанный вокал не найден. Текущий текст сохранён.");
                return;
            }
            QString text = sf::lrc(lyricTimes);
            lyrics->setPlainText(showTimes->isChecked() ? text : sf::plainLyrics(text));
        });
}
void Window::saveLyrics() {
    if (busy) return;
    QString text = lyricText();
    if (text.trimmed().isEmpty())
        throw sf::Error("Нет текста для сохранения");
    auto snapshot = timeline->project;
    bool link = linked->isChecked();
    QString original = source->text(), format = mixFormat->currentText().toLower(),
            exportFormat = lyricFormat->currentIndex() == 0   ? "embedded"
                           : lyricFormat->currentIndex() == 1 ? "lrc"
                                                              : "txt";
    if (!link && !lyricSource.isEmpty() && lyricSource != original) throw sf::Error("Текст относится к другой песне. Вернитесь к исходнику или импортируйте текст для выбранной песни.");
    QString sidecar;
    const auto track = lyricTrack->currentData().toString();
    if (exportFormat != "embedded") {
        const auto suggestion = (link ? (output->text().isEmpty() ? QDir::homePath() : output->text()) + "/SonicForge-mix" : QFileInfo(original).absolutePath() + "/" + QFileInfo(original).completeBaseName()) + "." + exportFormat;
        sidecar = QFileDialog::getSaveFileName(this, localize("Сохранить текст"), suggestion, exportFormat == "lrc" ? "LRC (*.lrc)" : "TXT (*.txt)");
        if (sidecar.isEmpty()) return;
    }
    auto restore = exportFormat == "embedded"
                       ? releaseAudioForWrite(link ? workingFile : original) : std::function<void()>([] {});
    startTask(
        "Сохраняю текст…",
        [this, snapshot, link, original, format, text, exportFormat, sidecar, track](sf::Progress) {
            WorkResult result;
            if (!sidecar.isEmpty()) { result.file = sf::saveLyricsFile(sidecar, text, exportFormat, cancel); return result; }
            if (link) { result.file = projectPath; return result; }
            result.file = prepare(snapshot, link, original, format);
            if (!link && exportFormat == "embedded") result.data["backup"] = sf::backupFile(result.file);
            result.file = sf::saveLyrics(result.file, text, exportFormat, cancel, track.section('|',0,0), track.section('|',1));
            // The tag replacement is committed. Finish synchronizing the project
            // even if cancellation arrives while hashing, or our own write looks external.
            if (snapshot.sources.contains(result.file)) { auto s = snapshot.sources.value(result.file); QFileInfo info(result.file); s.size = info.size(); s.modified = info.lastModified().toMSecsSinceEpoch(); s.fingerprint = sf::fileFingerprint(result.file); result.sources << s; }
            return result;
        },
        [this, link](const WorkResult& result) {
            for (const auto& s : result.sources) {
                timeline->project.sources[s.path] = s;
                for (auto& project : undoHistory) if (project.sources.contains(s.path)) project.sources[s.path] = s;
                for (auto& project : redoHistory) if (project.sources.contains(s.path)) project.sources[s.path] = s;
                workingSignature.clear();
            }
            lyricSource = source->text(); markDirty();
            status->setText(
                link ? "Текст сохранён в рабочем монтаже; «Выполнение» запишет его в итоговый файл."
                     : "Текст сохранён: " + result.file);
        });
    connect(watcher, &QFutureWatcher<WorkResult>::finished, this, [restore] { restore(); });
}
void Window::insertStamp(bool live, bool advance) {
    if (busy)
        return;
    double at = live ? (player && !player->source().isEmpty() && playerContext != "comparison"
                            ? playerOrigin + player->position() / 1000.
                            : timeline->cursor)
                     : sf::parseTime(stamp->text());
    if (live)
        at = qMax(0., at - sf::LyricLead);
    QString value = sf::timestamp(at, 3);
    QTextCursor cursor = lyrics->textCursor();
    cursor.beginEditBlock();
    cursor.movePosition(QTextCursor::StartOfBlock);
    cursor.movePosition(QTextCursor::EndOfBlock, QTextCursor::KeepAnchor);
    QString line = cursor.selectedText();
    line.remove(QRegularExpression("^(?:\\[\\d{1,6}:\\d{2}(?:[.:]\\d{1,3})?\\])+"));
    cursor.insertText("[" + value + "]" + line);
    cursor.endEditBlock();
    if (advance) {
        while (cursor.movePosition(QTextCursor::NextBlock)) {
            if (!cursor.block().text().trimmed().isEmpty()) {
                cursor.movePosition(QTextCursor::StartOfBlock);
                break;
            }
        }
    }
    lyrics->setTextCursor(cursor);
    lyrics->ensureCursorVisible();
    lyrics->setFocus();
    stamp->setText(value);
    QSignalBlocker blocker(showTimes);
    showTimes->setChecked(true);
}

void Window::processFiles() {
    if (busy)
        return;
    const QString original = source->text().trimmed(), destination = output->text().trimmed();
    bool link = linked->isChecked();
    if (destination.isEmpty())
        throw sf::Error("Укажите папку результата");
    if (!link && !QFileInfo::exists(original))
        throw sf::Error("Источник не найден");
    auto snapshot = timeline->project;
    QString format = mixFormat->currentText().toLower();
    auto metadata = metadataValues();
    auto audio = audioOptions();
    QString supplied = lyricText(), language = lyricLanguage->currentData().toString();
    bool timing = lyricMode->currentIndex() == 1, fastSpeech = lyricQuality->currentIndex() == 1,
         overwrite = overwriteLyrics->isChecked(), vocals = separateVocals->isChecked(),
         tags = checks["process_metadata"]->isChecked(),
         sound = checks["process_audio"]->isChecked(),
         words = checks["process_lyrics"]->isChecked(), art = checks["process_cover"]->isChecked(),
         replace = checks["overwrite_metadata"]->isChecked(), keepLyrics = true,
          replaceGenre = checks["overwrite_genre"]->isChecked(), automaticGenre = checks["auto_genre"]->isChecked();
    const QString soundFormat = link ? format : choices["output_format"]->currentText().toLower();
    if (!tags && !sound && !words && !art)
        throw sf::Error("Выберите хотя бы один этап");
    auto cover = currentCoverOptions();
    QString custom = customCoverFile;
    tabs->setCurrentIndex(5);
    startTask(
        "Обрабатываю выбранные этапы…",
        [=, this](sf::Progress progress) {
            QStringList files;
            if (link)
                files << prepare(snapshot, true, original, format);
            else if (QFileInfo(original).isFile())
                files << original;
            else {
                QDirIterator it(original, audioExtensions(), QDir::Files,
                                QDirIterator::Subdirectories);
                const QString excluded =
                    QDir::cleanPath(QFileInfo(destination).absoluteFilePath()) + "/";
                while (it.hasNext()) {
                    QString path = it.next();
                    if (!QDir::fromNativeSeparators(path).startsWith(excluded, Qt::CaseInsensitive))
                        files << path;
                }
            }
            if (files.isEmpty())
                throw sf::Error("В источнике нет аудиофайлов");
            QString destinationAbsolute = QFileInfo(destination).absoluteFilePath();
            if (QFileInfo(original).isDir() &&
                destinationAbsolute == QFileInfo(original).absoluteFilePath())
                throw sf::Error("Папка результата должна отличаться от источника");
            QDir().mkpath(QFileInfo(destinationAbsolute).absolutePath());
            QTemporaryDir staging(QFileInfo(destinationAbsolute).absolutePath() +
                                  "/.sonicforge-processing-XXXXXX");
            if (!staging.isValid())
                throw sf::Error("Не удалось создать временную папку");
            QList<QPair<QString, QString>> publishing;
            QSet<QString> names;
            QMap<QString, QString> planned;
            QStringList eligible, errors;
            for (const auto& input : files) {
                QString relative = link ? "SonicForge-mix." + format : QFileInfo(original).isDir() ? QDir(original).relativeFilePath(input) : QFileInfo(input).fileName();
                if (sound) relative = QFileInfo(relative).path() + "/" + QFileInfo(relative).completeBaseName() + "." + soundFormat;
                relative = QDir::cleanPath(relative);
                const auto target = QDir(destinationAbsolute).filePath(relative);
                if (relative.startsWith("..") || QDir::isAbsolutePath(relative) || QFileInfo::exists(target) || names.contains(target.toCaseFolded())) { errors << "Пропущено (путь или имя заняты): " + input; continue; }
                names.insert(target.toCaseFolded()); planned[input] = relative; eligible << input;
            }
            files = eligible;
            names.clear();
            if (files.isEmpty()) throw sf::Error(errors.join('\n'));
            for (int index = 0; index < files.size(); ++index) {
                sf::checkpoint(cancel);
                QString input = files[index];
                const QString relative = planned.value(input);
                QTemporaryDir track(staging.filePath(".track-XXXXXX"));
                if (!track.isValid()) throw sf::Error("Не удалось создать временную папку трека");
                QString staged = track.filePath(relative);
                QDir().mkpath(QFileInfo(staged).absolutePath());
                progress(QString("[%1/%2] %3")
                             .arg(index + 1)
                             .arg(files.size())
                             .arg(QFileInfo(input).fileName()),
                         double(index) / files.size());
                try {
                const auto tagSource = link && !snapshot.clips.isEmpty() ? snapshot.clips.first().labelSource() : input;
                auto originalTags = sf::coverMetadata(tagSource, sf::readMetadata(tagSource, cancel));
                if (sound) {
                    sf::normalize(input, staged, audio, cancel, progress);
                    if (originalTags.values.contains("lyrics")) originalTags.values["lyrics"] = sf::scaleLyrics(originalTags.values["lyrics"], audio.speed);
                    sf::writeMetadata(staged, originalTags.values, false, false, originalTags.cover,
                                      !originalTags.cover.isEmpty(), cancel);
                } else if (!QFile::copy(input, staged))
                    throw sf::Error("Не удалось скопировать исходник");
                if (tags) {
                    auto values = metadata;
                    if (values.value("title").isEmpty())
                        values["title"] = originalTags.values.value("title").isEmpty()
                                              ? QFileInfo(input).completeBaseName()
                                              : originalTags.values.value("title");
                    if (!replaceGenre && !originalTags.values.value("genre").isEmpty() &&
                        values.value("genre").isEmpty())
                        values["genre"] = originalTags.values.value("genre");
                    else if (values.value("genre").isEmpty() && automaticGenre) {
                        QString recognized = sf::genre(input, cancel, progress);
                        if (!recognized.isEmpty())
                            values["genre"] = recognized;
                        else
                            values["genre"] = originalTags.values.value("genre");
                    }
                    sf::writeMetadata(staged, values, replace, keepLyrics, {}, false, cancel);
                }
                if (words) {
                    QString existing = originalTags.values.value("lyrics");
                    if (existing.isEmpty()) {
                        for (auto ext : {".lrc", ".txt"}) {
                            QFile sidecar(QFileInfo(input).absolutePath() + "/" +
                                          QFileInfo(input).completeBaseName() + ext);
                            if (sidecar.open(QIODevice::ReadOnly)) {
                                existing = sf::readTextFile(sidecar.fileName());
                                if (sound) existing = sf::scaleLyrics(existing, audio.speed);
                                break;
                            }
                        }
                    }
                    QString text = link && !supplied.trimmed().isEmpty() ? supplied : existing;
                    if (timing) {
                        if (!text.trimmed().isEmpty()) {
                            QString speech = sound ? staged : input;
                            if (vocals) {
                                progress("Выделяю вокал…", 0);
                                speech = sf::separate(speech, true, cancel, progress).first();
                            }
                            auto aligned = sf::alignLyrics(speech, text, language, cancel, progress,
                                                           vocals ? (sound ? staged : input) : QString(), fastSpeech);
                            text = sf::lrc(aligned);
                            sf::saveLyrics(staged, text,
                                           QFileInfo(staged).suffix() == "mp3" ? "embedded" : "lrc",
                                           cancel);
                        }
                    } else if (link && !supplied.trimmed().isEmpty())
                        sf::saveLyrics(staged, sound ? sf::scaleLyrics(supplied, audio.speed) : supplied,
                                       QFileInfo(staged).suffix() == "mp3" ? "embedded"
                                       : supplied.contains(QRegularExpression("\\[\\d+:")) ? "lrc"
                                                                                           : "txt",
                                       cancel);
                    else if (existing.isEmpty() || overwrite) {
                        QString speech = sound ? staged : input;
                        if (vocals)
                            speech = sf::separate(speech, true, cancel, progress).first();
                        auto recognized = sf::recognize(speech, language, cancel, progress,
                                                        vocals ? (sound ? staged : input) : QString(), fastSpeech);
                        if (!recognized.isEmpty())
                            sf::saveLyrics(staged, sf::lrc(recognized),
                                           QFileInfo(staged).suffix() == "mp3" ? "embedded" : "lrc",
                                           cancel);
                    }
                }
                if (art) {
                    const auto suffix = QFileInfo(staged).suffix().toLower();
                    if (!QStringList{"mp3", "flac", "m4a", "ogg", "opus"}.contains(suffix))
                        throw sf::Error("Встраивание обложки недоступно для формата " + suffix.toUpper() +
                                        ". Используйте MP3, FLAC, M4A, Ogg или Opus.");
                    QImage image;
                    auto values = originalTags;
                    for (auto i = metadata.begin(); i != metadata.end(); ++i)
                        if (!i.value().isEmpty()) values.values[i.key()] = i.value();
                    if (!custom.isEmpty()) {
                        image = sf::decorateCover(sf::coverArtworkFromImage(QImage(custom), values, cover), cover, cancel);
                    } else {
                        image = sf::makeCover(input, values, cover, cancel);
                    }
                    QByteArray bytes;
                    QBuffer buffer(&bytes);
                    buffer.open(QIODevice::WriteOnly);
                    if (!image.save(&buffer, "JPEG", 94))
                        throw sf::Error("Не удалось закодировать обложку");
                    sf::writeMetadata(staged, {}, false, true, bytes, true, cancel);
                }
                QList<QPair<QString, QString>> completedTrack;
                QDirIterator generated(track.path(), QDir::Files, QDirIterator::Subdirectories);
                while (generated.hasNext()) {
                    const auto from = generated.next(), to = staging.filePath(QDir(track.path()).relativeFilePath(from));
                    QDir().mkpath(QFileInfo(to).absolutePath());
                    completedTrack << qMakePair(from, to);
                }
                sf::publishFiles(completedTrack);
                } catch (const std::exception& error) {
                    sf::checkpoint(cancel);
                    errors << QFileInfo(input).fileName() + ": " + QString::fromUtf8(error.what());
                }
            }
            sf::checkpoint(cancel);
            QDirIterator all(staging.path(), QDir::Files, QDirIterator::Subdirectories);
            while (all.hasNext()) {
                QString staged = all.next(),
                        relative = QDir(staging.path()).relativeFilePath(staged),
                        target = QDir(destinationAbsolute).filePath(relative);
                if (QFileInfo::exists(target))
                    throw sf::Error("Файл результата появился во время обработки: " + target);
            }
            QDirIterator publish(staging.path(), QDir::Files, QDirIterator::Subdirectories);
            WorkResult result;
            while (publish.hasNext()) {
                QString staged = publish.next(),
                        relative = QDir(staging.path()).relativeFilePath(staged),
                        target = QDir(destinationAbsolute).filePath(relative);
                QDir().mkpath(QFileInfo(target).absolutePath());
                publishing << qMakePair(staged, target);
                result.files << target;
            }
            sf::publishFiles(publishing);
            result.data["warnings"] = QJsonArray::fromStringList(errors);
            if (result.files.isEmpty() && !errors.isEmpty()) throw sf::Error(errors.join('\n'));
            progress("Обработка завершена", 1);
            return result;
        },
        [this](const WorkResult& result) {
            for (auto& file : result.files)
                appendLog("Сохранено: " + file);
            const auto warnings = result.data["warnings"].toArray();
            for (const auto& warning : warnings) appendLog(warning.toString());
            status->setText(localize("Готово. Файлов: ") + QString::number(result.files.size()) + (warnings.isEmpty() ? QString() : localize(" · Пропущено: ") + QString::number(warnings.size())));
        });
}
void Window::loadPreferences() {
    QSettings settings;
    language = settings.value("language", "ru").toString();
    coverOptions.symbol = settings.value("cover/symbol", true).toBool();
    QJsonObject options =
        QJsonDocument::fromJson(settings.value("cover/options").toByteArray()).object();
    if (options.isEmpty()) {
        QFile legacy(qEnvironmentVariable("LOCALAPPDATA") + "/SonicForge/custom_cover.json");
        if (legacy.open(QIODevice::ReadOnly))
            options = QJsonDocument::fromJson(legacy.readAll()).object();
    }
    auto integer = [&](const char* key, int& value) {
        if (options.contains(key))
            value = qRound(options[key].toDouble(value));
    };
    integer("detail", coverOptions.detail);
    integer("contrast", coverOptions.contrast);
    integer("saturation", coverOptions.saturation);
    integer("softness", coverOptions.softness);
    integer("size", coverOptions.size);
    integer("seed", coverOptions.seed);
    coverOptions.text = options["text"].toString();
    coverOptions.fontFamily = options["font"].toString("Unbounded");
    coverOptions.textSize = qBound(1., options["text_size"].toDouble(7.2), 20.);
    coverOptions.textX = qBound(0., options["text_x"].toDouble(50), 100.);
    coverOptions.textY = qBound(0., options["text_y"].toDouble(76), 100.);
    coverOptions.ink = QColor(options["ink"].toString());
    coverOptions.title = options["title"].toBool(true);
    coverOptions.artist = options["artist"].toBool(false);
    if (options["pattern"].isString())
        coverOptions.pattern = options["pattern"] == "legacy"   ? 0
                               : options["pattern"] == "modern" ? 1
                                                                : 2;
    else
        integer("pattern", coverOptions.pattern);
    if (options["color_source"].isString())
        coverOptions.colorSource = options["color_source"] == "custom"   ? 3
                                   : options["color_source"] == "legacy" ? 0
                                   : options["color_source"] == "modern" ? 1
                                                                         : 2;
    else
        integer("color_source", coverOptions.colorSource);
    if (!options["reference_palettes"].toBool() && coverOptions.colorSource != 3)
        coverOptions.colorSource = 4;
    QStringList palette = settings.value("cover/palette").toStringList();
    auto positions = settings.value("cover/positions").toList();
    if (palette.isEmpty()) {
        for (auto color : options["colors"].toArray())
            palette << color.toString();
        positions = options["positions"].toArray().toVariantList();
    }
    if (!palette.isEmpty()) {
        coverOptions.palette.clear();
        coverOptions.stops.clear();
        for (int i = 0; i < palette.size(); ++i) {
            QColor color(palette[i]);
            if (color.isValid()) {
                coverOptions.palette << color;
                coverOptions.stops
                    << positions.value(i, double(i) / qMax(1, palette.size() - 1)).toDouble();
            }
        }
    }
}
void Window::savePreferences() {
    QSettings settings;
    settings.setValue("language", language);
    if (checks.contains("cover_symbol"))
        settings.setValue("cover/symbol", checks["cover_symbol"]->isChecked());
    QStringList palette;
    QVariantList stops;
    for (auto& color : coverOptions.palette)
        palette << color.name();
    for (double at : coverOptions.stops)
        stops << at;
    settings.setValue("cover/palette", palette);
    settings.setValue("cover/positions", stops);
    QJsonObject options;
    options["text"] = coverOptions.text;
    options["font"] = coverOptions.fontFamily;
    options["text_size"] = coverOptions.textSize;
    options["text_x"] = coverOptions.textX;
    options["text_y"] = coverOptions.textY;
    options["ink"] = coverOptions.ink.isValid() ? coverOptions.ink.name() : QString();
    options["title"] = checks["cover_title"]->isChecked();
    options["artist"] = checks["cover_artist"]->isChecked();
    options["reference_palettes"] = true;
    for (const auto& key : {"size", "seed", "detail", "contrast", "saturation", "softness"})
        if (numbers.contains("cover_" + QString(key)))
            options[key] = numbers["cover_" + QString(key)]->value();
    if (choices.contains("cover_pattern"))
        options["pattern"] = choices["cover_pattern"]->currentIndex();
    if (choices.contains("cover_color"))
        options["color_source"] = choices["cover_color"]->currentIndex();
    settings.setValue("cover/options", QJsonDocument(options).toJson(QJsonDocument::Compact));
    const auto state = workspaceState();
    settings.setValue("workspace/preferences", QJsonDocument(QJsonObject{{"numbers", state["numbers"]}, {"checks", state["checks"]}, {"choices", state["choices"]}}).toJson());
    settings.setValue("window/geometry", saveGeometry());
}
void Window::closeEvent(QCloseEvent* event) {
    QElapsedTimer elapsed;
    elapsed.start();
    if (!closing && dirty && !property("sfTesting").toBool()) {
        const auto answer = QMessageBox::question(this, "Sonic Forge", localize("Сохранить монтаж и текст перед закрытием?"), QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Save);
        if (answer == QMessageBox::Cancel) { event->ignore(); return; }
        if (answer == QMessageBox::Save) { event->ignore(); if (busy) { failure(localize("Дождитесь завершения задачи или отмените её перед сохранением проекта.")); return; } closeAfterSave = true; saveProject(); return; }
    }
    closing = true;
    if (autosaveTimer) autosaveTimer->stop();
    comparisonTimer->stop();
    comparisonCancel->store(true);
    cancel->store(true);
    sf::shutdownWorkers();
    if ((comparisonWatcher && !comparisonWatcher->isFinished()) || (watcher && !watcher->isFinished()) || (autosaveWatcher && !autosaveWatcher->isFinished())) {
        event->ignore(); status->setText(localize("Завершаю задачи и сохраняю данные…"));
        QTimer::singleShot(50, this, &QWidget::close); return;
    }
    stop();
    player->stop();
    player->setSource({});
    originalPane->media->stop();
    originalPane->media->setSource({});
    processedPane->media->stop();
    processedPane->media->setSource({});
    savePreferences();
    disposeRecovery();
    if (property("sfCloseReport").isValid()) {
        QFile report(property("sfCloseReport").toString());
        if (report.open(QIODevice::WriteOnly))
            report.write(
                QJsonDocument(QJsonObject{{"complete", true},
                                          {"milliseconds", elapsed.elapsed()},
                                          {"task_finished", !watcher || watcher->isFinished()},
                                          {"comparison_finished",
                                           !comparisonWatcher || comparisonWatcher->isFinished()}})
                    .toJson());
    }
    event->accept();
    qApp->quit();
}
bool Window::eventFilter(QObject* object, QEvent* event) {
    if (event->type() == QEvent::Wheel && object->property("sfIgnoreWheel").toBool()) {
        event->ignore();
        return true;
    }
    if (event->type() == QEvent::ContextMenu) {
        if (qobject_cast<QLineEdit*>(object) || qobject_cast<QTextEdit*>(object) || qobject_cast<QPlainTextEdit*>(object)) return false;
        if (object->property("sfAction").isValid())
            return false;
        auto* context = static_cast<QContextMenuEvent*>(event);
        if (object == navigation) {
            const int index = navigation->tabAt(context->pos());
            if (index >= 0)
                showContextHelp(navigation, navigation->tabText(index),
                                tabs->widget(index)->property("sfHelpKey").toString(),
                                context->pos());
            return true;
        }
        for (auto* widget = qobject_cast<QWidget*>(object); widget;
             widget = widget->parentWidget()) {
            if (widget->property("sfHelpTitle").isValid()) {
                showContextHelp(widget, widget->property("sfHelpTitle").toString(),
                                widget->property("sfHelpKey").toString(),
                                widget->mapFromGlobal(context->globalPos()));
                return true;
            }
            if (qobject_cast<QMenu*>(widget))
                break;
        }
    }
    if (event->type() != QEvent::KeyPress || !tabs || tabs->currentIndex() != 0 ||
        QApplication::activeModalWidget() || busy)
        return QMainWindow::eventFilter(object, event);
    auto* key = static_cast<QKeyEvent*>(event);
    auto modifiers = key->modifiers();
    if (!(modifiers & Qt::ControlModifier) || (modifiers & Qt::AltModifier))
        return QMainWindow::eventFilter(object, event);
    auto* focus = QApplication::focusWidget();
    if (qobject_cast<QLineEdit*>(focus) || qobject_cast<QTextEdit*>(focus) ||
        qobject_cast<QPlainTextEdit*>(focus))
        return QMainWindow::eventFilter(object, event);
    quint32 code = key->nativeVirtualKey() ? key->nativeVirtualKey() : quint32(key->key());
    try {
        switch (code) {
        case 'I': {
            auto files = QFileDialog::getOpenFileNames(this, localize("Аудио"), {}, audioFilter());
            if (!files.isEmpty())
                importAudio(files);
            break;
        }
        case 'K':
            edit("split");
            break;
        case 'Z':
            history(modifiers & Qt::ShiftModifier);
            break;
        case 'Y':
            history(true);
            break;
        case 'D':
            edit("duplicate");
            break;
        case 'E':
            exportAudio();
            break;
        case 'M':
            if (!timeline->selected.isEmpty()) {
                remember();
                int lane = timeline->project.get(timeline->selected).lane;
                if (timeline->project.muted.contains(lane))
                    timeline->project.muted.remove(lane);
                else
                    timeline->project.muted.insert(lane);
                projectChanged();
            }
            break;
        default:
            return QMainWindow::eventFilter(object, event);
        }
    } catch (const std::exception& error) {
        failure(QString::fromUtf8(error.what()));
    }
    return true;
}
bool Window::smokeTest(const QString& directory) {
    setProperty("sfTesting", true);
    QDir().mkpath(directory);
    QJsonObject report;
    try {
        for (auto* button : findChildren<QToolButton*>())
            if (button->property("sfAction") == "Плавное начало") {
                auto opened = std::make_shared<bool>(false);
                const QString title = localize("Плавное начало");
                QTimer::singleShot(20, this, [opened, title] {
                    if (auto* menu = qobject_cast<QMenu*>(QApplication::activePopupWidget())) {
                        for (auto* label : menu->findChildren<QLabel*>())
                            if (label->text().contains(title) && label->text().contains("<br>"))
                                *opened = true;
                        menu->close();
                    }
                });
                QContextMenuEvent event(QContextMenuEvent::Mouse, QPoint(12, 12),
                                        button->mapToGlobal(QPoint(12, 12)));
                QApplication::sendEvent(button, &event);
                report["inactive_icon_context_help"] =
                    *opened && button->isEnabled() && !button->property("sfActionEnabled").toBool();
                break;
            }
        sf::Project test;
        auto first = test.add({"first.wav", 90, QVector<float>(2400, .4f)});
        test.add({"second.wav", 80, QVector<float>(2400, .2f)});
        timeline->project = test;
        timeline->selected = first;
        timeline->cursor = 9.75;
        timeline->refresh();
        auto clipDialog = std::make_shared<bool>(false);
        QTimer::singleShot(30, this, [=] {
            if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) {
                auto values = dialog->findChildren<QDoubleSpinBox*>();
                values.removeIf([](QDoubleSpinBox* value) { return !value->property("sfSliderControl").isValid(); });
                auto sliders = dialog->findChildren<QSlider*>();
                *clipDialog = values.size() == 5 && sliders.size() == 5 &&
                              values[0]->value() == 1 && values[1]->value() == 1 &&
                              values[0]->minimum() == 0 && values[0]->maximum() == 4 &&
                              values[1]->minimum() == 0 && values[1]->maximum() == 4;
                dialog->grab().save(directory + "/fragment-settings.png");
                if (*clipDialog) {
                    values[0]->setValue(2);
                    values[1]->setValue(2);
                    values[2]->setValue(3);
                }
                dialog->accept();
            }
        });
        fragmentSettings();
        report["fragment_sliders_and_ripple"] =
            *clipDialog && timeline->project.get(first).volume == 2 &&
            timeline->project.get(first).speed == 2 && timeline->project.get(first).bass == 3 &&
            timeline->project.clips[1].position == 45;
        history(false);
        {
            auto greenPixels = [](const QImage& image) {
                int count = 0;
                for (int y = 0; y < image.height(); ++y)
                    for (int x = 0; x < image.width(); ++x)
                        count += image.pixelColor(x, y) == QColor("#169c50");
                return count;
            };
            timeline->project.get(first).fadeIn = 5;
            timeline->refresh();
            QApplication::processEvents();
            report["editor_without_green_sound_marks"] =
                greenPixels(timeline->viewport()->grab().toImage()) == 0;
            timeline->project.get(first).fadeIn = 0;
            tabs->setCurrentIndex(2);
            processedPane->show();
            processedPane->seek->setRange(0, 10000);
            processedPane->seek->setChanges({{1, 3}, {7, 9}});
            QApplication::processEvents();
            report["sound_seek_paints_green_changes"] =
                greenPixels(processedPane->seek->grab().toImage()) > 150;
            report["original_seek_without_green_changes"] =
                originalPane->seek->changes().isEmpty() &&
                greenPixels(originalPane->seek->grab().toImage()) == 0;
            for (auto* scroll : tabs->widget(2)->findChildren<QScrollArea*>())
                scroll->ensureWidgetVisible(processedPane);
            QApplication::processEvents();
            grab().save(directory + "/sound-change-marks.png");
            processedPane->seek->setChanges({});
            processedPane->seek->setRange(0, 0);
            processedPane->hide();
            tabs->setCurrentIndex(0);
        }
        lyrics->setPlainText("Первая строка\nВторая строка");
        QTextCursor cursor = lyrics->textCursor();
        cursor.setPosition(0);
        lyrics->setTextCursor(cursor);
        insertStamp(true, true);
        report["cue_lead_45ms"] = lyrics->toPlainText().startsWith("[00:09.705]");
        report["next_line"] = lyrics->textCursor().blockNumber() == 1;
        QString text = lyrics->toPlainText();
        for (int i = 0; i < tabs->count(); ++i)
            tabs->setCurrentIndex(i);
        linked->setChecked(true);
        remember();
        timeline->project.get(first).fadeIn = .4;
        projectChanged();
        history(false);
        report["text_survives_tabs_and_edits"] = lyrics->toPlainText() == text;
        report["timeline_compact"] = timeline->height() >= 160 && timeline->height() <= 420;
        report["navigation_full_width"] = navigation->width() >= centralWidget()->width() - 40;
        report["navigation_above_controls"] =
            navigation->mapTo(this, QPoint(0, 0)).y() < linked->mapTo(this, QPoint(0, 0)).y();
        linked->setChecked(false);
        report["format_enabled_unlinked"] = mixFormat->isEnabled();
        linked->setChecked(true);
        report["audio_sliders"] = numbers["gain"]->parentWidget()->property("sfSlider").toBool();
        report["effects_collapsed"] = findChild<QWidget*>("audioAdvanced")->isHidden();
        report["cover_advanced_collapsed"] = findChild<QWidget*>("coverAdvanced")->isHidden();
        bool coverSliders = true;
        for (const auto& key : {"cover_detail", "cover_contrast", "cover_saturation", "cover_softness"})
            coverSliders &= numbers[key]->parentWidget()->property("sfSlider").toBool();
        report["cover_sliders"] = coverSliders;
        report["cover_embedding_uses_execution_step"] = !checks.contains("embed_cover") && !checks.contains("keep_cover");
        {
            const int pattern=choices["cover_pattern"]->currentIndex(),color=choices["cover_color"]->currentIndex();
            choices["cover_color"]->setCurrentIndex(2);
            choices["cover_pattern"]->setCurrentIndex((pattern+1)%3);
            report["cover_pattern_keeps_selected_color"] = choices["cover_color"]->currentIndex()==2;
            choices["cover_pattern"]->setCurrentIndex(pattern);
            choices["cover_color"]->setCurrentIndex(color);
        }
        auto* paletteButton = findChild<QPushButton*>("coverPaletteButton");
        int previousColor = choices["cover_color"]->currentIndex();
        choices["cover_color"]->setCurrentIndex(3);
        report["custom_palette_available"] = !paletteButton->isHidden();
        auto paletteWorks = std::make_shared<bool>(false);
        QTimer::singleShot(30, this, [this, paletteWorks] {
            if (auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) {
                auto* list = dialog->findChild<QListWidget*>();
                if (list && list->currentRow() == 0) {
                    QPushButton* edit = nullptr;
                    for (auto* button : dialog->findChildren<QPushButton*>())
                        if (button->text() == "Изменить") edit = button;
                    if (edit) {
                        QTimer::singleShot(30, this, [] {
                            if (auto* colors = qobject_cast<QColorDialog*>(QApplication::activeModalWidget())) {
                                colors->setCurrentColor(QColor("#ff1122"));
                                colors->accept();
                            }
                        });
                        edit->click();
                        *paletteWorks = list->item(0)->background().color() == QColor("#ff1122");
                    }
                }
                dialog->reject();
            }
        });
        coverSettings();
        report["palette_color_edit"] = *paletteWorks;
        choices["cover_color"]->setCurrentIndex(previousColor);
        auto* languageBox = findChild<QComboBox*>("interfaceLanguage");
        int languageIndex = languageBox->currentIndex();
        QWheelEvent wheel(QPointF(10,10), QPointF(languageBox->mapToGlobal(QPoint(10,10))),
                          QPoint(), QPoint(0,-120), Qt::NoButton, Qt::NoModifier,
                          Qt::NoScrollPhase, false);
        QApplication::sendEvent(languageBox, &wheel);
        report["language_ignores_mouse_wheel"] = languageBox->currentIndex() == languageIndex;
        {
            QTemporaryDir temporary;
            QString song = temporary.filePath("Ночная песня.wav");
            sf::writeWav(song, QVector<float>(8000, .01f), 8000, 1);
            sf::Project named;
            named.add(sf::readSource(song));
            auto mix = prepare(named, true, song, "mp3");
            const auto origin = named.clips.first().labelSource();
            report["linked_cover_keeps_song_title"] = sf::coverMetadata(origin, sf::readMetadata(origin)).values["title"] == "Ночная песня" && sf::readSource(mix, {}, false).bits == 32;
        }
        {
            auto previousOptions = currentCoverOptions();
            auto previousArtwork = coverArtwork;
            QImage background(512, 512, QImage::Format_RGB32);
            background.fill(QColor("#23414a"));
            sf::Metadata metadata;
            metadata.values = {{"title", "Ночная песня"}, {"artist", "SonicForge"}};
            coverArtwork = sf::coverArtworkFromImage(background, metadata, currentCoverOptions());
            auto editorWorks = std::make_shared<bool>(false);
            QTimer::singleShot(40, this, [this, directory, editorWorks] {
                auto* dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget());
                if (!dialog || dialog->objectName() != "coverTextDialog") return;
                auto* text = dialog->findChild<QPlainTextEdit*>("coverTextValue");
                auto* font = dialog->findChild<QFontComboBox*>("coverTextFont");
                auto* size = dialog->findChild<QDoubleSpinBox*>("coverTextSize");
                auto* x = dialog->findChild<QDoubleSpinBox*>("coverTextX");
                auto* y = dialog->findChild<QDoubleSpinBox*>("coverTextY");
                auto* preview = dialog->findChild<QWidget*>("coverTextPreview");
                text->setPlainText("Новая надпись");
                font->setCurrentFont(QFont("Noto Serif"));
                size->setValue(5.5);
                x->setValue(50);
                y->setValue(75);
                QPointF start(preview->width() / 2., (preview->height() - qMin(preview->width(),preview->height())) / 2. + qMin(preview->width(),preview->height()) * .75);
                QMouseEvent press(QEvent::MouseButtonPress, start, preview->mapToGlobal(start.toPoint()), Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
                QApplication::sendEvent(preview, &press);
                QMouseEvent move(QEvent::MouseMove, start + QPointF(0,-40), preview->mapToGlobal((start+QPointF(0,-40)).toPoint()), Qt::NoButton, Qt::LeftButton, Qt::NoModifier);
                QApplication::sendEvent(preview, &move);
                QMouseEvent release(QEvent::MouseButtonRelease, start+QPointF(0,-40), preview->mapToGlobal((start+QPointF(0,-40)).toPoint()), Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
                QApplication::sendEvent(preview, &release);
                *editorWorks = y->value() < 74 && text->toPlainText() == "Новая надпись" && size->value() == 5.5;
                dialog->grab().save(directory + "/cover-text-editor.png");
                dialog->accept();
            });
            coverTextSettings();
            report["cover_text_edit_font_size_and_drag"] = *editorWorks &&
                coverOptions.text == "Новая надпись" && coverOptions.fontFamily == "Noto Serif" && coverOptions.textY < 74;
            coverOptions = previousOptions;
            coverArtwork = previousArtwork;
            QSignalBlocker a(checks["cover_title"]), b(checks["cover_artist"]), c(checks["cover_symbol"]);
            checks["cover_title"]->setChecked(previousOptions.title);
            checks["cover_artist"]->setChecked(previousOptions.artist);
            checks["cover_symbol"]->setChecked(previousOptions.symbol);
        }
        double before = timeline->zoom;
        timeline->zoomBy(1.25);
        report["zoom"] = timeline->zoom > before;
        timeline->fit();
        tabs->setCurrentIndex(0);
        QApplication::processEvents();
        grab().save(directory + "/editor-native.png");
        tabs->setCurrentIndex(4);
        QApplication::processEvents();
        grab().save(directory + "/lyrics-native.png");
        for (int i : {1, 2, 3, 6, 7}) {
            tabs->setCurrentIndex(i);
            QApplication::processEvents();
            grab().save(directory + QString("/tab-%1.png").arg(i));
        }
        tabs->setCurrentIndex(3);
        choices["cover_color"]->setCurrentIndex(3);
        auto* coverAdvanced = findChild<QWidget*>("coverAdvanced");
        coverAdvanced->show();
        QApplication::processEvents();
        grab().save(directory + "/cover-custom-sliders.png");
        coverAdvanced->hide();
        choices["cover_color"]->setCurrentIndex(previousColor);
        QString previousLanguage = language;
        language = "en";
        loadLanguage();
        retranslate();
        tabs->setCurrentIndex(0);
        QApplication::processEvents();
        grab().save(directory + "/editor-en.png");
        tabs->setCurrentIndex(4);
        QApplication::processEvents();
        grab().save(directory + "/lyrics-en.png");
        language = previousLanguage;
        loadLanguage();
        retranslate();
        report["native_cpp"] = true;
        report["application_icon"] = !windowIcon().pixmap(48, 48).isNull();
#ifdef Q_OS_WIN
        if (QGuiApplication::platformName() == "windows") {
            auto handle = reinterpret_cast<HWND>(winId());
            report["taskbar_icon"] = SendMessageW(handle, WM_GETICON, ICON_BIG, 0) != 0 &&
                                     SendMessageW(handle, WM_GETICON, ICON_SMALL, 0) != 0;
        }
#endif
        bool success = true;
        for (auto it = report.begin(); it != report.end(); ++it)
            success &= it.value().toBool();
        QFile file(directory + "/ui-report.json");
        if (file.open(QIODevice::WriteOnly))
            file.write(QJsonDocument(report).toJson());
        return success;
    } catch (const std::exception& e) {
        report["error"] = QString::fromUtf8(e.what());
        QFile file(directory + "/ui-report.json");
        if (file.open(QIODevice::WriteOnly))
            file.write(QJsonDocument(report).toJson());
        return false;
    }
}
void Window::playbackSmoke(const QString& file, const QString& outputFile) {
    setProperty("sfTesting", true);
    auto report = std::make_shared<QJsonObject>();
    auto stage = std::make_shared<int>(0);
    auto elapsed = std::make_shared<QElapsedTimer>();
    elapsed->start();
    audioOutput->setVolume(0);
    linked->setChecked(true);
    timeline->project = {};
    timeline->selected = timeline->project.add(sf::readSource(file));
    timeline->cursor = 1.2;
    timeline->refresh();
    lyrics->setPlainText("Первая строка\nВторая строка");
    preview(true);
    auto* timer = new QTimer(this);
    timer->setInterval(40);
    connect(timer, &QTimer::timeout, this, [=, this] {
        if (*stage == 0 && player->playbackState() == QMediaPlayer::PlayingState &&
            player->position() >= 1200) {
            (*report)["start_at_cursor"] = player->position() < 1800;
            timeline->cursor = 2.4;
            QMetaObject::invokeMethod(timeline, "cursorChanged", Qt::DirectConnection,
                                      Q_ARG(double, 2.4));
            (*report)["red_cursor_seeks_while_playing"] =
                player->position() >= 2350 && player->position() < 2700 &&
                player->playbackState() == QMediaPlayer::PlayingState;
            preview(true);
            (*report)["pause"] = player->playbackState() == QMediaPlayer::PausedState;
            timeline->cursor = 2.8;
            QMetaObject::invokeMethod(timeline, "cursorChanged", Qt::DirectConnection,
                                      Q_ARG(double, 2.8));
            preview(true);
            *stage = 1;
        } else if (*stage == 1 && player->position() >= 2800 &&
                   player->playbackState() == QMediaPlayer::PlayingState) {
            (*report)["resume_after_seek"] = player->position() < 3500;
            timeline->project.get(timeline->selected).fadeIn = .5;
            projectChanged();
            (*report)["edit_invalidates_audio"] =
                player->source().isEmpty() && workingSignature.isEmpty();
            tabs->setCurrentIndex(4);
            preview(false);
            *stage = 2;
        } else if (*stage == 2 && player->position() >= 300 &&
                   player->playbackState() == QMediaPlayer::PlayingState) {
            (*report)["lyrics_playback"] = playerContext == "lyrics" && player->position() < 1000;
            double expected = qMax(0., player->position() / 1000. - sf::LyricLead);
            insertStamp(true, true);
            auto parsed = sf::parseLyrics(lyrics->toPlainText(), false);
            (*report)["live_stamp_lead"] =
                !parsed.isEmpty() && std::abs(parsed.first().start - expected) < .006;
            (*report)["text_preserved"] =
                sf::plainLyrics(lyrics->toPlainText()) == "Первая строка\nВторая строка";
            *stage = 3;
        }
        if (*stage == 3 || elapsed->elapsed() > 25000 || player->error() != QMediaPlayer::NoError) {
            timer->stop();
            bool success = *stage == 3;
            for (auto it = report->begin(); it != report->end(); ++it)
                success &= it.value().toBool();
            (*report)["complete"] = success;
            if (!success)
                (*report)["error"] = player->errorString();
            QFile result(outputFile);
            if (result.open(QIODevice::WriteOnly))
                result.write(QJsonDocument(*report).toJson());
            stop();
            qApp->exit(success ? 0 : 1);
        }
    });
    timer->start();
}
