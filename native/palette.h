#pragma once
#include <QtWidgets>
#include <algorithm>
#include <cmath>
#include <functional>
class PaletteEditor final : public QWidget {
    QList<QColor>& colors;
    QList<double>& stops;
    int dragging = -1;

  public:
    std::function<void(int)> changed;
    PaletteEditor(QList<QColor>& colors, QList<double>& stops, QWidget* parent = nullptr)
        : QWidget(parent), colors(colors), stops(stops) {
        setMinimumHeight(82);
        setMouseTracking(true);
    }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        QRectF bar(14, 10, width() - 28, 34);
        QLinearGradient gradient(bar.topLeft(), bar.topRight());
        QList<int> order;
        for (int i = 0; i < colors.size(); ++i)
            order << i;
        std::stable_sort(order.begin(), order.end(),
                         [&](int a, int b) { return stops[a] < stops[b]; });
        for (int i : order)
            gradient.setColorAt(qBound(0., stops[i], 1.), colors[i]);
        painter.setPen(QPen(QColor("#b9adc9"), 1));
        painter.setBrush(gradient);
        painter.drawRoundedRect(bar, 6, 6);
        for (int i = 0; i < colors.size(); ++i) {
            double x = 14 + stops[i] * (width() - 28);
            painter.setPen(QPen(i == dragging ? QColor("#5940a6") : QColor("#746783"), 1.5));
            painter.setBrush(colors[i]);
            painter.drawPolygon(QPolygonF{QPointF(x, 46), QPointF(x - 7, 54), QPointF(x - 7, 68),
                                          QPointF(x + 7, 68), QPointF(x + 7, 54)});
        }
    }
    void mousePressEvent(QMouseEvent* event) override {
        if (event->button() != Qt::LeftButton)
            return;
        double best = 14;
        for (int i = 0; i < stops.size(); ++i) {
            double distance = std::abs(event->position().x() - (14 + stops[i] * (width() - 28)));
            if (distance < best) {
                best = distance;
                dragging = i;
            }
        }
        if (dragging >= 0) {
            setCursor(Qt::ClosedHandCursor);
            mouseMoveEvent(event);
        }
    }
    void mouseMoveEvent(QMouseEvent* event) override {
        if (dragging < 0) {
            setCursor(Qt::OpenHandCursor);
            return;
        }
        stops[dragging] = qBound(0., (event->position().x() - 14) / qMax(1, width() - 28), 1.);
        if (changed)
            changed(dragging);
        update();
    }
    void mouseReleaseEvent(QMouseEvent*) override {
        dragging = -1;
        setCursor(Qt::OpenHandCursor);
        update();
    }
};
