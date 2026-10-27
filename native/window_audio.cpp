#include "window.h"
#include <cmath>
std::function<void()> Window::releaseAudioForWrite(const QString& file) {
    struct Reader { QPointer<QMediaPlayer> media; QUrl source; qint64 position; };
    QList<Reader> readers;
    const auto target = QFileInfo(file).canonicalFilePath();
    if (target.isEmpty()) return [] {};
    for (auto* media : {player, originalPane->media, processedPane->media}) {
        if (!media->source().isLocalFile() ||
            QFileInfo(media->source().toLocalFile()).canonicalFilePath().compare(target, Qt::CaseInsensitive) != 0)
            continue;
        readers << Reader{media, media->source(), media->position()};
        if (media == player) { pendingSeek.reset(); playingTimeline = false; }
        media->stop();
        // Pausing leaves FFmpeg's file handle open on Windows, preventing the
        // atomic replacement used when saving tags. Unload it before writing.
        media->setSource({});
    }
    return [readers] {
        for (const auto& reader : readers) {
            if (!reader.media || !reader.media->source().isEmpty()) continue;
            auto connection = std::make_shared<QMetaObject::Connection>();
            *connection = QObject::connect(reader.media, &QMediaPlayer::mediaStatusChanged, reader.media,
                [reader, connection](QMediaPlayer::MediaStatus status) {
                    if (status != QMediaPlayer::LoadedMedia && status != QMediaPlayer::BufferedMedia &&
                        status != QMediaPlayer::InvalidMedia) return;
                    QObject::disconnect(*connection);
                    if (reader.media && reader.media->source() == reader.source && status != QMediaPlayer::InvalidMedia) {
                        reader.media->setPosition(reader.position);
                        reader.media->pause();
                    }
                });
            reader.media->setSource(reader.source);
        }
    };
}
void Window::lyricsSaveSmoke(const QString& file, const QString& output) {
    setProperty("sfTesting", true);
    auto directory = std::make_shared<QTemporaryDir>();
    const auto song = directory->filePath("save-lyrics.mp3");
    sf::ffmpeg({"-i", file, "-t", "4", song});
    auto samples = std::make_shared<QVector<float>>(sf::decode(song, 8000, 1));
    const QString text = "[00:00.200]Первая строка\n[00:01.500]Вторая строка";
    linked->setChecked(false);
    source->setText(song);
    lyricFormat->setCurrentIndex(0);
    lyrics->setPlainText(text);
    audioOutput->setVolume(0);
    originalPane->audio->setVolume(0);
    processedPane->audio->setVolume(0);
    originalPane->setFile(song);
    processedPane->setFile(song);
    playFile(song, false);
    auto stage = std::make_shared<int>(0);
    auto report = std::make_shared<QJsonObject>();
    auto elapsed = std::make_shared<QElapsedTimer>();
    elapsed->start();
    auto* timer = new QTimer(this);
    timer->setInterval(50);
    connect(timer, &QTimer::timeout, this, [=, this] {
        Q_UNUSED(directory); // Keep the temporary MP3 alive until playback and saving finish.
        if (auto* box = qobject_cast<QMessageBox*>(QApplication::activeModalWidget())) {
            (*report)["save_error"] = box->text();
            box->reject();
        }
        auto loaded = [](QMediaPlayer* media) {
            return media->mediaStatus() == QMediaPlayer::LoadedMedia || media->mediaStatus() == QMediaPlayer::BufferedMedia;
        };
        if (*stage == 0 && player->position() > 200 && loaded(originalPane->media) && loaded(processedPane->media)) {
            try { sf::saveLyrics(song, text, "embedded"); (*report)["reader_lock_detected"] = false; }
            catch (const std::exception& error) {
                (*report)["reader_lock_detected"] = true;
                (*report)["before_save_error"] = QString::fromUtf8(error.what());
            }
            (*report)["saved_position"] = player->position();
            *stage = 1;
            saveLyrics();
        } else if (*stage == 1 && !busy && !watcher && loaded(player) && loaded(originalPane->media) && loaded(processedPane->media)) {
            (*report)["lyrics_written"] = sf::readMetadata(song).values.value("lyrics") == text;
            (*report)["audio_unchanged"] = sf::decode(song, 8000, 1) == *samples;
            (*report)["all_players_restored"] = player->source().toLocalFile() == song &&
                originalPane->media->source().toLocalFile() == song && processedPane->media->source().toLocalFile() == song;
            (*report)["position_restored"] = std::abs(player->position() - (*report)["saved_position"].toInteger()) < 100;
            *stage = 2;
        }
        if (*stage == 2 || elapsed->elapsed() > 15000) {
            timer->stop();
            bool success = *stage == 2 && (*report)["lyrics_written"].toBool() && (*report)["audio_unchanged"].toBool() &&
                           (*report)["all_players_restored"].toBool() && (*report)["position_restored"].toBool() && !report->contains("save_error");
            (*report)["complete"] = success;
            (*report)["stage"] = *stage;
            (*report)["player_status"] = int(player->mediaStatus());
            (*report)["player_error"] = player->errorString();
            (*report)["original_status"] = int(originalPane->media->mediaStatus());
            (*report)["original_error"] = originalPane->media->errorString();
            (*report)["processed_status"] = int(processedPane->media->mediaStatus());
            (*report)["position"] = player->position();
            QFile result(output);
            if (result.open(QIODevice::WriteOnly)) result.write(QJsonDocument(*report).toJson());
            stop();
            player->setSource({}); originalPane->setFile({}); processedPane->setFile({});
            qApp->exit(success ? 0 : 1);
        }
    });
    timer->start();
}
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
    processedPane->seek->setChanges({});
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
    const int previewSeconds = qRound(numbers["preview_seconds"]->value());
    const double previewStart = numbers["preview_start"]->value();
    const QString outputFormat = link ? mixFormat->currentText().toLower() : choices["output_format"]->currentText().toLower();
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
        processedPane->seek->setChanges(result.changes);
        processedPane->setVisible(dirty);
        processedPane->setEnabled(true);
        processedPane->message->setText(localize("Текущие настройки звука") + " · " + outputFormat.toUpper() +
            (previewSeconds > 0 ? " · " + sf::timestamp(previewStart) + " + " + QString::number(previewSeconds) + localize(" с") : localize(" · Весь файл")));
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
                sf::render(snapshot, result.file, token, previewStart, previewSeconds > 0 ? previewSeconds : -1);
            } else if (previewSeconds > 0) {
                result.file = sf::uniqueFile(); result.files << result.file;
                sf::ffmpeg({"-ss", QString::number(previewStart), "-i", original, "-t", QString::number(previewSeconds), "-map", "0:a:0", "-c:a", "pcm_f32le", "-rf64", "auto", result.file}, token);
            }
            if (dirty) {
                QString path = sf::uniqueFile("." + outputFormat);
                result.files << path;
                sf::normalize(result.file, path, options, token);
                result.data["processed"] = path;
                result.changes = sf::audioChanges(result.file, path, token);
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
    // This scenario exercises live comparison; settings/recovery remain isolated by main().
    setProperty("sfTesting", false);
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
            (*report)["original_unprocessed"] = !originalPane->file.isEmpty() && sf::audioChanges(file, originalPane->file).isEmpty();
            (*report)["automatic_processed_player"] =
                !processedPane->isHidden() && QFileInfo(processedPane->file).isFile();
            (*report)["hidden_effects_active"] = findChild<QWidget*>("audioAdvanced")->isHidden();
            (*report)["speed_applied"] = std::abs(processedPane->media->duration() -
                                                  originalPane->media->duration() / 2.) < 150;
            (*report)["processed_seek_has_change_marks"] = !processedPane->seek->changes().isEmpty();
            (*report)["marks_use_processed_duration"] =
                !processedPane->seek->changes().isEmpty() &&
                processedPane->seek->changes().last().second <= processedPane->media->duration() / 1000. + .05;
            (*report)["original_seek_has_no_change_marks"] = originalPane->seek->changes().isEmpty();
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
            auto directory = QFileInfo(output).absolutePath();
            grab().save(directory + "/sound-top.png");
            for (auto* scroll : tabs->widget(2)->findChildren<QScrollArea*>())
                scroll->ensureWidgetVisible(processedPane);
            QApplication::processEvents();
            grab().save(directory + "/sound-players.png");
            scheduleComparison();
            (*report)["settings_clear_outdated_change_marks"] = processedPane->seek->changes().isEmpty();
            bool ok = *phase == 2;
            for (auto it = report->begin(); it != report->end(); ++it)
                ok &= it.value().toBool();
            (*report)["complete"] = ok;
            QFile result(output);
            if (result.open(QIODevice::WriteOnly))
                result.write(QJsonDocument(*report).toJson());
            qApp->exit(ok ? 0 : 1);
        }
    });
    timer->start();
}
