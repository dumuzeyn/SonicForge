#include "cover_symbols.h"
#include <algorithm>
#include <cmath>
#include <numbers>

namespace sf {
namespace {
constexpr double pi = std::numbers::pi;
// Whole words and explicit forms keep «Мечта» distinct from «Меч» and Sunday from sun.
const QList<QPair<QString, QString>>& catalog() {
    static const QList<QPair<QString, QString>> entries{
        {"mirror", "mirror зеркало зеркала осколки обман"},
        {"heart", "heart love сердце сердца любовь любви люблю"},
        {"feather", "feather fallen falling перо перья падение падаю"},
        {"claw", "claw animal beast когти зверь"},
        {"prism", "prism crystal glass robot кристалл стекло робот"},
        {"star", "star stars space cosmic звезда звезды космос"},
        {"flame", "flame fire burn огонь пламя горит"},
        {"moon", "moon night luna луна луны лунный ночь ночи"},
        {"sun", "sun daylight summer солнце солнца рассвет лето"},
        {"wave", "wave ocean sea water волна волны океан море вода"},
        {"mountain", "mountain summit peak гора горы вершина"},
        {"eye", "eye watch vision глаз глаза взгляд"},
        {"hourglass", "hourglass time hour clock время часы песок"},
        {"key", "key secret door ключ ключи секрет дверь"},
        {"wing", "wing fly flight free крыло крылья полет свобода"},
        {"flower", "flower rose blossom цветок цветы роза цветение"},
        {"crown", "crown king queen корона король королева"},
        {"lightning", "lightning thunder storm молния гроза гром"},
        {"orbit", "orbit rotate rotation орбита орбиты вращение"},
        {"bloom", "bloom rosette pulse beat dance розетка пульс ритм танец"},
        {"tree", "tree forest дерево деревья лес"},
        {"leaf", "leaf autumn лист листья листва осень"},
        {"butterfly", "butterfly бабочка бабочки мотылек"},
        {"bird", "bird raven птица птицы ворон"},
        {"dragon", "dragon дракон драконы"},
        {"skull", "skull death череп смерть"},
        {"mask", "mask theatre маска театр"},
        {"sword", "sword blade меч мечи клинок"},
        {"shield", "shield armor щит броня"},
        {"anchor", "anchor якорь якоря"},
        {"compass", "compass north компас север"},
        {"ship", "ship sail корабль парус"},
        {"planet", "planet saturn планета планеты сатурн"},
        {"comet", "comet meteor комета метеор"},
        {"spiral", "spiral whirlpool spin spinning swirl спираль водоворот кружит крутится"},
        {"labyrinth", "labyrinth maze лабиринт"},
        {"bridge", "bridge crossing мост переправа"},
        {"lantern", "lantern lighthouse фонарь маяк"},
        {"raindrop", "raindrop rain tear дождь слеза слезы капля"},
        {"snowflake", "snowflake snow winter снежинка снег зима"},
        {"cloud", "cloud облако облака"},
        {"rainbow", "rainbow радуга"},
        {"hand", "hand palm ладонь рука"},
        {"arrow", "arrow стрела стрелы"},
        {"diamond", "diamond бриллиант алмаз"},
        {"hexagon", "hexagon шестиугольник"},
        {"lotus", "lotus лотос"},
        {"swan", "swan лебедь лебеди"},
        {"fish", "fish рыба рыбы"},
        {"jellyfish", "jellyfish медуза"},
        {"shell", "shell ракушка ракушки"},
        {"antenna", "antenna signal антенна сигнал"},
        {"pyramid", "pyramid пирамида"},
        {"tower", "tower башня башни"},
        {"book", "book книга книги"},
        {"chain", "chain цепь цепи"},
        {"scales", "scales balance весы равновесие"},
        {"flask", "flask колба колбы"},
        {"atom", "atom атом атомы"},
        {"helix", "helix dna днк"},
        {"fox", "fox лиса лисы лису лисе лисой лисица лисицы лисицу лисицей"},
        {"wolf", "wolf wolves волк волка волки волков волком волчий"},
        {"cat", "cat kitten кот кота коты кошка кошки кошку котенок"},
        {"deer", "deer stag олень оленя олени оленей"},
        {"bear", "bear медведь медведя медведи медведей"},
        {"lion", "lion лев льва львы львов львица"}};
    return entries;
}
}
QStringList coverSymbolNames() {
    QStringList names;
    for (const auto& entry : catalog())
        names << entry.first;
    return names;
}
QString coverSymbolFamily(const QString& title, double drive, double bass, double brightness,
                          quint32 variation) {
    QString normalized = title.normalized(QString::NormalizationForm_C).toLower().replace(QChar(0x451), QChar(0x435));
    const auto words = normalized.split(QRegularExpression("[^\\p{L}\\p{N}]+"), Qt::SkipEmptyParts);
    QStringList matches;
    for (const auto& entry : catalog())
        for (const auto& cue : entry.second.split(' '))
            if (words.contains(cue)) {
                matches << entry.first;
                break;
            }
    if (matches.isEmpty())
        return catalog()[variation % catalog().size()].first;
    return matches[qBound(0, int((drive * .65 + bass * .20 + brightness * .15) * matches.size()),
                           int(matches.size() - 1))];
}
QPainterPath coverSymbolPath(const QString& family, double drive) {
    QPainterPath result;
    result.setFillRule(Qt::WindingFill);
    // Boolean path operations flatten curves at device precision. Work at cover
    // resolution so normalized 0..1 curves retain their smooth silhouettes.
    constexpr double curveResolution = 8192;
    const auto up = QTransform::fromScale(curveResolution, curveResolution);
    const auto down = QTransform::fromScale(1 / curveResolution, 1 / curveResolution);
    auto unite = [&](const QPainterPath& path) {
        result = down.map(up.map(result).united(up.map(path)));
    };
    auto subtract = [&](const QPainterPath& path) {
        result = down.map(up.map(result).subtracted(up.map(path)));
    };
    auto poly = [&](std::initializer_list<QPointF> points) {
        QPainterPath p;
        bool first = true;
        for (auto point : points) {
            if (first) p.moveTo(point); else p.lineTo(point);
            first = false;
        }
        p.closeSubpath();
        unite(p);
    };
    auto stroke = [&](const QPainterPath& p, double width = .035) {
        QPainterPathStroker stroker;
        stroker.setWidth(width * (.85 + drive * .4) * curveResolution);
        stroker.setCapStyle(Qt::RoundCap);
        stroker.setJoinStyle(Qt::RoundJoin);
        unite(down.map(stroker.createStroke(up.map(p))));
    };
    auto line = [&](std::initializer_list<QPointF> points, double width = .035) {
        QPainterPath p;
        bool first = true;
        for (auto point : points) {
            if (first) p.moveTo(point); else p.lineTo(point);
            first = false;
        }
        stroke(p, width);
    };
    auto ellipse = [&](double x, double y, double w, double h, bool filled = true) {
        QPainterPath p;
        p.addEllipse(QRectF(x, y, w, h));
        if (filled) unite(p); else stroke(p);
    };
    auto curve = [&](QPointF a, QPointF b, QPointF c, QPointF d, double width = .04) {
        QPainterPath p;
        p.moveTo(a); p.cubicTo(b, c, d); stroke(p, width);
    };
    auto cutEllipse = [&](double x, double y, double w, double h) {
        QPainterPath p; p.addEllipse(QRectF(x, y, w, h)); subtract(p);
    };
    auto radial = [&](int count, double inner, double outer) {
        QPainterPath p;
        for (int i = 0; i < count * 2; ++i) {
            double a = -pi / 2 + i * pi / count, r = i % 2 ? inner : outer;
            QPointF point(.5 + std::cos(a) * r, .5 + std::sin(a) * r);
            if (i == 0) p.moveTo(point); else p.lineTo(point);
        }
        p.closeSubpath(); unite(p);
    };
    if (family == "heart") {
        QPainterPath p; p.moveTo(.5,.27);
        p.cubicTo(.13,-.04,.01,.43,.5,.89); p.cubicTo(.99,.43,.87,-.04,.5,.27);
        result = p;
    } else if (family == "mirror" || family == "prism" || family == "diamond") {
        if (family == "mirror") {
            poly({{.25,.1},{.74,.12},{.89,.43},{.78,.86},{.26,.91},{.1,.56}});
            cutEllipse(.22,.22,.55,.55);
            line({{.43,.14},{.49,.38},{.36,.54},{.61,.65},{.54,.88}},.02);
        } else {
            if (family == "prism")
                poly({{.5,.05},{.85,.36},{.73,.76},{.42,.93},{.14,.64},{.19,.23}});
            else
                poly({{.18,.30},{.32,.10},{.69,.10},{.84,.30},{.51,.91}});
            line({{.18,.3},{.84,.3}},.018);
            QPainterPath cuts; cuts.moveTo(.32,.1); cuts.lineTo(.44,.3); cuts.lineTo(.51,.91);
            cuts.moveTo(.69,.1); cuts.lineTo(.58,.3); cuts.lineTo(.51,.91);
            QPainterPathStroker s; s.setWidth(.022 * curveResolution); subtract(down.map(s.createStroke(up.map(cuts))));
            if (family == "prism") line({{.18,.3},{.51,.52},{.84,.3}},.018);
        }
    } else if (family == "feather" || family == "leaf" || family == "wing") {
        QPainterPath p; p.moveTo(.2,.87); p.cubicTo(.12,.3,.48,.03,.83,.12);
        p.cubicTo(.89,.56,.49,.81,.2,.87); result = p;
        QPainterPath veins; veins.moveTo(.2,.89); veins.lineTo(.77,.18);
        for (int i = 1; i < 8; ++i) {
            double t = i / 9., x = .23 + .5*t, y = .84 - .64*t;
            veins.moveTo(x-.12,y-.12); veins.lineTo(x,y); veins.lineTo(x+.15,y+.01);
        }
        QPainterPathStroker s; s.setWidth((family == "leaf" ? .015 : .024) * curveResolution);
        subtract(down.map(s.createStroke(up.map(veins))));
        if (family == "wing") curve({.2,.87},{.5,.6},{.4,.17},{.9,.07},.05);
    } else if (family == "claw") {
        for (int i=0;i<3;++i) curve({.17+i*.25,.87},{.55+i*.17,.56},{.05+i*.27,.38},{.3+i*.24,.1},.065);
    } else if (family == "star") {
        radial(8,.12,.44); cutEllipse(.43,.43,.14,.14);
    } else if (family == "flame" || family == "raindrop") {
        QPainterPath p; p.moveTo(.5,.06);
        p.cubicTo(.55,.37,.88,.46,.82,.68); p.cubicTo(.78,.99,.16,.99,.17,.64);
        p.cubicTo(.16,.43,.45,.31,.5,.06); result = p;
        if (family == "flame") cutEllipse(.36,.52,.24,.3);
    } else if (family == "moon") {
        ellipse(.13,.08,.74,.83); cutEllipse(.37,.02,.61,.72);
    } else if (family == "sun" || family == "snowflake") {
        if (family == "sun") ellipse(.31,.31,.38,.38);
        int count = family == "sun" ? 12 : 6;
        for (int i=0;i<count;++i) {
            double a=i*2*pi/count;
            auto point=[&](double r,double angle){return QPointF(.5+std::cos(angle)*r,.5+std::sin(angle)*r);};
            line({point(family=="sun"?.29:0,a),point(.44,a)});
            if (family=="snowflake") {
                QPointF mid=point(.28,a);
                line({mid+QPointF(std::cos(a+pi*.7)*.13,std::sin(a+pi*.7)*.13),mid,
                      mid+QPointF(std::cos(a-pi*.7)*.13,std::sin(a-pi*.7)*.13)},.025);
            }
        }
    } else if (family == "wave") {
        for(int i=0;i<3;++i) curve({.08,.4+i*.16},{.4,.04+i*.16},{.59,.8+i*.05},{.92,.35+i*.16},.045);
    } else if (family == "mountain") {
        poly({{.06,.85},{.37,.17},{.55,.58},{.7,.3},{.95,.85}});
        poly({{.28,.38},{.37,.17},{.47,.41},{.37,.34}});
    } else if (family == "eye") {
        curve({.06,.5},{.33,.08},{.68,.08},{.94,.5});
        curve({.06,.5},{.33,.92},{.68,.92},{.94,.5}); ellipse(.34,.34,.32,.32); cutEllipse(.44,.44,.12,.12);
    } else if (family == "hourglass") {
        line({{.2,.1},{.8,.1}},.06); line({{.2,.9},{.8,.9}},.06);
        line({{.25,.12},{.27,.3},{.5,.5},{.73,.7},{.75,.88},{.25,.88},{.27,.7},{.5,.5},{.73,.3},{.75,.12}});
        poly({{.32,.82},{.5,.61},{.68,.82}});
    } else if (family == "key") {
        ellipse(.13,.1,.4,.4,false); line({{.47,.44},{.83,.84},{.9,.77}},.07);
        line({{.64,.64},{.74,.55}},.065);
    } else if (family == "flower" || family == "bloom" || family == "lotus") {
        int count=family=="bloom"?9:family=="flower"?6:5;
        for(int i=0;i<count;++i) {
            double a=2*pi*i/count;
            QPainterPath petal; petal.addEllipse(QRectF(.4,.07,.2,.43));
            QTransform tr; tr.translate(.5,.5); tr.rotate(a*180/pi); tr.translate(-.5,-.5);
            unite(tr.map(petal));
        }
        cutEllipse(.4,.4,.2,.2); ellipse(.46,.46,.08,.08);
        if (family=="lotus") line({{.12,.78},{.5,.9},{.88,.78}});
    } else if (family == "crown") {
        poly({{.15,.3},{.33,.52},{.5,.12},{.67,.52},{.85,.3},{.76,.81},{.24,.81}});
        line({{.25,.89},{.75,.89}},.055);
    } else if (family == "lightning") {
        poly({{.51,.05},{.22,.55},{.47,.55},{.36,.96},{.81,.39},{.55,.4},{.72,.05}});
    } else if (family == "orbit" || family == "planet" || family == "atom") {
        int count=family=="planet"?1:family=="orbit"?2:3;
        for(int i=0;i<count;++i) {
            QPainterPath ring; ring.addEllipse(QRectF(.07,.34,.86,.32));
            QTransform tr; tr.translate(.5,.5); tr.rotate(-25+i*60); tr.translate(-.5,-.5);
            stroke(tr.map(ring),.025);
        }
        double r=family=="planet"?.23:.065; ellipse(.5-r,.5-r,r*2,r*2);
    } else if (family == "tree") {
        ellipse(.17,.17,.39,.4); ellipse(.39,.08,.4,.42); ellipse(.43,.29,.4,.33);
        line({{.5,.9},{.5,.43},{.3,.3}},.07); line({{.5,.63},{.72,.38}},.06);
    } else if (family == "butterfly") {
        for(double sign:{-1.,1.}) {
            QPainterPath p; p.moveTo(.5,.45); p.cubicTo(.5+sign*.6,-.2,.5+sign*.5,.6,.5,.59);
            p.cubicTo(.5+sign*.5,.95,.5+sign*.4,.25,.5,.45); unite(p);
        }
        line({{.5,.3},{.5,.8}},.04); line({{.4,.18},{.5,.33},{.6,.18}},.02);
    } else if (family == "bird" || family == "swan") {
        if(family=="bird") {
            curve({.09,.6},{.25,.21},{.43,.24},{.5,.55},.065);
            curve({.5,.55},{.58,.18},{.77,.22},{.93,.5},.065);
        } else {
            ellipse(.19,.55,.61,.29); curve({.7,.66},{.96,.32},{.42,.35},{.69,.15},.075);
            ellipse(.61,.1,.16,.14); poly({{.73,.15},{.88,.22},{.75,.23}});
        }
    } else if (family == "dragon") {
        poly({{.15,.78},{.3,.52},{.12,.25},{.46,.35},{.58,.12},{.81,.18},{.9,.37},{.68,.32},
              {.72,.53},{.55,.71},{.57,.89},{.37,.74}}); cutEllipse(.71,.21,.04,.04);
    } else if (family == "skull" || family == "mask") {
        ellipse(.17,.11,.66,.69); poly({{.31,.55},{.7,.55},{.65,.91},{.36,.91}});
        cutEllipse(.28,.36,.18,.19); cutEllipse(.55,.36,.18,.19);
        if(family=="skull") {cutEllipse(.46,.59,.09,.12); for(int i=0;i<3;++i) line({{.42+i*.08,.77},{.42+i*.08,.88}},.015);}
        else curve({.34,.66},{.45,.81},{.6,.81},{.68,.63},.035);
    } else if (family == "sword" || family == "arrow") {
        if(family=="sword") {
            poly({{.48,.07},{.59,.27},{.56,.66},{.65,.69},{.65,.76},{.54,.74},{.53,.93},{.46,.93},
                  {.45,.74},{.34,.76},{.34,.69},{.44,.66},{.42,.27}});
        } else poly({{.16,.84},{.1,.77},{.63,.25},{.43,.21},{.88,.08},{.8,.54},{.74,.35}});
    } else if (family == "shield") {
        QPainterPath p; p.moveTo(.18,.17); p.lineTo(.5,.08); p.lineTo(.82,.17);
        p.cubicTo(.86,.65,.67,.83,.5,.94); p.cubicTo(.32,.83,.14,.65,.18,.17); result=p;
        QPainterPath inset; inset.moveTo(.5,.18); inset.lineTo(.5,.8); stroke(inset,.025);
    } else if (family == "anchor") {
        ellipse(.4,.08,.2,.2,false); line({{.5,.3},{.5,.84}},.06); line({{.28,.39},{.72,.39}},.05);
        curve({.15,.59},{.22,.98},{.79,.98},{.85,.59},.06);
        poly({{.11,.68},{.15,.48},{.31,.62}}); poly({{.69,.62},{.85,.48},{.89,.68}});
    } else if (family == "compass") {
        ellipse(.1,.1,.8,.8,false); radial(4,.07,.44); cutEllipse(.46,.46,.08,.08);
    } else if (family == "ship") {
        poly({{.1,.69},{.9,.69},{.75,.88},{.27,.88}}); line({{.49,.13},{.49,.7}});
        poly({{.44,.18},{.13,.61},{.44,.61}}); poly({{.55,.25},{.82,.6},{.55,.6}});
    } else if (family == "comet") {
        ellipse(.12,.57,.3,.3); line({{.3,.7},{.84,.14}},.06);
        line({{.17,.54},{.64,.15}},.035); line({{.44,.83},{.9,.34}},.03);
    } else if (family == "spiral" || family == "helix") {
        QPainterPath p,q;
        for(int i=0;i<=180;++i) {
            double t=i/180., a=t*5*pi, r=.035+.39*t;
            QPointF v=family=="spiral"?QPointF(.5+std::cos(a)*r,.5+std::sin(a)*r):QPointF(.5+.23*std::sin(t*3*pi),.09+.82*t);
            if(i==0) p.moveTo(v); else p.lineTo(v);
            if(family=="helix") {
                QPointF other(1-v.x(),v.y()); if(i==0) q.moveTo(other); else q.lineTo(other);
                if(i%18==9) line({v,other},.02);
            }
        }
        stroke(p); stroke(q);
    } else if (family == "labyrinth") {
        line({{.91,.89},{.09,.89},{.09,.1},{.9,.1},{.9,.72},{.27,.72},{.27,.28},{.72,.28},{.72,.54},{.45,.54}},.045);
    } else if (family == "bridge") {
        line({{.09,.73},{.91,.73}},.06); line({{.23,.16},{.23,.85}},.05); line({{.77,.16},{.77,.85}},.05);
        curve({.05,.5},{.31,.86},{.69,.86},{.95,.5});
        for(int i=0;i<7;++i) { double x=.2+i*.1; line({{x,.44+.22*std::sin((x-.2)/.6*pi)},{x,.73}},.018); }
    } else if (family == "lantern") {
        ellipse(.39,.08,.22,.23,false); poly({{.26,.34},{.74,.34},{.68,.82},{.32,.82}});
        line({{.23,.29},{.77,.29}},.04); line({{.27,.88},{.73,.88}},.05); cutEllipse(.4,.47,.2,.25);
    } else if (family == "cloud") {
        ellipse(.12,.37,.42,.36); ellipse(.3,.2,.43,.53); ellipse(.57,.39,.32,.34);
    } else if (family == "rainbow" || family == "antenna") {
        for(int i=0;i<3;++i) { QPainterPath p; double inset=.1+i*.12;
            p.arcMoveTo(QRectF(inset,.18+inset*.4,1-2*inset,.85-inset),0);
            p.arcTo(QRectF(inset,.18+inset*.4,1-2*inset,.85-inset),0,180); stroke(p,.04);
        }
        if(family=="antenna") {line({{.5,.45},{.5,.89}},.05); line({{.32,.9},{.68,.9}}); ellipse(.44,.39,.12,.12);}
    } else if (family == "hand") {
        poly({{.27,.46},{.73,.46},{.7,.75},{.59,.9},{.36,.86},{.18,.65},{.08,.42},{.15,.38},{.3,.57}});
        for(int i=0;i<4;++i) line({{.32+i*.11,.6},{.32+i*.11,.13+std::abs(i-1)*.07}},.085);
    } else if (family == "hexagon") {
        radial(6,.37,.43); cutEllipse(.25,.25,.5,.5); ellipse(.44,.44,.12,.12);
    } else if (family == "fish") {
        QPainterPath p; p.moveTo(.14,.51); p.cubicTo(.4,.16,.69,.2,.79,.5);
        p.cubicTo(.66,.79,.33,.85,.14,.51); result=p;
        poly({{.71,.51},{.94,.26},{.94,.76}}); cutEllipse(.28,.42,.055,.055);
    } else if (family == "jellyfish") {
        QPainterPath p; p.moveTo(.16,.48); p.cubicTo(.16,.03,.84,.03,.84,.48);
        p.cubicTo(.69,.58,.32,.57,.16,.48); result=p;
        for(int i=0;i<5;++i) { double x=.24+i*.13; curve({x,.49},{x-.12,.65},{x+.13,.75},{x-.04,.91},.026); }
    } else if (family == "shell") {
        QPainterPath p; p.moveTo(.5,.8); p.arcTo(QRectF(.08,.2,.84,1.0),0,180); p.closeSubpath(); result=p;
        for(int i=0;i<7;++i) { double a=pi+.2+i*(pi-.4)/6; line({{.5,.74},{.5+.4*std::cos(a),.72+.48*std::sin(a)}},.025); }
    } else if (family == "pyramid") {
        poly({{.5,.08},{.09,.86},{.91,.86}}); line({{.5,.08},{.5,.86},{.7,.75}},.022);
    } else if (family == "tower") {
        poly({{.26,.91},{.3,.3},{.2,.3},{.2,.12},{.31,.12},{.31,.22},{.44,.22},{.44,.1},
              {.56,.1},{.56,.22},{.69,.22},{.69,.12},{.8,.12},{.8,.3},{.7,.3},{.74,.91}});
        cutEllipse(.44,.38,.12,.16); cutEllipse(.44,.62,.12,.16);
    } else if (family == "book") {
        line({{.5,.34},{.43,.25},{.12,.19},{.12,.79},{.43,.85},{.5,.92},{.57,.85},{.88,.79},{.88,.19},{.57,.25},{.5,.34},{.5,.86}},.04);
        for(double y:{.4,.52,.64}) {line({{.2,y},{.4,y+.04}},.018); line({{.6,y+.04},{.8,y}},.018);}
    } else if (family == "chain") {
        for(int i=0;i<3;++i) {
            QPainterPath ring; ring.addEllipse(QRectF(.08+i*.22,.6-i*.22,.4,.21));
            QTransform tr; tr.translate(.28+i*.22,.705-i*.22); tr.rotate(-42); tr.translate(-.28-i*.22,-.705+i*.22);
            stroke(tr.map(ring),.045);
        }
    } else if (family == "scales") {
        line({{.5,.16},{.5,.84}},.05); line({{.18,.32},{.82,.26}},.04); line({{.32,.89},{.68,.89}},.06);
        for(double x:{.22,.78}) {line({{x,.3},{x-.13,.64},{x+.13,.64},{x,.3}},.02); curve({x-.14,.65},{x-.12,.8},{x+.12,.8},{x+.14,.65},.04);}
    } else if (family == "flask") {
        poly({{.38,.11},{.62,.11},{.62,.18},{.57,.18},{.57,.44},{.85,.85},{.8,.92},{.2,.92},
              {.15,.85},{.43,.44},{.43,.18},{.38,.18}}); cutEllipse(.35,.68,.12,.12); cutEllipse(.56,.77,.08,.08);
    } else if (family == "fox" || family == "wolf") {
        if (family == "fox") {
            poly({{.13,.08},{.39,.29},{.61,.29},{.87,.08},{.82,.48},{.94,.53},
                  {.73,.73},{.5,.94},{.27,.73},{.06,.53},{.18,.48}});
            QPainterPath cheeks;
            cheeks.moveTo(.08,.53); cheeks.cubicTo(.29,.49,.33,.72,.5,.84);
            cheeks.cubicTo(.67,.72,.71,.49,.92,.53);
            QPainterPathStroker s; s.setWidth(.025 * curveResolution); subtract(down.map(s.createStroke(up.map(cheeks))));
        } else {
            poly({{.16,.06},{.41,.25},{.59,.25},{.84,.06},{.81,.43},{.92,.66},
                  {.69,.78},{.59,.93},{.41,.93},{.31,.78},{.08,.66},{.19,.43}});
            cutEllipse(.36,.65,.28,.18);
        }
        cutEllipse(.28,.43,.12,.055); cutEllipse(.60,.43,.12,.055);
        cutEllipse(.45,.77,.10,.065);
    } else if (family == "cat") {
        ellipse(.19,.29,.62,.55);
        poly({{.2,.45},{.18,.08},{.42,.31}}); poly({{.58,.31},{.82,.08},{.8,.45}});
        cutEllipse(.30,.46,.12,.065); cutEllipse(.58,.46,.12,.065); cutEllipse(.46,.63,.08,.065);
        for (double y : {.61,.71}) {
            line({{.07,y-.03},{.32,y}},.02); line({{.68,y},{.93,y-.03}},.02);
        }
    } else if (family == "deer") {
        poly({{.34,.38},{.66,.38},{.7,.58},{.57,.9},{.43,.9},{.3,.58}});
        poly({{.32,.47},{.12,.38},{.18,.59},{.33,.61}});
        poly({{.68,.47},{.88,.38},{.82,.59},{.67,.61}});
        line({{.37,.41},{.24,.27},{.23,.07}},.04); line({{.63,.41},{.76,.27},{.77,.07}},.04);
        line({{.24,.27},{.10,.20},{.07,.08}},.025); line({{.76,.27},{.90,.20},{.93,.08}},.025);
        line({{.24,.19},{.36,.1}},.025); line({{.76,.19},{.64,.1}},.025);
        cutEllipse(.37,.53,.07,.06); cutEllipse(.56,.53,.07,.06); cutEllipse(.46,.79,.08,.06);
    } else if (family == "bear" || family == "lion") {
        if (family == "lion") {
            radial(12,.34,.46); cutEllipse(.21,.23,.58,.6); ellipse(.27,.28,.46,.51);
        } else {
            ellipse(.13,.14,.25,.27); ellipse(.62,.14,.25,.27); ellipse(.19,.26,.62,.6);
        }
        cutEllipse(.32,.44,.09,.08); cutEllipse(.59,.44,.09,.08);
        cutEllipse(.36,.60,.28,.18); ellipse(.44,.61,.12,.09);
    }
    return result;
}
CoverColors coverColors(const QImage& background) {
    // Pick a prominent hue from the whole texture, rather than the single pixel
    // beneath the symbol. Bright chromatic areas carry more weight than shadows.
    constexpr int bins = 24;
    double weights[bins]{}, sine[bins]{}, cosine[bins]{}, saturation[bins]{};
    double localLight = 0;
    int localCount = 0;
    const auto sample = background.scaled(64, 64, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
    for (int y = 0; y < sample.height(); ++y)
        for (int x = 0; x < sample.width(); ++x) {
            auto color = sample.pixelColor(x, y);
            double h = color.hslHueF(), s = color.hslSaturationF();
            double chroma = std::max({color.redF(), color.greenF(), color.blueF()}) -
                            std::min({color.redF(), color.greenF(), color.blueF()});
            if (h >= 0 && s > .08) {
                int bin = qMin(bins - 1, int(h * bins));
                double weight = chroma * (.35 + color.lightnessF());
                weights[bin] += weight;
                sine[bin] += std::sin(h * 2 * pi) * weight;
                cosine[bin] += std::cos(h * 2 * pi) * weight;
                saturation[bin] += s * weight;
            }
            if (x >= 16 && x < 48 && y >= 9 && y < 36) {
                localLight += color.lightnessF();
                ++localCount;
            }
        }
    int dominant = int(std::max_element(std::begin(weights), std::end(weights)) - std::begin(weights));
    double h = 0, s = 0;
    if (weights[dominant] > 0) {
        double sumSin = 0, sumCos = 0, sumSat = 0, sumWeight = 0;
        for (int offset = -1; offset <= 1; ++offset) {
            int bin = (dominant + offset + bins) % bins;
            sumSin += sine[bin]; sumCos += cosine[bin];
            sumSat += saturation[bin]; sumWeight += weights[bin];
        }
        h = std::atan2(sumSin, sumCos) / (2 * pi);
        if (h < 0) h += 1;
        s = qBound(0., sumSat / sumWeight, .65);
    }
    bool lightSymbol = localLight / qMax(1, localCount) < .5;
    CoverColors colors;
    colors.symbol = QColor::fromHslF(h, s * .55, lightSymbol ? .86 : .24);
    colors.highlight = colors.title = colors.artist = colors.symbol;
    colors.shadow = QColor::fromHslF(h, s * .85, lightSymbol ? .40 : .16);
    return colors;
}
void paintCoverSymbol(QPainter& painter, int size, const QString& title, const QVector<double>& music,
                      const CoverColors& colors) {
    double drive=music.value(0,.4), bass=music.value(1,.4), brightness=music.value(2,.3);
    auto path=coverSymbolPath(coverSymbolFamily(title,drive,bass,brightness,
                                              quint32(music.value(4))),drive);
    QRectF bounds=path.boundingRect();
    if(bounds.isEmpty()) return;
    QTransform tr; tr.translate(size*.5,size*.35);
    tr.rotate((brightness-.35)*18);
    double extent=size*(.37+drive*.07), scale=extent/qMax(bounds.width(),bounds.height());
    tr.scale(scale*(.94+bass*.12),scale);
    tr.translate(-bounds.center().x(),-bounds.center().y()); path=tr.map(path);
    painter.save();
    QColor shadow = colors.symbol.lightnessF() > .5 ? QColor(0,0,0,120) : QColor(255,255,255,120);
    painter.translate(size*.003,size*.005); painter.fillPath(path,shadow);
    painter.translate(-size*.003,-size*.005);
    painter.setPen(QPen(colors.symbol,size*.0015)); painter.setBrush(colors.symbol); painter.drawPath(path);
    painter.restore();
}
}
