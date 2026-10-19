#include "core.h"
#include <QSvgRenderer>
namespace sf {
QString iconSvg(const QString& name, const QColor& color) {
    static const QHash<QString, QString> shapes{
        {"add", "<path d='M12 5v14M5 12h14'/>"},
        {"undo", "<path d='m8 4-5 5 5 5M3 9h10a7 7 0 0 1 7 7v3'/>"},
        {"redo", "<path d='m16 4 5 5-5 5m5-5H11a7 7 0 0 0-7 7v3'/>"},
        {"fade-in",
         "<path d='M3 19h18M4 16c7 0 9-10 16-11'/><path d='M4 19V16m16 3V5' opacity='.35'/>"},
        {"fade-out",
         "<path d='M3 19h18M4 5c7 0 9 11 16 11'/><path d='M4 19V5m16 14v-3' opacity='.35'/>"},
        {"crossfade", "<path d='M3 5c8 0 10 14 18 14M3 19C11 19 13 5 21 5'/><path d='M3 "
                      "3v18m18-18v18' opacity='.3'/>"},
        {"select", "<rect x='4' y='5' width='16' height='14' rx='2' stroke-dasharray='3 3'/><path "
                   "d='M9 3v18M15 3v18' opacity='.45'/>"},
        {"split", "<path d='M12 3v18' stroke-dasharray='2 3'/><path d='M3 "
                  "7h5v10H3m18-10h-5v10h5'/><path d='m5 4-2 3 2 3m14-6 2 3-2 3'/>"},
        {"delete", "<path d='M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7'/>"},
        {"play", "<path d='m8 4 12 8-12 8Z' fill='currentColor' stroke='none'/>"},
        {"pause", "<path d='M8 5v14M16 5v14' stroke-width='4'/>"},
        {"stop",
         "<rect x='6' y='6' width='12' height='12' rx='2' fill='currentColor' stroke='none'/>"},
        {"export", "<path d='M12 16V3m-5 5 5-5 5 5M4 14v6a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6'/>"},
        {"stems", "<path d='M4 6v12M8 3v18M12 8v8M16 5v14M20 9v6'/>"},
        {"fit", "<path d='M3 5v14M21 5v14M4 12h16m-12-4-4 4 4 4m8-8 4 4-4 4'/>"},
        {"zoom-in",
         "<circle cx='10.5' cy='10.5' r='6.5'/><path d='m16 16 5 5M7 10.5h7m-3.5-3.5v7'/>"},
        {"zoom-out", "<circle cx='10.5' cy='10.5' r='6.5'/><path d='m16 16 5 5M7 10.5h7'/>"},
        {"check", "<path d='m4 12 5 5L20 6'/>"},
        {"close", "<path d='m6 6 12 12M6 18 18 6'/>"},
        {"folder", "<path d='M3 7V5h7l2 3h9v12H3V7Z'/>"},
        {"file", "<path d='M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 13h8m-8 4h5'/>"},
        {"copy", "<rect x='8' y='8' width='12' height='13' rx='2'/><path d='M16 8V3H3v13h5'/>"},
        {"settings",
         "<path d='M4 6h16M4 12h16M4 18h16'/><circle cx='8' cy='6' r='2' fill='white'/><circle "
         "cx='16' cy='12' r='2' fill='white'/><circle cx='10' cy='18' r='2' fill='white'/>"},
        {"lyrics", "<path d='M4 5h11M4 10h8M4 15h5m9-7v10'/><ellipse cx='15' cy='19' rx='3' "
                   "ry='2'/><path d='m18 8 4-1v4'/>"},
        {"cover", "<rect x='3' y='3' width='18' height='18' rx='3'/><circle cx='8' cy='8' "
                  "r='1.5'/><path d='m4 18 5-5 4 3 4-6 4 7'/>"},
        {"link",
         "<path d='m9 15 6-6M8 13l-2 2a3.5 3.5 0 0 0 5 5l3-3m-4-10 3-3a3.5 3.5 0 0 1 5 5l-2 2'/>"},
        {"info", "<circle cx='12' cy='12' r='9'/><path d='M12 11v6m0-10v.1'/>"},
        {"volume",
         "<path d='M3 9h4l5-5v16l-5-5H3V9Zm13-2a7 7 0 0 1 0 10m3-13a11 11 0 0 1 0 16'/>"}};
    return QString("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' color='%1' "
                   "fill='none' stroke='%1' stroke-width='1.75' stroke-linecap='round' "
                   "stroke-linejoin='round'>%2</svg>")
        .arg(color.name(), shapes.value(name, shapes["info"]));
}
QIcon icon(const QString& name, const QColor& color) {
    QIcon result;
    QSvgRenderer renderer(iconSvg(name, color).toUtf8());
    for (int size : {20, 24, 32, 48, 64, 128}) {
        QPixmap pixmap(size, size);
        pixmap.fill(Qt::transparent);
        QPainter painter(&pixmap);
        renderer.render(&painter);
        result.addPixmap(pixmap);
    }
    return result;
}
} // namespace sf
