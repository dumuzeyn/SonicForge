#include "window.h"
#include <cmath>
void Window::fragmentSettings() {
    if (timeline->selected.isEmpty() || busy)
        return;
    const auto clip = timeline->project.get(timeline->selected);
    QDialog dialog(this);
    dialog.setWindowTitle(localize("Настройки фрагмента"));
    auto* layout = new QVBoxLayout(&dialog);
    auto* form = new QFormLayout;
    layout->addLayout(form);
    QList<QDoubleSpinBox*> values;
    auto add = [&](const QString& label, double value, double low, double high, double step,
                   const QString& unit, double scale = 1) {
        auto* model = new QDoubleSpinBox;
        model->setRange(low, high);
        model->setDecimals(step < 1 ? 2 : 0);
        model->setSingleStep(step);
        model->setValue(value);
        model->setAccessibleName(localize(label));
        auto* panel = valueSlider(model, unit, scale);
        panel->setProperty("sfHelpTitle", label);
        panel->setProperty("sfHelpKey", "clip");
        form->addRow(localize(label), panel);
        values << model;
    };
    add("Громкость", clip.volume * std::pow(10., clip.gain / 20.), 0, 4, .01, "%", 100);
    add("Скорость", clip.speed, 0, 4, .01, "%", 100);
    add("Бас, dB", clip.bass, -18, 18, .1, " dB");
    add("Средние частоты, dB", clip.mid, -18, 18, .1, " dB");
    add("Высокие частоты, dB", clip.treble, -18, 18, .1, " dB");
    auto* hint = new QLabel(localize(
        "100% — исходное значение. 0% громкости выключает звук; 0% скорости останавливает фрагмент "
        "(пауза в монтаже). Изменение длины сдвигает следующие фрагменты этой дорожки."));
    hint->setWordWrap(true);
    hint->setStyleSheet("color:#8b819c;");
    layout->addWidget(hint);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel);
    layout->addWidget(buttons);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    dialog.resize(600, 360);
    if (dialog.exec() != QDialog::Accepted)
        return;
    auto changed = timeline->project;
    auto& current = changed.get(clip.id);
    current.gain = 0;
    current.volume = values[0]->value();
    current.speed = values[1]->value();
    current.bass = values[2]->value();
    current.mid = values[3]->value();
    current.treble = values[4]->value();
    double delta = current.duration() - clip.duration();
    double fadeTotal = current.fadeIn + current.fadeOut;
    if (fadeTotal > current.duration()) {
        current.fadeIn *= current.duration() / fadeTotal;
        current.fadeOut *= current.duration() / fadeTotal;
    }
    for (auto& other : changed.clips)
        if (other.id != clip.id && other.lane == clip.lane &&
            other.position >= clip.position + clip.duration() - .0001)
            other.position += delta;
    changed.validate();
    remember();
    timeline->project = changed;
    projectChanged();
    timeline->fit();
}
void Window::scheduleComparison() {
    if (!comparisonTimer || property("sfTesting").toBool())
        return;
    ++comparisonRevision;
    comparisonCancel->store(true);
    if (!linked->isChecked()) {
        const QString path = source->text();
        originalPane->setFile(QFileInfo(path).isFile() ? path : QString());
        if (originalPane->file.isEmpty())
            originalPane->message->setText(localize("Выберите один аудиофайл"));
    }
    if (audioDirty) {
        processedPane->show();
        processedPane->media->pause();
        processedPane->setEnabled(false);
        processedPane->message->setText(localize("Обновляю звук…"));
    }
    if (tabs->currentIndex() == 2)
        comparisonTimer->start();
}
void Window::compareAudio() {
    if (property("sfTesting").toBool() || tabs->currentIndex() != 2)
        return;
    if (busy || comparisonWatcher) {
        comparisonTimer->start();
        return;
    }
    const bool link = linked->isChecked(), dirty = audioDirty;
    const QString original = source->text();
    const auto snapshot = timeline->project;
    if ((link && snapshot.clips.isEmpty()) || (!link && !QFileInfo(original).isFile())) {
        processedPane->hide();
        originalPane->setFile({});
        originalPane->message->setText(localize("Выберите песню или включите связь с редактором"));
        return;
    }
    if (!link && !dirty)
        return;
    const auto options = audioOptions();
    const auto revision = comparisonRevision;
    comparisonCancel = std::make_shared<std::atomic_bool>(false);
    const auto token = comparisonCancel;
    comparisonWatcher = new QFutureWatcher<WorkResult>(this);
    auto* current = comparisonWatcher;
    connect(current, &QFutureWatcher<WorkResult>::finished, this, [=, this] {
        auto result = current->result();
        current->deleteLater();
        comparisonWatcher = nullptr;
        if (token->load() || revision != comparisonRevision) {
            for (auto file : result.files)
                QFile::remove(file);
            if (tabs->currentIndex() == 2)
                comparisonTimer->start();
            return;
        }
        if (!result.error.isEmpty()) {
            for (auto file : result.files)
                QFile::remove(file);
            processedPane->setEnabled(false);
            processedPane->message->setText(localize(result.error));
            return;
        }
        originalPane->setFile(result.file);
        originalPane->message->setText(link ? localize("Текущий монтаж редактора")
                                            : QFileInfo(original).fileName());
        processedPane->setFile(result.data["processed"].toString());
        processedPane->setVisible(dirty);
        processedPane->setEnabled(true);
        processedPane->message->setText(localize("Текущие настройки звука"));
        QSet<QString> keep;
        for (auto file : result.files)
            keep.insert(file);
        for (auto file : comparisonFiles)
            if (!keep.contains(file))
                QFile::remove(file);
        comparisonFiles = keep;
    });
    current->setFuture(QtConcurrent::run([=] {
        WorkResult result;
        try {
            result.file = original;
            if (link) {
                result.file = sf::uniqueFile();
                result.files << result.file;
                sf::render(snapshot, result.file, token);
            }
            if (dirty) {
                QString path = sf::uniqueFile();
                result.files << path;
                sf::normalize(result.file, path, options, token);
                result.data["processed"] = path;
            }
        } catch (const std::exception& error) {
            result.error = QString::fromUtf8(error.what());
        }
        return result;
    }));
}
void Window::showContextHelp(QWidget* widget, const QString& title, const QString& key, QPoint at) {
    static const QJsonObject descriptions = [] {
        QFile file(":/context-help.json");
        if (!file.open(QIODevice::ReadOnly))
            return QJsonObject{};
        return QJsonDocument::fromJson(file.readAll()).object();
    }();
    QString description = descriptions[key].toObject()[language].toString();
    if (description.isEmpty())
        description = descriptions[title].toObject()[language].toString();
    if (description.isEmpty())
        description =
            language == "en"
                ? "Adjust this setting for the selected operation. Changes are applied to the "
                  "output copy."
                : "Настройка выбранного действия. Изменения применяются к выходной копии песни.";
    QMenu menu(widget);
    auto* action = new QWidgetAction(&menu);
    auto* text = new QLabel("<b>" + localize(title).toHtmlEscaped() + "</b><br><br>" +
                            description.toHtmlEscaped());
    text->setWordWrap(true);
    text->setMaximumWidth(400);
    text->setMargin(16);
    action->setDefaultWidget(text);
    menu.addAction(action);
    menu.exec(widget->mapToGlobal(at));
}
void Window::closeSmoke(const QString& output) {
    setProperty("sfTesting", true);
    setProperty("sfCloseReport", output);
    startTask("Проверка остановки фоновой задачи", [this](sf::Progress) {
        sf::process(sf::executable("ffmpeg"),
                    {"-hide_banner", "-nostdin", "-v", "error", "-re", "-f", "lavfi", "-i",
                     "sine=frequency=220:duration=120", "-f", "null", "-"},
                    cancel);
        return WorkResult{};
    });
    QTimer::singleShot(600, this, &Window::close);
}
void Window::soundSmoke(const QString& file, const QString& output) {
    audioOutput->setVolume(0);
    originalPane->audio->setVolume(0);
    processedPane->audio->setVolume(0);
    linked->setChecked(false);
    source->setText(file);
    tabs->setCurrentIndex(2);
    numbers["speed"]->setValue(2);
    numbers["gain"]->setValue(.5);
    auto* timer = new QTimer(this);
    timer->setInterval(80);
    auto elapsed = std::make_shared<QElapsedTimer>();
    auto phase = std::make_shared<int>(0);
    auto report = std::make_shared<QJsonObject>();
    elapsed->start();
    connect(timer, &QTimer::timeout, this, [=, this] {
        if (*phase == 0 && !comparisonWatcher && processedPane->media->duration() > 0 &&
            originalPane->media->duration() > 0) {
            (*report)["original_unprocessed"] = originalPane->file == file;
            (*report)["automatic_processed_player"] =
                !processedPane->isHidden() && QFileInfo(processedPane->file).isFile();
            (*report)["hidden_effects_active"] = findChild<QWidget*>("audioAdvanced")->isHidden();
            (*report)["speed_applied"] = std::abs(processedPane->media->duration() -
                                                  originalPane->media->duration() / 2.) < 150;
            originalPane->media->play();
            *phase = 1;
        }
        if (*phase == 1 && originalPane->media->position() > 160) {
            (*report)["original_plays"] =
                originalPane->media->playbackState() == QMediaPlayer::PlayingState;
            processedPane->media->setPosition(400);
            processedPane->media->play();
            *phase = 2;
        }
        if ((*phase == 2 && processedPane->media->position() > 650) || elapsed->elapsed() > 30000) {
            timer->stop();
            (*report)["processed_plays_and_seeks"] =
                *phase == 2 && processedPane->media->playbackState() == QMediaPlayer::PlayingState;
            (*report)["one_player_at_a_time"] =
                originalPane->media->playbackState() != QMediaPlayer::PlayingState;
            bool ok = *phase == 2;
            for (auto it = report->begin(); it != report->end(); ++it)
                ok &= it.value().toBool();
            (*report)["complete"] = ok;
            QFile result(output);
            if (result.open(QIODevice::WriteOnly))
                result.write(QJsonDocument(*report).toJson());
            auto directory = QFileInfo(output).absolutePath();
            grab().save(directory + "/sound-top.png");
            for (auto* scroll : tabs->widget(2)->findChildren<QScrollArea*>())
                scroll->ensureWidgetVisible(processedPane);
            QApplication::processEvents();
            grab().save(directory + "/sound-players.png");
            qApp->exit(ok ? 0 : 1);
        }
    });
    timer->start();
}