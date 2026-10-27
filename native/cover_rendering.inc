// Native ports of Music2Picture's classic-crisp-v2, contour-character-v5,
// chronological-organic-v3 and rhythmic-speed-v4 renderers. The streaming
// analyzer supplies their musical inputs; NumPy/Pillow are not runtime dependencies.
QVector<double> smoothProfile(const QVector<double>& input, int radius) {
    QVector<double> output(input.size());
    double sigma = qMax(1., radius / 2.);
    for (int i = 0; i < input.size(); ++i) {
        double sum = 0, weight = 0;
        for (int offset = -radius; offset <= radius; ++offset) {
            double w = std::exp(-.5 * offset * offset / (sigma * sigma));
            sum += input[qBound(0, i + offset, int(input.size()-1))] * w;
            weight += w;
        }
        output[i] = sum / weight;
    }
    return output;
}
QList<QColor> referencePalette(const Structure& s, const CoverOptions& options) {
    if (options.colorSource == 3 && !options.palette.isEmpty()) return options.palette;
    if (options.colorSource == 0 || (options.colorSource == 4 && options.pattern == 0))
        return {QColor(22,6,42), QColor(68,18,126), QColor(86,54,168), QColor(168,54,152),
                QColor(222,82,126), QColor(224,104,84), QColor(224,134,48), QColor(218,62,80), QColor(246,88,40)};
    constexpr double keyHues[12]{42,318,24,278,55,188,210,132,338,12,258,82};
    double warmth = unit(s.bass * .65 + (1-s.brightness) * .35);
    double hue = keyHues[s.key] + (warmth-.5)*48 + (s.energy-.5)*34;
    double saturation = unit(.28+s.drive*.34+s.dynamic*.18-(1-s.flatness)*.08);
    double luminance = unit(.28+s.brightness*.34+s.energy*.16-(1-s.energy)*.11);
    double contrast = unit(.28+s.drive*.28+s.dynamic*.24+s.attackStrength*.2);
    double accent = 12+s.drive*24+s.flatness*10;
    const double offsets[5]{-14,-6,0,accent*.4,accent};
    QList<QColor> colors;
    for (int i=0;i<5;++i) {
        double h = std::fmod(hue+offsets[i]+720,360.)/360;
        colors << QColor::fromHsvF(h,qBound(.24,.28+i*.10+saturation*.18,.84),
                                   qBound(.20,.22+i*.14+luminance*.10+contrast*.03,.88));
    }
    return colors;
}
QList<double> referenceStops(const CoverOptions& options) {
    if (options.colorSource == 3) return options.stops;
    if (options.colorSource == 0 || (options.colorSource == 4 && options.pattern == 0)) return {0,.16,.29,.42,.54,.66,.78,.90,1};
    return {0,.25,.5,.75,1};
}
QImage finishReference(QImage image, const Structure& structure, const CoverOptions& options,
                       QRandomGenerator& random) {
    const int n = image.width();
    if (options.pattern != 0) {
        QImage softened(n,n,QImage::Format_RGB32), horizontal(n,n,QImage::Format_RGB32);
        constexpr int weights[5]{1,4,6,4,1};
        for (int y=0;y<n;++y) for (int x=0;x<n;++x) {
            int r=0,g=0,b=0;
            for (int k=-2;k<=2;++k) { auto p=image.pixel(qBound(0,x+k,n-1),y); int w=weights[k+2]; r+=qRed(p)*w; g+=qGreen(p)*w; b+=qBlue(p)*w; }
            horizontal.setPixel(x,y,qRgb(r/16,g/16,b/16));
        }
        for (int y=0;y<n;++y) for (int x=0;x<n;++x) {
            int r=0,g=0,b=0;
            for (int k=-2;k<=2;++k) { auto p=horizontal.pixel(x,qBound(0,y+k,n-1)); int w=weights[k+2]; r+=qRed(p)*w; g+=qGreen(p)*w; b+=qBlue(p)*w; }
            auto original=image.pixel(x,y); double mix=.24+(1-structure.drive)*.16;
            softened.setPixel(x,y,qRgb(qRound(lerp(qRed(original),r/16.,mix)),qRound(lerp(qGreen(original),g/16.,mix)),qRound(lerp(qBlue(original),b/16.,mix))));
        }
        image = softened;
    }
    if (options.colorSource == 2 || (options.colorSource == 4 && options.pattern == 2)) {
        // Hue is a chronological rhythm map; organic folds affect brightness.
        Field texture(n);
        for (int y=0;y<n;++y) for(int x=0;x<n;++x) texture.values[y*n+x]=qGray(image.pixel(x,y))/255.f;
        texture.normalize();
        QList<QColor> colors{QColor("#21103F"),QColor("#5E2A92"),QColor("#173D87"),QColor("#157FAF"),QColor("#40C8B0"),QColor("#EDD96B"),QColor("#EF743D"),QColor("#DB283D"),QColor("#870D24")};
        QList<double> stops{0,.12,.24,.35,.45,.55,.65,.75,1};
        for(int y=0;y<n;++y) for(int x=0;x<n;++x) {
            double t=double(x)/(n-1);
            double field=texture.values[y*n+x];
            auto color=palette(colors,stops,structure.curve(structure.pace,t));
            image.setPixel(x,y,qRgb(qBound(0,qRound(color.red()*(.40+field*.76)),255),qBound(0,qRound(color.green()*(.40+field*.76)),255),qBound(0,qRound(color.blue()*(.40+field*.76)),255)));
        }
    }
    for (int y=0;y<n;++y) for(int x=0;x<n;++x) {
        auto color=image.pixelColor(x,y);
        // A common luminance grain, never independent RGB speckles.
        double grain = options.pattern == 0 ? 0 : (random.generateDouble()+random.generateDouble()+random.generateDouble()-1.5)*1.1;
        auto channel=[&](int v){ return qBound(0,qRound((v+grain-127.5)*options.contrast/100.+127.5),255); };
        color=QColor(channel(color.red()),channel(color.green()),channel(color.blue()));
        float h,s,l,a; color.getHslF(&h,&s,&l,&a);
        color=QColor::fromHslF(h,unit(s*options.saturation/100.),l);
        image.setPixelColor(x,y,color);
    }
    return image;
}
Field classicField(int n, int cells, double detail, QRandomGenerator& random) {
    auto field=fbm(n,cells,1,random);
    auto fine=fbm(n,qMax(cells*4,cells+8),1,random);
    for(int i=0;i<field.values.size();++i) field.values[i]=float(lerp(field.values[i],fine.values[i],detail));
    field.normalize(); return field;
}
QImage renderClassic(const Structure& s, const CoverOptions& options, QRandomGenerator& random,
                      const Cancel& cancel) {
    const int n=qBound(192,options.size,1000);
    const double energy=s.drive, detail=options.detail/100., detailAmount=.12+.20*energy;
    int calmCells=qRound(8+8*energy),sharpCells=qRound(18+18*energy);
    auto a=classicField(n,calmCells,detailAmount*.55,random), b=classicField(n,sharpCells,detailAmount,random),
         c=classicField(n,qMax(7,calmCells-2),detailAmount*.70,random), d=classicField(n,qMax(24,sharpCells+8),qMin(.42,detailAmount+.10),random),
         micro=classicField(n,qMax(36,sharpCells*2),.36,random);
    Field signal(n), edge(n), spectral(n), sharp(n), highMap(n);
    QVector<QVector3D> rgb(n*n);
    auto colors=referencePalette(s,options); auto stops=referenceStops(options);
    auto motion=smoothProfile(s.speed,8);
    for(int y=0;y<n;++y) {
        checkpoint(cancel);
        for(int x=0;x<n;++x) {
            int i=y*n+x; double fa=a.values[i],fb=b.values[i],fc=c.values[i],fd=d.values[i];
            double part=n-1-y,frequency=x,scale=n/1000.;
            double initial=unit((part+(fa-.5)*46*scale+(fd-.5)*28*scale)/(n-1));
            double localEnergy=unit(s.curve(motion,initial)*1.8), peak=unit(s.curve(s.attack,initial)*2);
            double calm=1-localEnergy,sh=unit(localEnergy*.92+peak*.55);
            double angular=(std::abs(fd-.5)*2-.5)*(fb>=.5?1:-1);
            double partWarp=((fa-.5)*(42+62*calm)*(1-sh)+angular*(42+168*sh)*sh)*scale;
            double freqWarp=((fc-.5)*(55+78*calm)*(1-sh)+(fb-.5)*(58+205*sh)*sh)*scale;
            double soft=std::sin((x*.010+fc*5.5)*pi)*(20+45*calm)*scale;
            double triangle=2*std::abs(std::fmod(x*(.010+.012*sh)+fd*4,1.)-.5)-.5;
            partWarp+=soft*(1-sh)+triangle*(42+118*sh)*scale;
            freqWarp+=std::sin((y*.012+fa*7)*pi)*(24+102*sh)*scale;
            double stripe=std::sin((x*(.016+.010*energy)+y*(.006+.008*energy)+fa*4.2+fb*2.4-fc*3)*pi);
            double ridge=std::pow(std::abs(stripe),.34)*unit(.46+fd*.58+std::abs(fa-fb)*.46);
            signal.values[i]=float(ridge-.5);
            edge.values[i]=float(std::pow(1-unit(std::abs(stripe)*4.2),.34)*unit(.46+fb*.76+std::abs(fc-fd)*.62));
            partWarp+=(ridge-.5)*(20+74*sh)*scale; freqWarp+=stripe*(18+62*sh)*scale;
            double tp=unit((part+partWarp)/(n-1)),fp=unit((frequency+freqWarp)/(n-1));
            double spec=unit(s.spec(tp,1-fp)+(micro.values[i]-.5)*.050+(fd-.5)*.030+(ridge-.5)*.070+edge.values[i]*.125);
            double local=unit(s.curve(motion,tp)*1.8); peak=unit(s.curve(s.attack,tp)*2); sh=unit(local*.92+peak*.55);
            double bass=s.spec(tp,.12),mid=s.spec(tp,.45),high=s.spec(tp,.8),volume=s.curve(s.level,tp);
            double pixelEnergy=unit(.56*energy+.44*local+(fc-.5)*(.012+.026*sh)*(.3+detail*.4)+
                                     (spec-.5)*.05+(micro.values[i]-.5)*.025+(ridge-.5)*.055+edge.values[i]*.085+peak*.025);
            QColor base=palette(colors,stops,pixelEnergy);
            double value=unit(.13+spec*.54+volume*.24+bass*.10+peak*(.18+.20*energy));
            double boost=qBound(.78,.82+spec*.22+sh*.18,1.22)*value/qMax(.08,double(std::max({base.redF(),base.greenF(),base.blueF()})));
            QVector3D color(base.redF()*boost,base.greenF()*boost,base.blueF()*boost);
            if(options.colorSource==0 || options.colorSource==4) {
                double lane=std::pow(.5+.5*std::sin((x*.016-y*.010+fd*5+fa*1.6)*pi),3.2)*unit(.42+sh*.48+peak*.28)*.30;
                QVector3D laneColor=QVector3D(.08,.42,1)*(1-local)+QVector3D(1,.18,.54)*local;
                color=color*(1-lane)+laneColor*lane;
                color=(color-QVector3D(.5,.5,.5))*1.1+QVector3D(.5,.5,.5);
                double blueMix=unit((fb-.48)*2.65+(high-bass)*1.75+spec*.30)*unit(.92-pixelEnergy)/.92*.38;
                color=color*(1-blueMix)+QVector3D(.06,.26,1)*blueMix;
                double greenMix=unit((fc-.40)*2.65+(mid+bass-high*.35)*.95+(1-sh)*.24)*unit(.86-pixelEnergy)/.86*.28;
                color=color*(1-greenMix)+QVector3D(.04,.78,.34)*greenMix;
            }
            rgb[i]=color; spectral.values[i]=spec; sharp.values[i]=sh; highMap.values[i]=high;
        }
    }
    QImage image(n,n,QImage::Format_RGB32);
    auto at=[&](int x,int y){return ((y+n)%n)*n+(x+n)%n;};
    for(int y=0;y<n;++y) for(int x=0;x<n;++x) {
        int i=y*n+x;
        double patternEdge=edge.values[i]*(.70+detail*.25);
        double rim=qBound(0.,patternEdge*(.38+highMap.values[i]*.30+spectral.values[i]*.12),.62);
        double shadow=qBound(0.,patternEdge*(.38+sharp.values[i]*.34),.58);
        QVector3D neighbor=(rgb[at(x-3,y)]+rgb[at(x+3,y)]+rgb[at(x,y-3)]+rgb[at(x,y+3)])*.25;
        double lum=neighbor.x()*.2126+neighbor.y()*.7152+neighbor.z()*.0722;
        QVector3D saturated=QVector3D(lum,lum,lum)+(neighbor-QVector3D(lum,lum,lum))*(1.3+patternEdge*.55);
        double dark=unit((lum-.34)/.16);dark=dark*dark*(3-2*dark);
        QVector3D light=QVector3D(1,1,1)-(QVector3D(1,1,1)-saturated)*(.42-patternEdge*.10);
        QVector3D rimColor=light*(1-dark)+saturated*(.30-patternEdge*.08)*dark;
        auto color=rgb[i]*(1-shadow*(1-rim*.35))*(1-rim)+rimColor*rim;
        image.setPixel(x,y,qRgb(qBound(0,qRound(color.x()*255),255),qBound(0,qRound(color.y()*255),255),qBound(0,qRound(color.z()*255),255)));
    }
    return finishReference(image,s,options,random);
}
QImage renderOrganic(const Structure& s, const CoverOptions& options, QRandomGenerator& random,
                      const Cancel& cancel) {
    int n=qBound(192,options.size,640);
    double drive=s.drive, detail=options.detail/100.;
    double tempo=unit(drive*.8+s.regularity*.2), chaos=unit(s.flatness*.7+s.flux*.3);
    double macroScale=qBound(.22,.82-s.bass*.50+drive*.08,.90);
    double mesoScale=unit((.28+tempo*.40+s.harmonic*.22)*(.5+detail));
    double microScale=unit((.08+s.brightness*.35+drive*.48)*(.25+detail*1.5));
    double warpStrength=unit(.08+drive*.42+chaos*.20+s.dynamic*.12);
    double turbulence=unit(.05+drive*.52+chaos*.24+s.dynamic*.10);
    double vein=unit(.06+s.brightness*.25+s.dynamic*.12+drive*.48)*(.5+detail);
    if(options.pattern==2) vein*=.72;
    int warpCells=2+int(turbulence*2),macroCells=qMax(2,int(2+(1-macroScale)*4));
    auto warpX=fbm(n,warpCells,3,random,.42),warpY=fbm(n,warpCells+1,3,random,.40);
    auto macro=fbm(n,macroCells,3,random,.40),macroB=fbm(n,macroCells+1,2,random,.35);
    auto meso=fbm(n,5+int(mesoScale*8),3,random,.42),micro=fbm(n,15+int(microScale*22),2,random,.45);
    int composition=s.flatness>.6&&drive<.35?3:drive>.55&&s.regularity>.58?4:
                    drive>.65?0:s.bass>.6&&drive<.45?2:drive>.4?1:4;
    int climax=int(std::max_element(s.level.begin(),s.level.end())-s.level.begin());
    double fx=.18+double(climax)/(Structure::columns-1)*.64,fy=unit(.70-s.brightness*.32+s.bass*.15);
    double focalSize=unit(.22+s.bass*.36+s.energy*.18-(.16+drive*.42+s.harmonic*.22)*.1);
    double phase=unit(s.flux*.34+s.attackStrength*.27+s.dynamic*.24+drive*.15)*2*pi+random.generateDouble()*.3-.15;
    const auto chronologicalSpeed=smoothProfile(s.speed,36);
    Field macroMap(n),macroBMap(n),mesoMap(n),microMap(n),currents(n),compositionMap(n),base(n),cellBorder(n);
    QVector<QPointF> points;
    for(int i=0;i<3+int(s.bass*4);++i) points << QPointF(random.generateDouble()*2.3-1.15,random.generateDouble()*2.3-1.15);
    for(int y=0;y<n;++y) {
        checkpoint(cancel);
        for(int x=0;x<n;++x) {
            int i=y*n+x;
            double u=double(x)/(n-1)*2-1,v=double(y)/(n-1)*2-1;
            double wx=warpX.values[i]*2-1,wy=warpY.values[i]*2-1,strength=.12+warpStrength*.36;
            double xw=u+wx*strength,yw=v+wy*strength;
            double dx=xw-(fx*2-1),dy=yw-(fy*2-1),radius=std::hypot(dx,dy)+1e-5,angle=std::atan2(dy,dx);
            if(composition==1) {
                angle+=(1.1+turbulence*3.6)*std::exp(-radius*.72)+wx*.35;
                xw=fx*2-1+std::cos(angle)*radius; yw=fy*2-1+std::sin(angle)*radius;
            } else if(composition==2) {
                double pulse=std::sin(radius*pi*(2+tempo*3.2)+wy*2.5);
                xw+=dx/radius*pulse*strength*.42; yw+=dy/radius*pulse*strength*.42;
            } else if(composition==3) {
                xw+=std::sin(yw*pi*1.8+wy*2.2)*strength*.34;
                yw+=std::sin(xw*pi*1.5-wx*2)*strength*.34;
            } else if(composition==4) {
                double fold=std::sin((xw+yw)*pi*(1.2+s.regularity*2.2));
                xw+=fold*strength*.38; yw-=fold*strength*.22;
            } else {
                double drift=xw*std::cos(phase)+yw*std::sin(phase);
                xw+=std::sin(drift*pi*1.7+wy*2.6)*strength*.30;
                yw+=std::cos(drift*pi*1.3+wx*2.1)*strength*.20;
            }
            double a=macro.at(xw,yw),b=macroB.at(xw*.92,yw*.92),m=meso.at(xw*1.1,yw*1.1);
            macroMap.values[i]=a; macroBMap.values[i]=b;mesoMap.values[i]=m;microMap.values[i]=micro.at(xw*1.46,yw*1.46);
            double directional=xw*std::cos(phase)+yw*std::sin(phase),cross=-xw*std::sin(phase)+yw*std::cos(phase);
            double flow=directional*pi*(.72+tempo*1.15+drive*.45)+(b-.5)*pi*(1.2+warpStrength*2)+
                        (m-.5)*(.25+turbulence*.5)+std::sin(cross*pi*(.7+s.harmonic*1.1))*(.28+turbulence*.55);
            if(options.pattern==2) flow+=(m-.5)*unit(s.curve(chronologicalSpeed,double(x)/(n-1))*1.8)*1.8;
            currents.values[i]=float(.5+.5*std::sin(flow));
            double field=.5+.5*std::sin(flow*(.82+s.flux*.45)+b*1.8);
            dx=xw-(fx*2-1);dy=yw-(fy*2-1);radius=std::hypot(dx,dy);angle=std::atan2(dy,dx);
            if(composition==0) field=directional+(b-.5)*.46;
            else if(composition==1) field=.5+.5*std::sin(angle*(2+qRound(s.harmonic*2))+radius*(3.4+turbulence*2.4)+(m-.5)*1.2);
            else if(composition==2) field=unit(1-radius/(1.10+focalSize*.75)+std::cos(angle*(3+qRound(s.regularity*4)))*(.06+turbulence*.08)+(b-.5)*.18);
            else if(composition==3) {
                double first=10,second=10;
                for(auto point:points) {
                    double distance=std::pow(xw-point.x(),2)+std::pow(yw-point.y(),2);
                    if(distance<first){second=first;first=distance;}else second=qMin(second,distance);
                }
                field=std::sqrt(first);cellBorder.values[i]=std::sqrt(second)-field;
            }
            compositionMap.values[i]=field;
        }
    }
    if(composition==3) {
        cellBorder.normalize();
        for(int i=0;i<base.values.size();++i) compositionMap.values[i]=compositionMap.values[i]*.62+(1-cellBorder.values[i])*.38;
    }
    if(composition==0||composition==3) compositionMap.normalize();
    for(int i=0;i<base.values.size();++i) base.values[i]=macroMap.values[i]*.10+macroBMap.values[i]*.10+compositionMap.values[i]*.46+currents.values[i]*.34;
    base.normalize();
    Structure timeline=s;
    timeline.level=smoothProfile(s.level,36);timeline.attack=smoothProfile(s.attack,33);
    for(auto& value:timeline.speed) value=unit(value*1.8);
    timeline.speed=smoothProfile(timeline.speed,36);
    for(int band=0;band<Structure::bands;++band) {
        QVector<double> row(Structure::columns);
        for(int c=0;c<Structure::columns;++c) for(int d=-2;d<=2;++d)
            row[c]+=s.spectrum[qBound(0,band+d,Structure::bands-1)*Structure::columns+c]*(3-std::abs(d))/9.;
        row=smoothProfile(row,33);
        std::copy(row.begin(),row.end(),timeline.spectrum.begin()+band*Structure::columns);
    }
    auto colors=referencePalette(s,options);auto stops=referenceStops(options);
    double width=.34+s.harmonic*.10,center=qBound(width*.5,drive,1-width*.5),lower=center-width*.5,upper=center+width*.5;
    if(drive<.45) upper=qMin(upper,.49);else if(drive>.55)lower=qMax(lower,.51);
    QImage image(n,n,QImage::Format_RGB32);
    for(int y=0;y<n;++y) {
        checkpoint(cancel);
        for(int x=0;x<n;++x) {
            int i=y*n+x;double t=double(x)/(n-1),py=double(y)/(n-1);
            t=unit(t+std::pow(std::sin(t*pi),2)*(.026*std::sin(py*2*pi+phase)+.010*std::sin(py*4*pi-phase)));
            double field=base.values[i],position=lower+field*(upper-lower),local=drive,level=timeline.curve(timeline.level,t),spectrum=timeline.spec(t,1-py);
            if(options.pattern==2) {
                local=timeline.curve(timeline.speed,t)*unit(level/.28);
                field=unit(field*.90+spectrum*.07+level*.03);
                position=unit(position*.70+(.18+local*.64)*.30+(field-.5)*.08);
            }
            if(options.colorSource==3) position=field;
            QColor color=palette(colors,stops,position);
            double strata=.5+.5*std::sin(field*pi*(2+local*6)+(mesoMap.values[i]-.5)*.18);
            double depth=(.52+.52*field)*(.86+.14*strata);
            if(options.pattern==2) depth*=(.88+level*.12)*(.94+spectrum*.08);
            double edge=std::exp(-std::pow((strata-.91)/.045,2))*(.025+local*.045);
            double ribbonWidth=.028+(1-vein)*.040;
            double smooth=unit((macroBMap.values[i]-.22)/(.78-.22));smooth=smooth*smooth*(3-2*smooth);
            double ribbon=std::exp(-std::pow((currents.values[i]-.56)/ribbonWidth,2))*(.35+.65*smooth)*(.08+vein*.18);
            if(options.pattern==2) ribbon*=.35+local*.65+timeline.curve(timeline.attack,t)*.20;
            double shadow=1-std::exp(-std::pow((currents.values[i]-.47)/(ribbonWidth*1.8),2))*(.08+local*.12);
            double glow=(std::exp(-std::hypot(double(x)/(n-1)*2-1-(fx*2-1),double(y)/(n-1)*2-1-(fy*2-1))*(1.3+(1-focalSize)*1.8))-.35)*(10+(.34+drive*.26+s.dynamic*.25)*20);
            auto channel=[&](int v){double value=v*depth;value=lerp(value,value*.55+125,edge);value=lerp(value,value*.45+140,ribbon)*shadow+glow+(microMap.values[i]-.5)*(.8+microScale*1.8);return qBound(0,qRound(value),255);};
            image.setPixel(x,y,qRgb(channel(color.red()),channel(color.green()),channel(color.blue())));
        }
    }
    return finishReference(image,s,options,random);
}
