"""Twenty additional focal silhouettes, each with its own construction."""
import math

import numpy as np
from PIL import Image, ImageDraw

# Cues, angularity/mass/openness/valence/rhythm/tension, gallery label.
ADDITIONAL_SYMBOLS = {
    'cloud': (('cloud', 'облако', 'облака'), (.10,.35,.84,.55,.18,.20), 'Облако'),
    'rainbow': (('rainbow', 'радуга'), (.12,.26,.88,.90,.35,.12), 'Радуга'),
    'hand': (('hand', 'palm', 'ладонь', 'рука'), (.36,.52,.60,.62,.35,.32), 'Ладонь'),
    'arrow': (('arrow', 'стрела', 'стрелы'), (.92,.42,.34,.62,.80,.60), 'Стрела'),
    'diamond': (('diamond', 'бриллиант', 'алмаз'), (.90,.58,.32,.75,.60,.40), 'Алмаз'),
    'hexagon': (('hexagon', 'шестиугольник'), (.76,.45,.48,.50,.72,.44), 'Шестиугольник'),
    'lotus': (('lotus', 'лотос'), (.12,.32,.90,.82,.22,.15), 'Лотос'),
    'swan': (('swan', 'лебедь', 'лебеди'), (.16,.30,.90,.78,.20,.22), 'Лебедь'),
    'fish': (('fish', 'рыба', 'рыбы'), (.24,.40,.75,.60,.55,.28), 'Рыба'),
    'jellyfish': (('jellyfish', 'медуза'), (.08,.30,.88,.50,.42,.35), 'Медуза'),
    'shell': (('shell', 'ракушка', 'ракушки'), (.25,.46,.80,.68,.22,.20), 'Ракушка'),
    'antenna': (('antenna', 'signal', 'антенна', 'сигнал'), (.66,.30,.55,.55,.86,.52), 'Антенна'),
    'pyramid': (('pyramid', 'пирамида'), (.88,.85,.30,.54,.22,.48), 'Пирамида'),
    'tower': (('tower', 'башня', 'башни'), (.78,.92,.28,.44,.28,.65), 'Башня'),
    'book': (('book', 'книга', 'книги'), (.42,.50,.66,.60,.18,.25), 'Книга'),
    'chain': (('chain', 'цепь', 'цепи'), (.62,.65,.40,.38,.68,.78), 'Цепь'),
    'scales': (('scales', 'balance', 'весы', 'равновесие'), (.48,.45,.72,.66,.32,.46), 'Весы'),
    'flask': (('flask', 'колба', 'колбы'), (.34,.42,.60,.58,.48,.40), 'Колба'),
    'atom': (('atom', 'атом', 'атомы'), (.44,.32,.78,.66,.84,.40), 'Атом'),
    'helix': (('helix', 'dna', 'днк', 'спираль днк'), (.20,.35,.72,.58,.74,.46), 'Двойная спираль'),
}


def draw_symbol(name, size, plan):
    mask = Image.new('L', (size, size))
    draw = ImageDraw.Draw(mask)
    def points(coords):
        return [(round(x * size), round(y * size)) for x, y in coords]
    def polygon(coords, fill=255):
        draw.polygon(points(coords), fill=fill)
    def line(coords, width=.025, fill=255):
        draw.line(points(coords), fill=fill, width=max(1, round(size * width)), joint='curve')
    def ellipse(box, fill=255, outline=None, width=.02):
        draw.ellipse(tuple(round(v * size) for v in box), fill=fill,
                     outline=outline, width=max(1, round(size * width)))
    def curve(a, b, c, d):
        t = np.linspace(0, 1, 60)[:, None]
        return (1-t)**3*np.array(a)+3*(1-t)**2*t*np.array(b)+3*(1-t)*t*t*np.array(c)+t**3*np.array(d)
    def arc(box, start, end, width=.028):
        draw.arc(tuple(round(v * size) for v in box), start, end,
                 fill=255, width=max(1, round(size * width)))
    if name == 'cloud':
        ellipse((.13,.35,.49,.72));ellipse((.31,.20,.73,.73));ellipse((.58,.38,.90,.72))
        polygon(((.23,.53),(.80,.53),(.80,.72),(.23,.72)))
        line(curve((.25,.67),(.38,.58),(.55,.70),(.76,.62)),.025,0)
    elif name == 'rainbow':
        for inset in (.08,.19,.30):
            arc((inset,.17+inset/2,1-inset,1-inset/2),180,360,.045)
        ellipse((.09,.57,.25,.73));ellipse((.75,.57,.91,.73))
    elif name == 'hand':
        polygon(((.29,.47),(.72,.47),(.71,.75),(.61,.89),(.36,.85),(.22,.65)))
        for i, top in enumerate((.23,.12,.17,.30)):
            x=.29+i*.11
            draw.rounded_rectangle((round(x*size),round(top*size),round((x+.09)*size),round(.62*size)),
                                   radius=round(size*.04),fill=255)
        polygon(((.31,.59),(.13,.37),(.08,.41),(.17,.67),(.36,.77)))
        line(curve((.33,.63),(.46,.56),(.58,.61),(.63,.70)),.018,0)
    elif name == 'arrow':
        polygon(((.16,.84),(.10,.77),(.63,.25),(.43,.21),(.88,.08),(.80,.54),(.74,.35)))
    elif name == 'diamond':
        polygon(((.18,.30),(.32,.11),(.69,.11),(.84,.30),(.51,.91)))
        for coords in (((.18,.30),(.84,.30)),((.32,.11),(.44,.30),(.51,.91)),
                       ((.69,.11),(.58,.30),(.51,.91))):line(coords,.018,0)
    elif name == 'hexagon':
        a=np.linspace(0,math.tau,7)+math.pi/6
        polygon(zip(.5+.40*np.cos(a),.5+.40*np.sin(a)))
        polygon(zip(.5+.29*np.cos(a),.5+.29*np.sin(a)),0)
        for angle in a[:-1:2]:line(((.5,.5),(.5+.32*math.cos(angle),.5+.32*math.sin(angle))),.026)
        ellipse((.44,.44,.56,.56))
    elif name == 'lotus':
        for i in range(5):
            tip=(.16+i*.17,.21+.11*abs(i-2))
            left=curve((.50,.79),(.13+i*.05,.62),(tip[0]-.08,tip[1]+.13),tip)
            right=curve(tip,(tip[0]+.10,tip[1]+.16),(.84-i*.06,.69),(.50,.79))
            polygon(np.concatenate((left,right)))
            line(left[10:],.011,0)
        arc((.10,.40,.90,.91),12,168,.055)
    elif name == 'swan':
        ellipse((.19,.53,.81,.83))
        polygon(curve((.32,.69),(.41,.39),(.76,.45),(.76,.72)))
        line(curve((.70,.62),(.94,.37),(.43,.35),(.68,.15)),.075)
        ellipse((.60,.09,.78,.24));polygon(((.74,.16),(.87,.21),(.75,.23)))
        line(curve((.27,.73),(.40,.62),(.56,.55),(.69,.57)),.018,0)
    elif name == 'fish':
        a=curve((.14,.51),(.40,.16),(.69,.20),(.79,.50))
        b=curve((.79,.50),(.66,.79),(.33,.85),(.14,.51))
        polygon(np.concatenate((a,b)));polygon(((.71,.51),(.94,.26),(.94,.76)))
        ellipse((.27,.41,.32,.46),0)
        line(curve((.49,.27),(.42,.38),(.42,.61),(.50,.73)),.02,0)
        polygon(((.45,.28),(.62,.10),(.68,.30)))
    elif name == 'jellyfish':
        polygon(np.concatenate((curve((.16,.48),(.16,.03),(.84,.03),(.84,.48)),
                                curve((.84,.48),(.69,.58),(.32,.57),(.16,.48)))))
        for i in range(5):
            x=.24+i*.13
            line(curve((x,.49),(x-.12,.65),(x+.13,.75),(x-.04,.91)),.025+.008*(i%2))
        line(curve((.22,.41),(.42,.28),(.59,.28),(.78,.41)),.018,0)
    elif name == 'shell':
        a=np.linspace(math.pi,math.tau,140)
        polygon(np.column_stack((.5+.42*np.cos(a),.72+.50*np.sin(a))))
        ellipse((.37,.67,.63,.82))
        for angle in np.linspace(math.pi+.22,math.tau-.22,7):
            line(((.5,.75),(.5+.40*math.cos(angle),.72+.48*math.sin(angle))),.014,0)
    elif name == 'antenna':
        polygon(((.47,.37),(.53,.37),(.53,.87),(.47,.87)))
        polygon(((.31,.89),(.69,.89),(.63,.80),(.37,.80)))
        ellipse((.43,.28,.57,.42))
        for width, height in ((.25,.20),(.40,.33)):
            arc((.5-width,.34-height,.5+width,.34+height),205,335,.028)
    elif name == 'pyramid':
        polygon(((.50,.08),(.09,.86),(.91,.86)))
        polygon(((.50,.08),(.50,.86),(.70,.75)),0)
        line(((.15,.78),(.50,.68),(.85,.78)),.018,0)
    elif name == 'tower':
        polygon(((.26,.91),(.30,.30),(.20,.30),(.20,.12),(.31,.12),(.31,.22),(.44,.22),
                 (.44,.10),(.56,.10),(.56,.22),(.69,.22),(.69,.12),(.80,.12),(.80,.30),(.70,.30),(.74,.91)))
        for y in (.39,.59):
            draw.rounded_rectangle((round(.44*size),round(y*size),round(.56*size),round((y+.11)*size)),
                                   radius=round(.04*size),fill=0)
        polygon(((.44,.91),(.44,.78),(.56,.78),(.56,.91)),0)
    elif name == 'book':
        polygon(((.12,.19),(.43,.25),(.5,.34),(.57,.25),(.88,.19),(.88,.79),(.57,.85),(.5,.92),(.43,.85),(.12,.79)))
        line(((.5,.34),(.5,.86)),.028,0)
        for y in (.40,.52,.64):
            line(((.20,y),(.40,y+.04)),.018,0);line(((.60,y+.04),(.80,y)),.018,0)
    elif name == 'chain':
        for i in range(3):
            layer=Image.new('L',mask.size);ld=ImageDraw.Draw(layer)
            cx=.28+i*.22;cy=.72-i*.22
            ld.ellipse((round((cx-.20)*size),round((cy-.105)*size),round((cx+.20)*size),round((cy+.105)*size)),
                       outline=255,width=max(2,round(.05*size)))
            layer=layer.rotate(42,resample=Image.Resampling.BICUBIC)
            mask=Image.fromarray(np.maximum(np.asarray(mask),np.asarray(layer)))
    elif name == 'scales':
        line(((.5,.16),(.5,.84)),.05);line(((.18,.32),(.82,.26)),.04)
        polygon(((.32,.89),(.68,.89),(.57,.79),(.43,.79)))
        for x,y in ((.22,.33),(.78,.27)):
            line(((x,y),(x-.13,y+.31),(x+.13,y+.31),(x,y)),.018)
            a=np.linspace(0,math.pi,60)
            polygon(np.column_stack((x+.145*np.cos(a),y+.31+.09*np.sin(a))))
        ellipse((.45,.11,.55,.21))
    elif name == 'flask':
        polygon(((.38,.11),(.62,.11),(.62,.18),(.57,.18),(.57,.44),(.85,.85),
                 (.80,.92),(.20,.92),(.15,.85),(.43,.44),(.43,.18),(.38,.18)))
        polygon(((.48,.20),(.52,.20),(.52,.47),(.70,.70),(.30,.70),(.48,.47)),0)
        ellipse((.33,.75,.40,.82),0);ellipse((.53,.79,.59,.85),0)
    elif name == 'atom':
        for angle in (0,60,120):
            layer=Image.new('L',mask.size)
            ImageDraw.Draw(layer).ellipse((round(.10*size),round(.35*size),round(.90*size),round(.65*size)),
                                          outline=255,width=max(2,round(.025*size)))
            layer=layer.rotate(angle,resample=Image.Resampling.BICUBIC)
            mask=Image.fromarray(np.maximum(np.asarray(mask),np.asarray(layer)))
        ImageDraw.Draw(mask).ellipse((round(.44*size),round(.44*size),round(.56*size),round(.56*size)),fill=255)
    elif name == 'helix':
        t=np.linspace(0,1,180);y=.09+.82*t
        x=.5+.22*np.sin(t*math.pi*3)
        line(zip(x,y),.035);line(zip(1-x,y),.035)
        for index in range(12,170,18):line(((x[index],y[index]),(1-x[index],y[index])),.02)
    else:
        raise ValueError(f'Unknown additional symbol: {name}')
    return mask
