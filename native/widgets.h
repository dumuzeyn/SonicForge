#pragma once
#include "core.h"
#include <QtMultimedia>
#include <QtWidgets>
#include <cmath>

inline QWidget* valueSlider(QDoubleSpinBox* model, const QString& unit = {}, double scale = 1) {
    auto* panel = new QWidget;
    auto* row = new QHBoxLayout(panel);
    row->setContentsMargins(0, 0, 0, 0);
    auto* slider = new QSlider(Qt::Horizontal, panel);
    model->setProperty("sfSliderControl", QVariant::fromValue<QObject*>(slider));
    model->setProperty("sfScale", scale);
    const double step = model->singleStep();
    const int count = qMin(100000, qMax(1, qRound((model->maximum() - model->minimum()) / step)));
    slider->setRange(0, count);
    slider->setMinimumWidth(120);
    auto* text = new QLabel(panel);
    text->setMinimumWidth(78);
    text->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    model->setParent(panel);
    model->show();
    model->setMinimumWidth(90);
    model->setMaximumWidth(125);
    auto sync = [=](double value) {
        QSignalBlocker blocker(slider);
        slider->setValue(
            qRound((value - model->minimum()) / (model->maximum() - model->minimum()) * count));
        int decimals = scale == 100 ? qMax(0, model->decimals() - 2) : model->decimals();
        text->setText(QLocale().toString(value * scale, 'f', decimals) + unit);
        slider->setAccessibleName(model->accessibleName());
        slider->setAccessibleDescription(text->text());
    };
    QObject::connect(slider, &QSlider::valueChanged, model, [=](int value) {
        model->setValue(model->minimum() +
                        double(value) / count * (model->maximum() - model->minimum()));
    });
    QObject::connect(model, qOverload<double>(&QDoubleSpinBox::valueChanged), panel, sync);
    sync(model->value());
    row->addWidget(slider, 1);
    row->addWidget(model);
    if (scale != 1) {
        model->hide();
        auto* input = new QDoubleSpinBox(panel);
        model->setProperty("sfNumericControl", QVariant::fromValue<QObject*>(input));
        input->setRange(model->minimum() * scale, model->maximum() * scale);
        input->setSingleStep(model->singleStep() * scale);
        input->setDecimals(qMax(0, model->decimals() - 2));
        input->setValue(model->value() * scale); input->setAccessibleName(model->accessibleName());
        input->setMinimumWidth(95); input->setMaximumWidth(125);
        QObject::connect(input, qOverload<double>(&QDoubleSpinBox::valueChanged), model, [=](double value) { model->setValue(value / scale); });
        QObject::connect(model, qOverload<double>(&QDoubleSpinBox::valueChanged), input, [=](double value) { QSignalBlocker block(input); input->setValue(value * scale); });
        row->addWidget(input);
    }
    text->hide();
    if (!unit.isEmpty()) { auto* suffix = new QLabel(unit, panel); row->addWidget(suffix); }
    panel->setProperty("sfSlider", true);
    return panel;
}
inline void syncValueControls(QDoubleSpinBox* model) {
    if (auto* slider = qobject_cast<QSlider*>(model->property("sfSliderControl").value<QObject*>())) {
        QSignalBlocker block(slider);
        const double span = model->maximum() - model->minimum();
        slider->setValue(span > 0 ? qRound((model->value() - model->minimum()) / span * slider->maximum()) : 0);
    }
    if (auto* input = qobject_cast<QDoubleSpinBox*>(model->property("sfNumericControl").value<QObject*>())) {
        QSignalBlocker block(input); input->setValue(model->value() * model->property("sfScale").toDouble());
    }
}
inline QWidget* disclosure(QVBoxLayout* layout, const QString& title) {
    auto* button = new QToolButton;
    button->setText(title);
    button->setCheckable(true);
    button->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    button->setArrowType(Qt::RightArrow);
    button->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    button->setMinimumHeight(38);
    layout->addWidget(button);
    auto* content = new QWidget;
    content->setVisible(false);
    layout->addWidget(content);
    QObject::connect(button, &QToolButton::toggled, content, [=](bool open) {
        content->setVisible(open);
        button->setArrowType(open ? Qt::DownArrow : Qt::RightArrow);
    });
    return content;
}
class CoverPreview final : public QWidget {
    QImage artwork;
    QImage display;
    QRectF textBounds;
    QPointF dragStart, anchor;
    bool dragging = false, hovering = false;
    QRectF imageRect() const {
        QSizeF fitted = artwork.size();
        fitted.scale(size(), Qt::KeepAspectRatio);
        return QRectF(QPointF((width() - fitted.width()) / 2,
                              (height() - fitted.height()) / 2), fitted);
    }
    QRectF displayedText() const {
        auto rect = imageRect();
        return QRectF(rect.left() + textBounds.left() / artwork.width() * rect.width(),
                      rect.top() + textBounds.top() / artwork.height() * rect.height(),
                      textBounds.width() / artwork.width() * rect.width(),
                      textBounds.height() / artwork.height() * rect.height());
    }
  public:
    std::function<void(QPointF)> moved;
    explicit CoverPreview(QWidget* parent = nullptr) : QWidget(parent) {
        setMinimumSize(320, 320);
        setMouseTracking(true);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    }
    void setImage(const QImage& image, const QRectF& text = {}) {
        artwork = image;
        display = {};
        textBounds = text;
        update();
    }
  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter painter(this);
        painter.fillRect(rect(), QColor("#eeeaf5"));
        if (artwork.isNull()) {
            painter.setPen(QColor("#8f85a3"));
            painter.drawText(rect(), Qt::AlignCenter, "Предпросмотр");
            return;
        }
        const auto bounds = imageRect();
        const auto pixels = QSize(qMax(1, qRound(bounds.width() * devicePixelRatioF())),
                                  qMax(1, qRound(bounds.height() * devicePixelRatioF())));
        // QImage's area resampling keeps fine lettering stable when a large
        // cover is reduced to a preview, including on high-DPI displays.
        if (display.size() != pixels)
            display = artwork.scaled(pixels, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
        painter.setRenderHint(QPainter::SmoothPixmapTransform);
        painter.drawImage(bounds, display);
        if (moved && !textBounds.isEmpty() && (hovering || dragging)) {
            painter.setPen(QPen(Qt::white, 1, Qt::DashLine));
            painter.setBrush(Qt::NoBrush);
            painter.drawRect(displayedText().adjusted(-3, -3, 3, 3));
        }
    }
    void mousePressEvent(QMouseEvent* event) override {
        if (event->button() == Qt::LeftButton && moved && !artwork.isNull() &&
            !textBounds.isEmpty() && displayedText().adjusted(-6,-6,6,6).contains(event->position())) {
            dragging = true;
            dragStart = event->position();
            anchor = QPointF(textBounds.center().x() / artwork.width() * 100,
                             textBounds.center().y() / artwork.height() * 100);
            setCursor(Qt::ClosedHandCursor);
        }
    }
    void mouseMoveEvent(QMouseEvent* event) override {
        if (dragging) {
            auto bounds = imageRect();
            auto delta = event->position() - dragStart;
            moved(QPointF(qBound(0., anchor.x() + delta.x() / bounds.width() * 100, 100.),
                          qBound(0., anchor.y() + delta.y() / bounds.height() * 100, 100.)));
        } else {
            hovering = moved && !artwork.isNull() && !textBounds.isEmpty() &&
                       displayedText().adjusted(-6,-6,6,6).contains(event->position());
            setCursor(hovering ? Qt::OpenHandCursor : Qt::ArrowCursor);
            update();
        }
    }
    void mouseReleaseEvent(QMouseEvent*) override {
        dragging = false;
        setCursor(hovering ? Qt::OpenHandCursor : Qt::ArrowCursor);
        update();
    }
    void leaveEvent(QEvent*) override { hovering = false; update(); }
};
class AudioSeekSlider final : public QSlider {
    QList<QPair<double, double>> ranges;

  public:
    explicit AudioSeekSlider(QWidget* parent = nullptr) : QSlider(Qt::Horizontal, parent) {}
    void setChanges(const QList<QPair<double, double>>& changes) {
        ranges = changes;
        update();
    }
    const QList<QPair<double, double>>& changes() const { return ranges; }

  protected:
    void paintEvent(QPaintEvent* event) override {
        QSlider::paintEvent(event);
        if (ranges.isEmpty() || maximum() <= minimum())
            return;
        QStyleOptionSlider option;
        initStyleOption(&option);
        QRect groove = style()->subControlRect(QStyle::CC_Slider, &option,
                                               QStyle::SC_SliderGroove, this);
        QRect handle = style()->subControlRect(QStyle::CC_Slider, &option,
                                               QStyle::SC_SliderHandle, this);
        double left = groove.left() + handle.width() / 2.;
        double span = qMax(0., double(groove.width() - handle.width()));
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.setClipRegion(QRegion(rect()).subtracted(QRegion(handle.adjusted(-1, -1, 1, 1))));
        painter.setPen(Qt::NoPen);
        painter.setBrush(QColor("#169c50"));
        for (auto range : ranges) {
            double a = qBound(0., (range.first * 1000 - minimum()) / (maximum() - minimum()), 1.);
            double b = qBound(0., (range.second * 1000 - minimum()) / (maximum() - minimum()), 1.);
            if (b <= a)
                continue;
            if (option.upsideDown) {
                double start = a;
                a = 1 - b;
                b = 1 - start;
            }
            double width = qMin(span, qMax(4., (b - a) * span));
            double x = qMin(left + a * span, left + span - width);
            painter.drawRoundedRect(QRectF(x, groove.center().y() - 3.5, width, 8), 2, 2);
        }
    }
};
class AudioPane final : public QGroupBox {
  public:
    QMediaPlayer* media;
    QAudioOutput* audio;
    QLabel* message;
    AudioSeekSlider* seek;
    QString file;
    explicit AudioPane(const QString& title, QWidget* parent = nullptr) : QGroupBox(title, parent) {
        auto* layout = new QVBoxLayout(this);
        message = new QLabel;
        message->setWordWrap(true);
        layout->addWidget(message);
        auto* row = new QHBoxLayout;
        layout->addLayout(row);
        auto* play = new QToolButton;
        play->setProperty("sfHelpTitle", "Прослушивание");
        play->setProperty("sfHelpKey", "audio_preview");
        play->setIcon(sf::icon("play"));
        play->setIconSize({24, 24});
        play->setFixedSize(42, 36);
        play->setAccessibleName(title);
        play->setAccessibleDescription("Слушать / пауза");
        seek = new AudioSeekSlider(this);
        seek->setProperty("sfHelpTitle", "Позиция прослушивания");
        seek->setProperty("sfHelpKey", "seek");
        seek->setRange(0, 0);
        auto* clock = new QLabel("00:00.00 / 00:00.00");
        row->addWidget(play);
        row->addWidget(seek, 1);
        row->addWidget(clock);
        media = new QMediaPlayer(this);
        audio = new QAudioOutput(this);
        audio->setVolume(.8);
        media->setAudioOutput(audio);
        QObject::connect(play, &QToolButton::clicked, this, [=, this] {
            if (media->playbackState() == QMediaPlayer::PlayingState)
                media->pause();
            else if (!file.isEmpty())
                media->play();
        });
        QObject::connect(media, &QMediaPlayer::playbackStateChanged, this,
                         [=](QMediaPlayer::PlaybackState state) {
                             play->setIcon(
                                 sf::icon(state == QMediaPlayer::PlayingState ? "pause" : "play"));
                         });
        QObject::connect(media, &QMediaPlayer::durationChanged, this, [=, this](qint64 duration) {
            seek->setRange(0, int(duration));
            clock->setText(sf::timestamp(media->position() / 1000.) + " / " +
                           sf::timestamp(duration / 1000.));
        });
        QObject::connect(media, &QMediaPlayer::positionChanged, this, [=, this](qint64 position) {
            QSignalBlocker blocker(seek);
            seek->setValue(int(position));
            clock->setText(sf::timestamp(position / 1000.) + " / " +
                           sf::timestamp(media->duration() / 1000.));
        });
        QObject::connect(seek, &QSlider::sliderMoved, media, &QMediaPlayer::setPosition);
        QObject::connect(
            media, &QMediaPlayer::errorOccurred, this,
            [this](QMediaPlayer::Error, const QString& text) { message->setText(text); });
    }
    void setFile(const QString& path) {
        if (file == path)
            return;
        media->stop();
        seek->setChanges({});
        file = path;
        media->setSource(path.isEmpty() ? QUrl() : QUrl::fromLocalFile(path));
        message->setText(path.isEmpty() ? QString() : QFileInfo(path).fileName());
    }
};
