#include "window.h"

namespace {
QString persistWorkspace(const QString& path, QJsonObject state, const sf::Cancel& cancel = {}, const QImage& background = {}) {
    auto project = sf::Project::fromJson(state["project"].toObject());
    QSet<QString> used;
    for (const auto& clip : project.clips) { used.insert(clip.source); used.insert(clip.originalSource); }
    for (auto it = project.sources.begin(); it != project.sources.end();) { if (!used.contains(it.key())) it = project.sources.erase(it); else ++it; }
    const QString assetRoot = path + ".assets";
    const QString cacheRoot = QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + "/edits/";
    const QString recoveryRoot = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/recovery/";
    QMap<QString, QString> replacements;
    for (const auto& s : project.sources) {
        sf::checkpoint(cancel);
        const auto full = QFileInfo(s.path).absoluteFilePath();
        if (!full.startsWith(cacheRoot, Qt::CaseInsensitive) && !full.startsWith(recoveryRoot, Qt::CaseInsensitive)) continue;
        if (!QDir().mkpath(assetRoot)) throw sf::Error("Не удалось создать папку ресурсов проекта");
        const auto hash = s.fingerprint.isEmpty() ? sf::fileFingerprint(s.path, cancel) : s.fingerprint;
        const QString target = assetRoot + "/" + QString::fromLatin1(hash.toHex()) + "." + QFileInfo(s.path).suffix();
        if (!QFileInfo::exists(target)) {
            QFile input(s.path); QSaveFile output(target);
            if (!input.open(QIODevice::ReadOnly) || !output.open(QIODevice::WriteOnly)) throw sf::Error("Не удалось сохранить ресурсы проекта");
            while (!input.atEnd()) {
                sf::checkpoint(cancel);
                if (output.write(input.read(1024 * 1024)) < 0) throw sf::Error(output.errorString());
            }
            if (!output.commit()) throw sf::Error(output.errorString());
        }
        replacements[s.path] = target;
    }
    for (auto& clip : project.clips) {
        clip.source = replacements.value(clip.source, clip.source);
        clip.originalSource = replacements.value(clip.originalSource, clip.originalSource);
    }
    for (auto it = replacements.cbegin(); it != replacements.cend(); ++it) {
        auto s = project.sources.take(it.key()); s.path = it.value();
        QFileInfo info(s.path); s.size = info.size(); s.modified = info.lastModified().toMSecsSinceEpoch();
        project.sources[s.path] = s;
    }
    auto json = project.json();
    // Resources stay relative to the project, so a saved project can be moved with its .assets folder.
    auto sources = json["sources"].toArray();
    QMap<QString, QString> relative;
    for (auto value : sources) {
        auto s = value.toObject(); const auto full = s["path"].toString();
        if (full.startsWith(assetRoot + "/")) { const auto local = QDir(QFileInfo(path).absolutePath()).relativeFilePath(full); relative[full] = local; s["path"] = local; value = s; }
    }
    auto clips = json["clips"].toArray();
    for (auto value : clips) { auto c = value.toObject(); for (const auto& key : {"source", "originalSource"}) c[key] = relative.value(c[key].toString(), c[key].toString()); value = c; }
    json["sources"] = sources; json["clips"] = clips;
    state["project"] = json;
    if (!background.isNull()) {
        QByteArray bytes; QBuffer buffer(&bytes); buffer.open(QIODevice::WriteOnly);
        if (!background.save(&buffer, "PNG")) throw sf::Error("Не удалось сохранить фон обложки");
        sf::checkpoint(cancel);
        const auto imagePath = assetRoot + "/cover-" + QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex()) + ".png";
        if (!QDir().mkpath(assetRoot)) throw sf::Error("Не удалось создать папку ресурсов проекта");
        if (!QFileInfo::exists(imagePath)) { QSaveFile image(imagePath); if (!image.open(QIODevice::WriteOnly) || image.write(bytes) != bytes.size() || !image.commit()) throw sf::Error("Не удалось сохранить фон обложки"); }
        state["coverBackground"] = QDir(QFileInfo(path).absolutePath()).relativeFilePath(imagePath);
    }
    state["schema"] = "SonicForgeProject"; state["version"] = 1;
    state["savedAt"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile output(path);
    if (!output.open(QIODevice::WriteOnly) || output.write(QJsonDocument(state).toJson()) < 0 || !output.commit()) throw sf::Error("Не удалось сохранить проект: " + path + "\n" + output.errorString());
    return path;
}
QJsonObject readWorkspace(const QString& path) {
    QFile input(path);
    if (!input.open(QIODevice::ReadOnly) || input.size() > 64 * 1024 * 1024) throw sf::Error("Не удалось открыть проект");
    QJsonParseError error;
    auto state = QJsonDocument::fromJson(input.readAll(), &error).object();
    if (error.error != QJsonParseError::NoError || state["schema"] != "SonicForgeProject" || state["version"].toInt() != 1) throw sf::Error("Неподдерживаемый или повреждённый проект");
    auto json = state["project"].toObject(); auto sources = json["sources"].toArray(); QMap<QString, QString> resolved;
    for (auto value : sources) {
        auto s = value.toObject(); const auto old = s["path"].toString();
        if (QDir::isRelativePath(old)) { const auto full = QFileInfo(QDir(QFileInfo(path).absolutePath()).filePath(old)).absoluteFilePath(); resolved[old] = full; s["path"] = full; value = s; }
    }
    auto clips = json["clips"].toArray();
    for (auto value : clips) { auto c = value.toObject(); for (const auto& key : {"source", "originalSource"}) c[key] = resolved.value(c[key].toString(), c[key].toString()); value = c; }
    json["sources"] = sources; json["clips"] = clips; state["project"] = json;
    auto project = sf::Project::fromJson(json);
    QStringList missing;
    for (auto& source : project.sources) if (!QFileInfo::exists(source.path)) missing << source.path;
    if (!missing.isEmpty()) throw sf::Error("Не найдены ресурсы проекта:\n" + missing.join('\n'));
    const auto background = state["coverBackground"].toString();
    if (!background.isEmpty()) { const auto full = QDir(QFileInfo(path).absolutePath()).absoluteFilePath(background); if (!QFileInfo::exists(full)) throw sf::Error("Не найден фон обложки проекта: " + full); state["coverBackground"] = full; }
    return state;
}
}
void Window::markDirty() {
    if (restoring || property("sfTesting").toBool()) return;
    dirty = true; ++documentRevision;
    setWindowModified(true);
    if (autosaveTimer) autosaveTimer->start();
}
QString Window::lyricText() const {
    if (showTimes->isChecked() || lyricTimes.isEmpty()) return lyrics->toPlainText();
    const auto rows = sf::plainLyrics(lyrics->toPlainText()).split('\n', Qt::SkipEmptyParts);
    if (rows.size() != lyricTimes.size()) {
        // Never silently assign the timing of a deleted/inserted row to another row.
        QStringList output;
        int previous = 0;
        for (const auto& row : rows) {
            int found = -1;
            for (int i = previous; i < lyricTimes.size(); ++i) if (lyricTimes[i].text.trimmed() == row.trimmed()) { found = i; break; }
            if (found >= 0) { output << "[" + sf::timestamp(lyricTimes[found].start, 3) + "]" + row; previous = found + 1; }
            else output << row;
        }
        return output.join('\n');
    }
    auto copy = lyricTimes;
    for (int i = 0; i < rows.size(); ++i) copy[i].text = rows[i];
    return sf::lrc(copy);
}
QJsonObject Window::workspaceState() const {
    QJsonObject state{{"project", timeline->project.json()}, {"lyrics", lyricText()}, {"source", source->text()},
        {"output", output->text()}, {"linked", linked->isChecked()}, {"cursor", timeline->cursor},
        {"selected", timeline->selected}, {"zoom", timeline->zoom}, {"format", mixFormat->currentIndex()}};
    QJsonObject metadata, numeric, flags, selections;
    for (auto it = metadataFields.cbegin(); it != metadataFields.cend(); ++it) metadata[it.key()] = it.value()->text();
    for (auto it = numbers.cbegin(); it != numbers.cend(); ++it) numeric[it.key()] = it.value()->value();
    for (auto it = checks.cbegin(); it != checks.cend(); ++it) flags[it.key()] = it.value()->isChecked();
    for (auto it = choices.cbegin(); it != choices.cend(); ++it) selections[it.key()] = it.value()->currentIndex();
    state["metadata"] = metadata; state["numbers"] = numeric; state["checks"] = flags; state["choices"] = selections;
    state["lyricLanguage"] = lyricLanguage->currentData().toString(); state["lyricMode"] = lyricMode->currentIndex(); state["lyricFormat"] = lyricFormat->currentIndex();
    QJsonArray tracks; for (int i = 0; i < lyricTrack->count(); ++i) tracks.append(QJsonObject{{"key", lyricTrack->itemData(i).toString()}, {"text", lyricTrack->itemData(i, Qt::UserRole + 1).toString()}});
    state["lyricTracks"] = tracks; state["lyricTrack"] = lyricTrack->currentData().toString();
    const auto cover = currentCoverOptions(); QJsonArray palette, stops, music;
    for (const auto& color : cover.palette) palette.append(color.name());
    for (double at : cover.stops) stops.append(at);
    for (double value : coverArtwork.music) music.append(value);
    QJsonObject coverMetadata; for (auto it = coverArtwork.metadata.values.begin(); it != coverArtwork.metadata.values.end(); ++it) coverMetadata[it.key()] = it.value();
    state["cover"] = QJsonObject{{"text", cover.text}, {"font", cover.fontFamily}, {"textSize", cover.textSize}, {"textX", cover.textX}, {"textY", cover.textY}, {"ink", cover.ink.isValid() ? cover.ink.name() : QString()}, {"mood", cover.mood}, {"palette", palette}, {"stops", stops}, {"music", music}, {"metadata", coverMetadata}, {"custom", !customCoverFile.isEmpty()}};
    return state;
}
void Window::applyWorkspace(const QJsonObject& state) {
    auto project = sf::Project::fromJson(state["project"].toObject());
    restoring = true; auto restore = qScopeGuard([&] { restoring = false; });
    stop(); player->setSource({}); playerContext.clear(); comparisonCancel->store(true);
    source->setText(state["source"].toString()); output->setText(state["output"].toString());
    linked->setChecked(state["linked"].toBool()); mixFormat->setCurrentIndex(state["format"].toInt());
    auto set = [&](auto& widgets, const QString& field, auto apply) { const auto values = state[field].toObject(); for (auto it = widgets.begin(); it != widgets.end(); ++it) if (values.contains(it.key())) { QSignalBlocker block(it.value()); apply(it.value(), values[it.key()]); } };
    set(metadataFields, "metadata", [](QLineEdit* w, QJsonValue v) { w->setText(v.toString()); });
    set(numbers, "numbers", [](QDoubleSpinBox* w, QJsonValue v) { w->setValue(v.toDouble()); });
    for (auto* field : numbers) syncValueControls(field);
    set(checks, "checks", [](QCheckBox* w, QJsonValue v) { w->setChecked(v.toBool()); });
    set(choices, "choices", [](QComboBox* w, QJsonValue v) { w->setCurrentIndex(qBound(0, v.toInt(), w->count() - 1)); });
    const auto text = state["lyrics"].toString(); lyricTimes = sf::parseLyrics(text, false);
    lyrics->setPlainText(showTimes->isChecked() ? text : sf::plainLyrics(text));
    lyricLanguage->setCurrentIndex(qMax(0, lyricLanguage->findData(state["lyricLanguage"].toString())));
    lyricMode->setCurrentIndex(state["lyricMode"].toInt()); lyricFormat->setCurrentIndex(state["lyricFormat"].toInt());
    { QSignalBlocker block(lyricTrack); lyricTrack->clear(); for (const auto& value : state["lyricTracks"].toArray()) { const auto track = value.toObject(); lyricTrack->addItem(track["key"].toString().replace('|', " · "), track["key"].toString()); lyricTrack->setItemData(lyricTrack->count() - 1, track["text"].toString(), Qt::UserRole + 1); } if (!lyricTrack->count()) lyricTrack->addItem(localize("Основная (und)"), "und|"); lyricTrack->setCurrentIndex(qMax(0, lyricTrack->findData(state["lyricTrack"].toString()))); }
    lyricSource = source->text();
    lyricTrack->setProperty("sfPreviousTrack", lyricTrack->currentIndex());
    timeline->project = project; timeline->selected = state["selected"].toString();
    timeline->cursor = qBound(0., state["cursor"].toDouble(), project.duration()); timeline->zoom = qBound(1., state["zoom"].toDouble(1), 4096.);
    undoHistory.clear(); redoHistory.clear(); workingSignature.clear(); coverArtwork = {}; coverImage = {}; lastCover.clear(); customCoverFile.clear();
    const auto cover = state["cover"].toObject();
    coverOptions.text = cover["text"].toString(); coverOptions.fontFamily = cover["font"].toString("Unbounded"); coverOptions.textSize = qBound(1., cover["textSize"].toDouble(7.2), 20.); coverOptions.textX = qBound(0., cover["textX"].toDouble(50), 100.); coverOptions.textY = qBound(0., cover["textY"].toDouble(76), 100.); coverOptions.ink = QColor(cover["ink"].toString()); coverOptions.mood = cover["mood"].toString();
    if (!cover["palette"].toArray().isEmpty()) { coverOptions.palette.clear(); coverOptions.stops.clear(); for (const auto& color : cover["palette"].toArray()) coverOptions.palette.append(QColor(color.toString())); for (const auto& at : cover["stops"].toArray()) coverOptions.stops.append(at.toDouble()); }
    for (const auto& value : cover["music"].toArray()) coverArtwork.music.append(value.toDouble());
    const auto meta = cover["metadata"].toObject(); for (auto it = meta.begin(); it != meta.end(); ++it) coverArtwork.metadata.values[it.key()] = it.value().toString();
    coverArtwork.background = QImage(state["coverBackground"].toString());
    if (cover["custom"].toBool()) customCoverFile = state["coverBackground"].toString();
    coverPreview->setImage({}); if (!coverArtwork.background.isNull()) refreshCoverPreview();
    timeline->refresh(); updateState(); dirty = false; setWindowModified(false); scheduleComparison();
}
void Window::saveProject(const QString& requested) {
    if (busy) return;
    QString target = requested.isEmpty() ? projectPath : requested;
    if (target.isEmpty()) target = QFileDialog::getSaveFileName(this, localize("Сохранить проект"), "SonicForge.sfproject", "Sonic Forge (*.sfproject)");
    if (target.isEmpty()) { closeAfterSave = false; return; }
    if (!target.endsWith(".sfproject", Qt::CaseInsensitive)) target += ".sfproject";
    const auto state = workspaceState(); const auto revision = documentRevision; const auto background = coverArtwork.background;
    startTask("Сохраняю проект…", [=, this](sf::Progress) { WorkResult result; result.file = persistWorkspace(target, state, cancel, background); return result; },
        [=, this](const WorkResult& result) { projectPath = result.file; if (revision == documentRevision) { timeline->project = sf::Project::fromJson(readWorkspace(result.file)["project"].toObject()); dirty = false; setWindowModified(false); } if (closeAfterSave) QTimer::singleShot(0, this, &QWidget::close); else if (!pendingOpenProject.isEmpty()) { const auto next = std::exchange(pendingOpenProject, {}); QTimer::singleShot(0, this, [this, next] { openProject(next); }); } });
}
void Window::openProject(const QString& requested) {
    if (busy) return;
    const QString target = requested.isEmpty() ? QFileDialog::getOpenFileName(this, localize("Открыть проект"), {}, "Sonic Forge (*.sfproject)") : requested;
    if (target.isEmpty()) return;
    if (dirty) {
        const auto answer = QMessageBox::question(this, "Sonic Forge", localize("Сохранить текущий проект перед открытием другого?"), QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Save);
        if (answer == QMessageBox::Cancel) return;
        if (answer == QMessageBox::Save) { pendingOpenProject = target; saveProject(); return; }
    }
    startTask("Открываю проект…", [target](sf::Progress) { WorkResult result; result.data = readWorkspace(target); result.file = target; return result; },
        [this](const WorkResult& result) { applyWorkspace(result.data); projectPath = result.file; });
}
void Window::autosave() {
    if (!dirty || restoring || closing || property("sfTesting").toBool() || recoveryPath.isEmpty()) return;
    if (autosaveWatcher) { autosaveTimer->start(); return; }
    const auto state = workspaceState(); const auto path = recoveryPath; const auto background = coverArtwork.background;
    autosaveWatcher = new QFutureWatcher<QString>(this);
    connect(autosaveWatcher, &QFutureWatcher<QString>::finished, this, [this] {
        const auto error = autosaveWatcher->result(); autosaveWatcher->deleteLater(); autosaveWatcher = nullptr;
        if (!error.isEmpty()) { appendLog(error); status->setText(localize("Автосохранение не выполнено: ") + error); }
    });
    autosaveWatcher->setFuture(QtConcurrent::run([state, path, background] { try { persistWorkspace(path, state, {}, background); return QString(); } catch (const std::exception& error) { return QString::fromUtf8(error.what()); } }));
}
void Window::setupRecovery() {
    autosaveTimer = new QTimer(this); autosaveTimer->setSingleShot(true); autosaveTimer->setInterval(2000);
    connect(autosaveTimer, &QTimer::timeout, this, &Window::autosave);
    if (QCoreApplication::instance()->property("sfTesting").toBool()) { setProperty("sfTesting", true); return; }
    const auto root = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/recovery";
    const auto directory = root + "/" + QUuid::createUuid().toString(QUuid::Id128);
    QDir().mkpath(directory); recoveryPath = directory + "/workspace.sfproject";
    recoveryLease = std::make_unique<QLockFile>(directory + "/active.lock"); recoveryLease->setStaleLockTime(0);
    if (!recoveryLease->tryLock()) { recoveryPath.clear(); return; }
    QThreadPool::globalInstance()->start([] { try { sf::cleanCache(); } catch (...) {} });
    if (QCoreApplication::instance()->property("sfSkipRecovery").toBool()) return;
    QTimer::singleShot(500, this, [this, root, directory] {
        for (const auto& info : QDir(root).entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Time)) {
            if (info.absoluteFilePath() == directory || info.isSymLink()) continue;
            auto lock = std::make_unique<QLockFile>(info.absoluteFilePath() + "/active.lock"); lock->setStaleLockTime(0); if (!lock->tryLock()) continue;
            const auto candidate = info.absoluteFilePath() + "/workspace.sfproject";
            if (!QFileInfo::exists(candidate)) continue;
            if (QMessageBox::question(this, "Sonic Forge", localize("Найдена незавершённая сессия. Восстановить монтаж и текст?")) == QMessageBox::Yes) {
                try { applyWorkspace(readWorkspace(candidate)); restoredRecoveryLease = std::move(lock); restoredRecoveryPath = candidate; projectPath.clear(); markDirty(); } catch (const std::exception& error) { failure(QString::fromUtf8(error.what())); }
            }
            break;
        }
    });
}
void Window::disposeRecovery() {
    recoveryLease.reset(); restoredRecoveryLease.reset();
    const auto root = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/recovery/";
    for (const auto& file : {recoveryPath, restoredRecoveryPath}) {
        if (file.isEmpty()) continue;
        const auto folder = QFileInfo(file).absolutePath();
        if (folder.startsWith(root) && !QFileInfo(folder).isSymLink()) QDir(folder).removeRecursively();
    }
}
void Window::updateInputs(bool enabled) {
    for (auto* field : {source, output}) field->setEnabled(enabled && (field != source || !linked->isChecked()));
    for (auto* field : metadataFields) field->setReadOnly(!enabled);
    for (auto* field : numbers) field->setEnabled(enabled);
    for (auto* field : checks) field->setEnabled(enabled);
    for (auto* field : choices) field->setEnabled(enabled);
    lyricFormat->setEnabled(enabled); lyricMode->setEnabled(enabled); lyricLanguage->setEnabled(enabled); lyricQuality->setEnabled(enabled); lyricTrack->setEnabled(enabled);
}
void Window::refreshWrittenSource(const QString& path) {
    if (!timeline->project.sources.contains(path)) return;
    auto update = [&](sf::Project& project) { if (!project.sources.contains(path)) return; auto& s = project.sources[path]; QFileInfo info(path); s.size = info.size(); s.modified = info.lastModified().toMSecsSinceEpoch(); s.fingerprint = sf::fileFingerprint(path); };
    update(timeline->project); for (auto& p : undoHistory) update(p); for (auto& p : redoHistory) update(p);
    workingSignature.clear(); markDirty();
}
void Window::cleanWorkingCache() {
    if (busy || comparisonWatcher) return;
    QSet<QString> keep{workingFile, lastCover};
    for (auto* media : {player, originalPane->media, processedPane->media}) if (media->source().isLocalFile()) keep.insert(QFileInfo(media->source().toLocalFile()).absoluteFilePath());
    for (const auto& path : comparisonFiles) keep.insert(path);
    auto protect = [&](const sf::Project& project) { for (auto it = project.sources.begin(); it != project.sources.end(); ++it) keep.insert(QFileInfo(it.key()).absoluteFilePath()); };
    protect(timeline->project); for (const auto& project : undoHistory) protect(project); for (const auto& project : redoHistory) protect(project);
    const auto root = sf::cacheDirectory();
    QDirIterator files(root, QDir::Files, QDirIterator::Subdirectories);
    while (files.hasNext()) { const auto path = files.next(); if (!files.fileInfo().isSymLink() && files.fileInfo().fileName() != "session.lock" && !keep.contains(QFileInfo(path).absoluteFilePath())) QFile::remove(path); }
}
void Window::reliabilitySmoke(const QString& reportPath) {
    setProperty("sfTesting", true);
    QJsonObject report;
    QTemporaryDir temporary;
    auto waitTask = [&] {
        QElapsedTimer timeout; timeout.start();
        while (busy && timeout.elapsed() < 30000) { QApplication::processEvents(); QThread::msleep(10); }
        if (busy) { cancel->store(true); throw sf::Error("Превышено время GUI-проверки"); }
    };
    auto* dismiss = new QTimer(this); dismiss->setInterval(50);
    connect(dismiss, &QTimer::timeout, this, [&] { if (auto* box = qobject_cast<QMessageBox*>(QApplication::activeModalWidget())) { report["unexpected_dialog"] = box->text(); box->reject(); } }); dismiss->start();
    try {
        const auto wave = temporary.filePath("Проверка звука.wav"), mp3 = temporary.filePath("Песня.mp3");
        sf::ffmpeg({"-f", "lavfi", "-i", "sine=frequency=220:duration=1:sample_rate=44100", wave});
        sf::ffmpeg({"-i", wave, mp3});
        linked->setChecked(false); source->setText(mp3);
        timeline->project = {}; timeline->selected = timeline->project.add(sf::readSource(mp3));
        lyrics->setPlainText("[00:00.800]Hello world"); showTimes->setChecked(false);
        report["hidden_times_preserved"] = lyricText().contains("[00:00.800]");
        lyricFormat->setCurrentIndex(0); saveLyrics(); waitTask();
        report["hidden_times_written"] = sf::readMetadata(mp3).values["lyrics"].contains("[00:00.800]");
        sf::render(timeline->project, temporary.filePath("after-tags.wav"));
        report["own_tag_write_keeps_project_valid"] = true;
        const auto saved = temporary.filePath("Монтаж.sfproject");
        const auto cached = sf::uniqueFile(); sf::ffmpeg({"-i", wave, cached});
        timeline->project = {}; timeline->selected = timeline->project.add(sf::readSource(cached));
        QImage cover(128, 128, QImage::Format_RGB32); cover.fill(Qt::cyan); coverArtwork = sf::coverArtworkFromImage(cover, {}, currentCoverOptions()); coverOptions.text = "Saved cover";
        persistWorkspace(saved, workspaceState(), {}, coverArtwork.background);
        auto restored = readWorkspace(saved); auto recovered = sf::Project::fromJson(restored["project"].toObject());
        report["project_round_trip"] = recovered.clips.size() == 1 && recovered.clips.first().source.startsWith(saved + ".assets/");
        report["project_lyrics_preserved"] = restored["lyrics"].toString().contains("[00:00.800]");
        applyWorkspace(restored); report["project_cover_preserved"] = !coverImage.isNull() && coverOptions.text == "Saved cover";
        numbers["width"]->setValue(1.23); const auto state = workspaceState(); numbers["width"]->setValue(.5); applyWorkspace(state);
        auto* visibleValue = qobject_cast<QDoubleSpinBox*>(numbers["width"]->property("sfNumericControl").value<QObject*>());
        report["restored_numeric_control"] = !visibleValue || std::abs(visibleValue->value() - 123) < .01;
        timeline->project = {}; timeline->selected.clear();
        player->setSource(QUrl::fromLocalFile(mp3)); playerContext = "lyrics";
        source->setText(wave);
        report["song_context_changed"] = player->source().isEmpty() && lyrics->toPlainText().isEmpty();
        source->setText(mp3);
        report["song_draft_restored"] = lyricText().contains("Hello world");
        output->setText(temporary.filePath("out")); numbers["speed"]->setValue(2);
        checks["process_metadata"]->setChecked(false); checks["process_audio"]->setChecked(true);
        checks["process_lyrics"]->setChecked(false); checks["process_cover"]->setChecked(false); checks["auto_noise"]->setChecked(false);
        processFiles(); waitTask();
        const auto processed = temporary.filePath("out/Песня.mp3");
        const auto tagged = sf::parseLyrics(sf::readMetadata(processed).values.value("lyrics"));
        report["speed_timing_scaled"] = tagged.size() == 1 && std::abs(tagged.first().start - .4) < .01 && sf::readSource(processed, {}, false).duration > tagged.first().start;
        undoHistory.clear();
        for (int i = 0; i < 120; ++i) { emit timeline->editStarted(); emit timeline->changed(); }
        report["undo_bounded"] = undoHistory.size() <= 100;
        QImage image(128, 128, QImage::Format_RGB32); image.fill(Qt::blue);
        sf::CoverOptions options; options.size = 128;
        coverArtwork = sf::coverArtworkFromImage(image, {}, options); customCoverFile.clear(); refreshCoverPreview();
        numbers["cover_seed"]->setValue(123);
        report["stale_cover_blocked"] = coverImage.isNull() && lastCover.isEmpty();
        timeline->project = {}; timeline->project.add({"long.wav", 86300, {}}); timeline->zoom = 4096; timeline->refresh();
        QElapsedTimer elapsed; elapsed.start(); timeline->viewport()->grab();
        report["visible_timeline_only"] = elapsed.elapsed() < 1000;
        auto numeric = numbers["bass"]->parentWidget()->findChildren<QDoubleSpinBox*>();
        bool editable = false; for (const auto* value : numeric) editable |= !value->isHidden(); report["numeric_input"] = editable;
    } catch (const std::exception& error) { report["error"] = QString::fromUtf8(error.what()); }
    dismiss->stop(); bool success = !report.isEmpty();
    for (auto it = report.begin(); it != report.end(); ++it) success &= it.value().isBool() && it.value().toBool();
    report["complete"] = success;
    QFile output(reportPath); if (output.open(QIODevice::WriteOnly)) output.write(QJsonDocument(report).toJson());
    qApp->exit(success ? 0 : 1);
}
