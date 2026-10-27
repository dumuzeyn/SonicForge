#include "window.h"
#include "cover_symbols.h"
#include "windows_cover_test.h"
void Window::coverExportSmoke(const QString& file, const QString& resultFile) {
    setProperty("sfTesting", true);
    auto directory = std::make_shared<QTemporaryDir>();
    const auto input = directory->filePath("song.mp3");
    const auto destination = directory->filePath("result");
    sf::ffmpeg({"-i", file, "-t", "2", input});
    auto hashFile = [](const QString& path) {
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) return QByteArray();
        QCryptographicHash hash(QCryptographicHash::Sha256);
        hash.addData(&file);
        return hash.result();
    };
    const auto sourceHash = hashFile(input);
    QImage image(128,128,QImage::Format_RGB32);
    image.fill(QColor("#6550b9"));
    customCoverFile = directory->filePath("custom.png");
    image.save(customCoverFile);
    linked->setChecked(false);
    source->setText(input);
    output->setText(destination);
    for (const auto& key : {"process_metadata", "process_audio", "process_lyrics", "cover_title", "cover_artist", "cover_symbol"})
        checks[key]->setChecked(false);
    checks["process_cover"]->setChecked(true);
    numbers["cover_size"]->setValue(128);
    auto elapsed = std::make_shared<QElapsedTimer>(); elapsed->start();
    processFiles();
    auto* timer = new QTimer(this);
    timer->setInterval(50);
    connect(timer, &QTimer::timeout, this, [=, this] {
        Q_UNUSED(directory);
        if (auto* box = qobject_cast<QMessageBox*>(QApplication::activeModalWidget())) box->reject();
        if (busy && elapsed->elapsed() < 15000) return;
        timer->stop();
        QJsonObject report;
        try {
            const auto target = destination + "/song.mp3";
            const auto metadata = sf::readMetadata(target);
            const auto cover = QImage::fromData(metadata.cover);
            report["cover_embedded"] = !cover.isNull() && cover.size() == image.size();
            if (!cover.isNull()) {
                const auto actual = cover.pixelColor(64,64), expected = image.pixelColor(64,64);
                report["selected_image_embedded"] = std::abs(actual.red()-expected.red()) < 5 &&
                    std::abs(actual.green()-expected.green()) < 5 && std::abs(actual.blue()-expected.blue()) < 5;
            }
            const auto probe = QJsonDocument::fromJson(sf::process(sf::executable("ffprobe"),
                {"-v", "error", "-show_streams", "-of", "json", target})).object();
            bool attached = false;
            for (auto stream : probe["streams"].toArray())
                attached |= stream.toObject()["disposition"].toObject()["attached_pic"].toInt() == 1;
            report["independent_reader_finds_cover"] = attached;
#ifdef Q_OS_WIN
            report["windows_reads_cover"] = windowsReadsCover(target);
#endif
            report["no_extra_png"] = QDir(destination).entryList(QDir::Files) == QStringList{"song.mp3"};
            report["original_unchanged"] = hashFile(input) == sourceHash;
        } catch (const std::exception& error) { report["error"] = QString::fromUtf8(error.what()); }
        bool success = !report.isEmpty();
        for (auto entry = report.begin(); entry != report.end(); ++entry) success &= entry.value().toBool();
        report["complete"] = success;
        QFile result(resultFile);
        if (result.open(QIODevice::WriteOnly)) result.write(QJsonDocument(report).toJson());
        qApp->exit(success ? 0 : 1);
    });
    timer->start();
}

sf::CoverOptions Window::currentCoverOptions() const {
    auto options = coverOptions;
    options.symbol = checks["cover_symbol"]->isChecked();
    options.title = checks["cover_title"]->isChecked();
    options.artist = checks["cover_artist"]->isChecked();
    options.size = qRound(numbers["cover_size"]->value());
    options.seed = qRound(numbers["cover_seed"]->value());
    options.pattern = choices["cover_pattern"]->currentIndex();
    options.colorSource = choices["cover_color"]->currentIndex();
    options.detail = qRound(numbers["cover_detail"]->value());
    options.contrast = qRound(numbers["cover_contrast"]->value());
    options.saturation = qRound(numbers["cover_saturation"]->value());
    options.softness = qRound(numbers["cover_softness"]->value());
    return options;
}
void Window::refreshCoverPreview() {
    if (coverArtwork.background.isNull()) return;
    auto options = currentCoverOptions();
    coverImage = sf::decorateCover(coverArtwork, options);
    coverPreview->setImage(coverImage, sf::layoutCoverText(coverArtwork.metadata, options).bounds);
}
void Window::coverTextSettings() {
    if (coverArtwork.background.isNull()) return;
    auto options = currentCoverOptions();
    QDialog dialog(this);
    dialog.setObjectName("coverTextDialog");
    dialog.setWindowTitle(localize("Текст и оформление обложки"));
    auto* outer = new QVBoxLayout(&dialog);
    auto* columns = new QHBoxLayout;
    outer->addLayout(columns, 1);
    auto* preview = new CoverPreview;
    preview->setObjectName("coverTextPreview");
    preview->setMinimumSize(220, 220);
    columns->addWidget(preview, 1);
    auto* settings = new QWidget;
    settings->setMinimumWidth(300);
    settings->setMaximumWidth(390);
    auto* scroll = new QScrollArea; scroll->setWidgetResizable(true); scroll->setFrameShape(QFrame::NoFrame); scroll->setWidget(settings); scroll->setMinimumWidth(320); columns->addWidget(scroll);
    auto* form = new QFormLayout(settings);
    auto* showTitle = new QCheckBox(localize("Писать название"));
    showTitle->setObjectName("coverTextEnabled");
    showTitle->setChecked(options.title);
    form->addRow(showTitle);
    auto* text = new QPlainTextEdit(options.text);
    text->setObjectName("coverTextValue");
    text->setPlaceholderText(localize("Если пусто — название песни"));
    text->setFixedHeight(70);
    form->addRow(localize("Текст"), text);
    auto* font = new QFontComboBox;
    font->setObjectName("coverTextFont");
    font->setCurrentFont(QFont(options.fontFamily));
    form->addRow(localize("Шрифт"), font);
    auto add = [&](const QString& name, const QString& label, double value, double low, double high) {
        auto* model = new QDoubleSpinBox;
        model->setObjectName(name);
        model->setRange(low, high);
        model->setDecimals(1);
        model->setSingleStep(.1);
        model->setValue(value);
        model->setAccessibleName(localize(label));
        form->addRow(localize(label), valueSlider(model, "%"));
        return model;
    };
    auto* size = add("coverTextSize", "Размер текста", options.textSize, 1, 20);
    auto* x = add("coverTextX", "По горизонтали", options.textX, 0, 100);
    auto* y = add("coverTextY", "По вертикали", options.textY, 0, 100);
    auto* artist = new QCheckBox(localize("Писать исполнителя"));
    artist->setChecked(options.artist);
    form->addRow(artist);
    auto* symbol = new QCheckBox(localize("Показывать символ"));
    symbol->setChecked(options.symbol);
    form->addRow(symbol);
    auto* colorRow = new QHBoxLayout;
    auto* color = new QPushButton;
    color->setObjectName("coverInkColor");
    auto* automatic = new QPushButton(localize("Автоцвет"));
    colorRow->addWidget(color, 1);
    colorRow->addWidget(automatic);
    form->addRow(localize("Цвет текста и символа"), colorRow);
    auto* hint = new QLabel(localize("Перетащите надпись мышью. Размер указан в процентах от стороны обложки."));
    hint->setWordWrap(true);
    form->addRow(hint);
    auto* previewTimer = new QTimer(&dialog);
    previewTimer->setSingleShot(true); previewTimer->setInterval(40);
    auto refresh = [&] {
      try {
        options.title = showTitle->isChecked();
        options.artist = artist->isChecked();
        options.symbol = symbol->isChecked();
        options.text = text->toPlainText();
        options.fontFamily = font->currentFont().family();
        options.textSize = size->value();
        options.textX = x->value();
        options.textY = y->value();
        auto smallOptions = options; smallOptions.size = qMin(512, options.size);
        auto smallArtwork = coverArtwork; smallArtwork.background = coverArtwork.background.scaled(smallOptions.size, smallOptions.size, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
        auto image = sf::decorateCover(smallArtwork, smallOptions);
        preview->setImage(image, sf::layoutCoverText(coverArtwork.metadata, smallOptions).bounds);
        auto ink = options.ink.isValid() ? options.ink : sf::coverColors(coverArtwork.background).symbol;
        color->setText(ink.name());
        color->setStyleSheet(QString("background:%1;color:%2;").arg(ink.name(), ink.lightness() > 128 ? "black" : "white"));
      } catch (const std::exception& error) { previewTimer->stop(); hint->setText(QString::fromUtf8(error.what())); }
    };
    connect(previewTimer, &QTimer::timeout, &dialog, refresh);
    for (auto* model : {size, x, y})
        connect(model, qOverload<double>(&QDoubleSpinBox::valueChanged), &dialog, [&](double) { previewTimer->start(); });
    for (auto* check : {showTitle, artist, symbol})
        connect(check, &QCheckBox::toggled, &dialog, [&](bool) { previewTimer->start(); });
    connect(text, &QPlainTextEdit::textChanged, &dialog, [&] { showTitle->setChecked(true); previewTimer->start(); });
    connect(font, &QFontComboBox::currentFontChanged, &dialog, [&](const QFont&) { previewTimer->start(); });
    connect(color, &QPushButton::clicked, &dialog, [&] {
        auto initial = options.ink.isValid() ? options.ink : sf::coverColors(coverArtwork.background).symbol;
        auto chosen = QColorDialog::getColor(initial, &dialog, localize("Цвет текста и символа"));
        if (chosen.isValid()) { options.ink = chosen; refresh(); }
    });
    connect(automatic, &QPushButton::clicked, &dialog, [&] { options.ink = {}; refresh(); });
    preview->moved = [&](QPointF anchor) {
        x->setValue(anchor.x());
        y->setValue(anchor.y());
        previewTimer->start();
    };
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel);
    buttons->button(QDialogButtonBox::Cancel)->setText(localize("Отмена"));
    outer->addWidget(buttons);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    const auto available = screen()->availableGeometry().size(); dialog.resize(qMin(960, available.width() - 30), qMin(590, available.height() - 50));
    refresh();
    if (dialog.exec() != QDialog::Accepted) return;
    refresh();
    coverOptions = options;
    {
        QSignalBlocker a(checks["cover_title"]), b(checks["cover_artist"]), c(checks["cover_symbol"]);
        checks["cover_title"]->setChecked(options.title);
        checks["cover_artist"]->setChecked(options.artist);
        checks["cover_symbol"]->setChecked(options.symbol);
    }
    refreshCoverPreview();
    markDirty();
    if (!property("sfTesting").toBool()) savePreferences();
}
