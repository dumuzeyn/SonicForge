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
    const double step = model->singleStep();
    const int count = qMin(100000, qMax(1, qRound((model->maximum() - model->minimum()) / step)));
    slider->setRange(0, count);
    slider->setMinimumWidth(120);
    auto* text = new QLabel(panel);
    text->setMinimumWidth(78);
    text->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    model->setParent(panel);
    model->hide();
    auto sync = [=](double value) {
        QSignalBlocker blocker(slider);
        slider->setValue(
            qRound((value - model->minimum()) / (model->maximum() - model->minimum()) * count));
        int decimals = scale == 100 ? 0 : model->decimals();
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
    row->addWidget(text);
    panel->setProperty("sfSlider", true);
    return panel;
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
class AudioPane final : public QGroupBox {
  public:
    QMediaPlayer* media;
    QAudioOutput* audio;
    QLabel* message;
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
        auto* seek = new QSlider(Qt::Horizontal);
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
        file = path;
        media->setSource(path.isEmpty() ? QUrl() : QUrl::fromLocalFile(path));
        message->setText(path.isEmpty() ? QString() : QFileInfo(path).fileName());
    }
};
