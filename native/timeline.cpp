#include "timeline.h"
#include <QMimeData>
#include <QMouseEvent>
#include <QScrollBar>
#include <algorithm>
#include <cmath>
Timeline::Timeline(QWidget* parent) : QAbstractScrollArea(parent) {
    setAcceptDrops(true);
    setFocusPolicy(Qt::StrongFocus);
    setMinimumHeight(160);
    setMaximumHeight(245);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    connect(horizontalScrollBar(), &QScrollBar::valueChanged, viewport(),
            qOverload<>(&QWidget::update));
    connect(verticalScrollBar(), &QScrollBar::valueChanged, viewport(),
            qOverload<>(&QWidget::update));
}
double Timeline::scale() const {
    return qMax(1., (viewport()->width() - 96) / qMax(10., project.duration())) * zoom;
}
double Timeline::at(double x) const {
    return qMax(0., (x + horizontalScrollBar()->value() - 84) / scale());
}
int Timeline::laneAt(double y) const {
    return qMax(0, int((y + verticalScrollBar()->value() - 32) / 70));
}
QString Timeline::hit(QPoint point) const {
    double time = at(point.x());
    int lane = laneAt(point.y());
    for (auto it = project.clips.rbegin(); it != project.clips.rend(); ++it)
        if (it->lane == lane && time >= it->position && time <= it->position + it->duration())
            return it->id;
    return {};
}
void Timeline::refresh() {
    horizontalScrollBar()->setRange(
        0, qMax(0, int(96 + project.duration() * scale()) - viewport()->width()));
    horizontalScrollBar()->setPageStep(viewport()->width());
    verticalScrollBar()->setRange(0,
                                  qMax(0, 32 + (project.lanes() + 1) * 70 - viewport()->height()));
    verticalScrollBar()->setPageStep(viewport()->height());
    viewport()->update();
    emit stateChanged();
}
void Timeline::fit() {
    zoom = 1;
    horizontalScrollBar()->setValue(0);
    refresh();
}
void Timeline::zoomBy(double factor, QPoint anchor) {
    if (anchor.isNull())
        anchor = QPoint(viewport()->width() / 2, 0);
    double time = at(anchor.x());
    zoom = qBound(1., zoom * factor, 4096.);
    refresh();
    horizontalScrollBar()->setValue(qRound(84 + time * scale() - anchor.x()));
    viewport()->update();
}
void Timeline::resizeEvent(QResizeEvent* event) {
    QAbstractScrollArea::resizeEvent(event);
    refresh();
}
void Timeline::paintEvent(QPaintEvent*) {
    QPainter p(viewport());
    p.setRenderHints(QPainter::Antialiasing | QPainter::TextAntialiasing);
    p.fillRect(viewport()->rect(), QColor("#f8f7fd"));
    p.translate(-horizontalScrollBar()->value(), -verticalScrollBar()->value());
    double s = scale(), width = viewport()->width() + horizontalScrollBar()->value();
    int height = qMax(viewport()->height(), 32 + (project.lanes() + 1) * 70);
    double target = 80 / s, step = 1;
    for (double candidate : {.1, .2, .5, 1., 2., 5., 10., 20., 30., 60., 120., 300., 600.})
        if (candidate >= target) {
            step = candidate;
            break;
        }
    p.setFont(QFont("Noto Sans", 9));
    for (double t = std::floor(at(0) / step) * step; t <= project.duration() + step; t += step) {
        double x = 84 + t * s;
        p.setPen(QColor("#e4e0f0"));
        p.drawLine(QPointF(x, 28), QPointF(x, height));
        p.setPen(QColor("#6d6489"));
        p.drawText(QRectF(x + 3, 4, 85, 20), sf::timestamp(t));
    }
    for (int lane = 0; lane < project.lanes(); ++lane) {
        double y = 32 + lane * 70;
        p.fillRect(QRectF(horizontalScrollBar()->value(), y, 82, 68), QColor("#f0edf8"));
        p.setPen(QColor("#534b70"));
        p.drawText(QRectF(horizontalScrollBar()->value() + 8, y + 13, 73, 20),
                   (property("english").toBool() ? "Track " : "Дорожка ") +
                       QString::number(lane + 1));
        p.setPen(QColor(project.muted.contains(lane) ? "#a49cb6" : "#7769ae"));
        p.drawText(QRectF(horizontalScrollBar()->value() + 8, y + 36, 73, 20),
                   project.muted.contains(lane)
                       ? (property("english").toBool() ? "Muted" : "Выключена")
                       : (property("english").toBool() ? "Enabled" : "Включена"));
    }
    for (auto clip : project.clips) {
        double x = 84 + clip.position * s, y = 34 + clip.lane * 70,
               w = qMax(1., clip.duration() * s);
        if (x + w < horizontalScrollBar()->value() + 82 || x > width)
            continue;
        QColor fill = QColor::fromHsl((260 + clip.lane * 43) % 360, 110, 225);
        if (project.muted.contains(clip.lane))
            fill = QColor("#e5e2eb");
        QRectF rect(x, y, w, 64);
        p.setPen(QPen(clip.id == selected ? QColor("#6b50c7") : QColor("#b8aadf"),
                      clip.id == selected ? 1.8 : 1));
        p.setBrush(fill);
        p.drawRoundedRect(rect, 4, 4);
        p.save();
        p.setClipRect(rect.adjusted(2, 2, -2, -2));
        p.setPen(QColor("#41345f"));
        p.drawText(QRectF(x + 7, y + 3, w - 14, 19), Qt::AlignLeft | Qt::AlignVCenter,
                   QFileInfo(clip.source).completeBaseName());
        const auto source = project.sources.value(clip.source);
        p.setPen(QPen(QColor("#8267ce"), 1));
        if (!source.peaks.isEmpty()) {
            int first = qMax(0, int(std::floor((horizontalScrollBar()->value() + 82 - x) / 2))),
                last = qMin(int(w / 2), int((width - x) / 2));
            for (int px = first; px <= last; ++px) {
                double time = clip.start + (px * 2 / w) * clip.duration();
                int bin = qBound(0, int(time / source.duration * source.peaks.size()),
                                 int(source.peaks.size() - 1));
                double level = source.peaks[bin] * 14;
                double edgeTime = time - clip.start;
                if (clip.fadeIn > 0)
                    level *= qBound(0., edgeTime / clip.fadeIn, 1.);
                if (clip.fadeOut > 0)
                    level *= qBound(0., (clip.duration() - edgeTime) / clip.fadeOut, 1.);
                p.drawLine(QPointF(x + px * 2, y + 43 - level),
                           QPointF(x + px * 2, y + 43 + level));
            }
        }
        p.setPen(QPen(QColor("#6e4ec6"), 1.5));
        if (clip.fadeIn > 0)
            p.drawLine(QPointF(x, y + 62), QPointF(x + clip.fadeIn * s, y + 2));
        if (clip.fadeOut > 0)
            p.drawLine(QPointF(x + w - clip.fadeOut * s, y + 2), QPointF(x + w, y + 62));
        p.restore();
    }
    if (selection && !selected.isEmpty()) {
        try {
            const auto& clip = project.get(selected);
            double a = qMin(selection->first, selection->second),
                   b = qMax(selection->first, selection->second);
            a = qMax(a, clip.position);
            b = qMin(b, clip.position + clip.duration());
            if (b > a) {
                p.fillRect(QRectF(84 + a * s, 34 + clip.lane * 70, (b - a) * s, 64),
                           QColor(113, 81, 207, 55));
                p.setPen(QPen(QColor("#6546b5"), 1, Qt::DashLine));
                p.drawRect(QRectF(84 + a * s, 34 + clip.lane * 70, (b - a) * s, 64));
            }
        } catch (...) {
        }
    }
    p.setPen(QPen(QColor("#df526a"), 1.5));
    double x = 84 + cursor * s;
    p.drawLine(QPointF(x, 27), QPointF(x, height));
    p.setBrush(QColor("#df526a"));
    p.drawPolygon(QPolygonF{{x - 4, 23}, {x + 4, 23}, {x, 28}});
    p.setPen(QPen(QColor("#c3badc"), 1, Qt::DashLine));
    p.setBrush(Qt::NoBrush);
    p.drawRoundedRect(QRectF(86, 36 + project.lanes() * 70, qMax(200., width - 96), 52), 4, 4);
    p.setPen(QColor("#8575ae"));
    p.drawText(QRectF(100, 44 + project.lanes() * 70, 250, 32),
               (property("english").toBool() ? "+  New track" : "+  Новая дорожка"));
}
void Timeline::mousePressEvent(QMouseEvent* event) {
    if (busy)
        return;
    setFocus();
    emit editStarted();
    QPoint point = event->position().toPoint();
    if (point.x() < 82 && event->button() == Qt::LeftButton) {
        int lane = laneAt(point.y());
        if (project.muted.contains(lane))
            project.muted.remove(lane);
        else
            project.muted.insert(lane);
        emit changed();
        refresh();
        return;
    }
    dragStart = point;
    anchorTime = at(point.x());
    selecting =
        event->button() == Qt::RightButton || event->modifiers().testFlag(Qt::ShiftModifier);
    seeking = point.y() + verticalScrollBar()->value() < 30 ||
              (!selecting && std::abs(at(point.x()) - cursor) * scale() < 5);
    QString clip = hit(point);
    if (!clip.isEmpty() && !seeking)
        selected = clip;
    else if (!selecting && !seeking)
        selected.clear();
    selection.reset();
    dragging.reset();
    if (!selected.isEmpty() && !seeking)
        dragging = project.get(selected);
    cursor = qBound(0., anchorTime, project.duration());
    emit cursorChanged(cursor);
    refresh();
}
void Timeline::mouseMoveEvent(QMouseEvent* event) {
    if (busy || !(event->buttons() & (Qt::LeftButton | Qt::RightButton)))
        return;
    if (selecting && dragging) {
        selection = qMakePair(anchorTime, at(event->position().x()));
        viewport()->update();
        emit stateChanged();
    } else if (seeking || !dragging) {
        cursor = qBound(0., at(event->position().x()), project.duration());
        emit cursorChanged(cursor);
        viewport()->update();
    } else {
        auto& current = project.get(dragging->id);
        current.lane = laneAt(event->position().y());
        current.position = project.freePosition(
            current.lane, qMax(0., dragging->position + at(event->position().x()) - anchorTime),
            current.duration(), current.id);
        viewport()->update();
    }
}
void Timeline::mouseReleaseEvent(QMouseEvent* event) {
    if (busy)
        return;
    if (dragging && !selecting && !seeking) {
        if ((dragStart - event->position().toPoint()).manhattanLength() > 3)
            emit changed();
        else
            project.get(dragging->id) = *dragging;
    }
    if (selection && std::abs(selection->first - selection->second) < .01)
        selection.reset();
    dragging.reset();
    selecting = seeking = false;
    refresh();
}
void Timeline::wheelEvent(QWheelEvent* event) {
    if (event->modifiers().testFlag(Qt::ControlModifier) ||
        event->modifiers().testFlag(Qt::ShiftModifier)) {
        zoomBy(std::pow(1.25, event->angleDelta().y() / 120.), event->position().toPoint());
        event->accept();
    } else
        QAbstractScrollArea::wheelEvent(event);
}
void Timeline::dragEnterEvent(QDragEnterEvent* event) {
    if (event->mimeData()->hasUrls())
        event->acceptProposedAction();
}
void Timeline::dragMoveEvent(QDragMoveEvent* event) {
    if (event->mimeData()->hasUrls())
        event->acceptProposedAction();
}
void Timeline::dropEvent(QDropEvent* event) {
    QStringList files;
    for (auto& url : event->mimeData()->urls())
        if (url.isLocalFile())
            files << url.toLocalFile();
    if (!files.isEmpty()) {
        emit imported(files, laneAt(event->position().y()), at(event->position().x()));
        event->acceptProposedAction();
    }
}
