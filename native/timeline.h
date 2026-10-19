#pragma once
#include "core.h"
#include <QAbstractScrollArea>
#include <optional>
class Timeline final : public QAbstractScrollArea {
    Q_OBJECT
  public:
    explicit Timeline(QWidget* parent = nullptr);
    sf::Project project;
    QString selected;
    double cursor = 0;
    std::optional<QPair<double, double>> selection;
    double zoom = 1;
    bool busy = false;
    void refresh();
    void fit();
    void zoomBy(double factor, QPoint anchor = {});
    double scale() const;
  signals:
    void changed();
    void cursorChanged(double);
    void editStarted();
    void imported(QStringList, int, double);
    void stateChanged();

  protected:
    void paintEvent(QPaintEvent*) override;
    void resizeEvent(QResizeEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void wheelEvent(QWheelEvent*) override;
    void dragEnterEvent(QDragEnterEvent*) override;
    void dragMoveEvent(QDragMoveEvent*) override;
    void dropEvent(QDropEvent*) override;

  private:
    double at(double x) const;
    int laneAt(double y) const;
    QString hit(QPoint point) const;
    QPoint dragStart;
    std::optional<sf::Clip> dragging;
    double anchorTime = 0;
    bool selecting = false, seeking = false;
};
