"""A small sculptural focal symbol, shaped by music and optional lyric imagery."""
from __future__ import annotations

import math
import re
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .music_lettering import design_from_music, intersection_fraction, luminance, unit


VERSION = "song-symbol-v7"
# Meaning is taken from available words, never invented from a genre label.
IMAGERY = (
    ("mirror", ("не верю", "невер", "trust", "mirror", "зеркал", "оскол", "обман")),
    ("heart", ("love", "heart", "любов", "люблю", "сердц")),
    ("feather", ("fallen", "falling", "паден", "пада", "перо")),
    ("claw", ("animal", "beast", "wolf", "звер", "волк", "когт")),
    ("prism", ("android", "robot", "glass", "crystal", "андроид", "робот", "стекл", "кристалл")),
    ("star", ("star", "space", "cosmic", "звезд", "звёзд", "космос", "interstellar")),
    ("flame", ("fire", "flame", "burn", "огонь", "плам", "горит")),
    ("moon", ("moon", "night", "luna", "луна", "лунн", "ночь", "ночн")),
    ("sun", ("sun", "daylight", "summer", "солн", "рассвет", "лето")),
    ("wave", ("ocean", "sea", "water", "wave", "океан", "море", "волн", "вода")),
    ("mountain", ("mountain", "summit", "peak", "гора", "горы", "вершин")),
    ("eye", ("eye", "watch", "vision", "глаз", "взгляд", "виден")),
    ("hourglass", ("time", "hour", "clock", "время", "час", "песок")),
    ("key", ("key", "secret", "door", "ключ", "секрет", "двер")),
    ("wing", ("wing", "fly", "flight", "free", "полёт", "полет", "свобод", "крыл")),
    ("flower", ("flower", "rose", "blossom", "цветок", "цветы", "роза", "цветени")),
    ("crown", ("crown", "king", "queen", "корон", "король", "королев")),
    ("lightning", ("lightning", "thunder", "storm", "молни", "гроза", "гром")),
    ("tree", ("tree", "forest", "дерев", "лес")),
    ("leaf", ("leaf", "autumn", "листв", "лист", "осень")),
    ("butterfly", ("butterfly", "бабоч", "мотыл")),
    ("bird", ("bird", "raven", "птиц", "ворон")),
    ("dragon", ("dragon", "дракон")),
    ("skull", ("skull", "death", "череп", "смерть")),
    ("mask", ("mask", "theatre", "маска", "театр")),
    ("sword", ("sword", "blade", "меч", "клинок")),
    ("shield", ("shield", "armor", "щит", "броня")),
    ("anchor", ("anchor", "якор")),
    ("compass", ("compass", "north", "компас", "север")),
    ("ship", ("ship", "sail", "кораб", "парус")),
    ("planet", ("planet", "saturn", "планет", "сатурн")),
    ("comet", ("comet", "meteor", "комет", "метеор")),
    ("spiral", ("spiral", "whirlpool", "spin", "spinning", "swirl", "кружит", "крутит", "спирал", "водоворот")),
    ("orbit", ("orbit", "rotate", "rotation", "орбит", "вращение", "по кругу")),
    ("bloom", ("pulse", "beat", "dance", "пульс", "ритм", "танец")),
    ("labyrinth", ("labyrinth", "maze", "лабиринт")),
    ("bridge", ("bridge", "crossing", "мост", "переправ")),
    ("lantern", ("lantern", "lighthouse", "фонарь", "маяк")),
    ("raindrop", ("raindrop", "rain", "tear", "дожд", "слеза", "капля")),
    ("snowflake", ("snowflake", "snow", "winter", "снежин", "снег", "зима")),
)

# Geometry priors, not genres or claims about the song's literal meaning.
# Each target is angularity, mass, openness, valence, rhythm, tension.
AUDIO_ARCHETYPES = {
    "mirror": (.70,.45,.30,.25,.40,.85), "heart": (.15,.35,.75,.72,.25,.35),
    "feather": (.08,.10,.90,.45,.10,.15), "claw": (.85,.90,.15,.30,.65,.85),
    "prism": (.80,.55,.30,.55,.75,.50), "star": (.45,.35,.75,.55,.25,.30),
    "flame": (.60,.75,.30,.45,.60,.65), "moon": (.10,.20,.85,.25,.15,.35),
    "sun": (.30,.55,.70,.90,.50,.15), "wave": (.20,.45,.80,.55,.55,.30),
    "mountain": (.75,.85,.45,.45,.15,.45), "eye": (.35,.30,.50,.35,.35,.65),
    "hourglass": (.50,.30,.55,.40,.75,.40), "key": (.45,.45,.65,.70,.35,.40),
    "wing": (.30,.40,.85,.75,.45,.25), "flower": (.15,.30,.80,.85,.30,.10),
    "crown": (.65,.85,.40,.65,.40,.60), "lightning": (.95,.70,.15,.50,.90,.80),
    "orbit": (.40,.35,.55,.45,.45,.75), "bloom": (.25,.65,.65,.60,.65,.25),
    "tree": (.22,.70,.75,.65,.20,.20), "leaf": (.10,.25,.92,.65,.12,.18),
    "butterfly": (.12,.16,.86,.78,.48,.12), "bird": (.24,.28,.88,.68,.40,.18),
    "dragon": (.92,.88,.20,.42,.58,.92), "skull": (.78,.62,.25,.10,.28,.82),
    "mask": (.48,.36,.38,.38,.58,.68), "sword": (.94,.56,.24,.38,.54,.72),
    "shield": (.72,.96,.36,.55,.24,.52), "anchor": (.52,.88,.62,.32,.12,.42),
    "compass": (.62,.38,.58,.60,.52,.38), "ship": (.38,.58,.74,.62,.34,.30),
    "planet": (.28,.72,.58,.48,.18,.46), "comet": (.66,.48,.68,.74,.82,.42),
    "spiral": (.36,.32,.62,.52,.68,.62), "labyrinth": (.82,.42,.28,.34,.62,.72),
    "bridge": (.46,.66,.72,.64,.46,.34), "lantern": (.18,.46,.84,.82,.16,.24),
    "raindrop": (.08,.38,.86,.30,.38,.34), "snowflake": (.58,.18,.78,.48,.56,.22),
}

# With no word evidence use geometric music gestures, not an invented object
# such as an anchor, crown, sword, or skull. All 40 remain available by meaning.
ABSTRACT_MOTIFS = ("orbit", "bloom", "spiral", "prism", "wave", "lightning")


def _words(text):
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFC", text).casefold().replace("ё", "е")))


# Explicit word forms prevent 'star' matching Starship, 'меч' matching Мечта,
# or 'лес' matching Лестница. This bounded vocabulary is not a language model.
_FORMS = {
    "невер": "неверие неверия неверием", "зеркал": "зеркало зеркала зеркале зеркалом зеркал зеркалами",
    "оскол": "осколок осколки осколков осколками", "обман": "обман обмана обманом обманы обмани обманул",
    "любов": "любовь любви любовью", "люблю": "люблю любишь любит любим любят любить любил любила",
    "сердц": "сердце сердца сердцем сердцу сердцах сердец",
    "паден": "падение падения падении падением", "пада": "падаю падаешь падает падаем падают падать падал падала",
    "перо": "перо пера пером перу перья перьев перьями",
    "звер": "зверь зверя звери зверей зверем зверями", "волк": "волк волка волки волков волком волками",
    "когт": "коготь когтя когти когтей когтями", "андроид": "андроид андроиды андроида",
    "робот": "робот робота роботы роботов", "стекл": "стекло стекла стеклом стекле",
    "кристалл": "кристалл кристаллы кристалла кристаллов",
    "звезд": "звезда звезды звезд звезде звездой звездами звездный звездная",
    "звёзд": "звезда звезды звезд звезде звездой звездами звездный звездная",
    "огонь": "огонь огня огнем огне огни огней", "плам": "пламя пламени пламенем",
    "горит": "горит горят гореть горящий горящая", "луна": "луна луны луне луной",
    "лунн": "лунный лунная лунное лунные лунного лунной", "ночь": "ночь ночи ночью ночей ночами",
    "ночн": "ночной ночная ночное ночные ночного ночную ночных",
    "солн": "солнце солнца солнцу солнцем солнечный солнечная солнечное",
    "рассвет": "рассвет рассвета рассвете рассветом", "лето": "лето лета летом",
    "океан": "океан океана океане океаном океаны", "море": "море моря морем морю морей морях",
    "волн": "волна волны волн волне волной волнами", "вода": "вода воды воде воду водой",
    "гора": "гора горе гору горой", "горы": "горы гор горам горами горах",
    "вершин": "вершина вершины вершине вершину вершин", "глаз": "глаз глаза глазом глазу глазами глазах",
    "взгляд": "взгляд взгляда взглядом взгляды", "виден": "видение видения видений",
    "время": "время времени времен временем", "час": "час часа часы часов часом часами",
    "песок": "песок песка песком пески", "ключ": "ключ ключа ключи ключей ключом ключами",
    "секрет": "секрет секрета секреты секретов", "двер": "дверь двери дверей дверью дверями",
    "полёт": "полет полета полеты полетов полете", "полет": "полет полета полеты полетов полете",
    "свобод": "свобода свободы свободе свободой свободный свободная свободные",
    "крыл": "крыло крыла крылу крылом крылья крыльев крыльями крылатый крылатая",
    "цветок": "цветок цветка цветком", "цветы": "цветы цветов цветами",
    "роза": "роза розы роз розой розами", "цветени": "цветение цветения цветении цветением",
    "корон": "корона короны корон короной коронованный", "король": "король короля короли королей",
    "королев": "королева королевы королев королевой", "молни": "молния молнии молний молнией",
    "гроза": "гроза грозы грозой гроз", "гром": "гром грома громом",
    "дерев": "дерево дерева деревом деревья деревьев деревьями", "лес": "лес леса лесу лесом лесов лесами",
    "листв": "листва листвы листве листвой", "лист": "лист листа листу листом листья листьев листьями",
    "осень": "осень осени осенью", "бабоч": "бабочка бабочки бабочек бабочкой бабочками",
    "мотыл": "мотылек мотыльки мотыльков мотыльком", "птиц": "птица птицы птиц птицей птицами",
    "ворон": "ворон ворона вороны воронов вороном", "дракон": "дракон дракона драконы драконов",
    "череп": "череп черепа черепом черепов", "смерть": "смерть смерти смертью",
    "маска": "маска маски масок маской", "театр": "театр театра театры театром",
    "меч": "меч меча мечи мечей мечом мечами", "клинок": "клинок клинка клинки клинков",
    "щит": "щит щита щитом щиты щитов", "броня": "броня брони броней",
    "якор": "якорь якоря якорем якорей", "компас": "компас компаса компасы компасом",
    "север": "север севера севере севером", "кораб": "корабль корабля корабли кораблей кораблем",
    "парус": "парус паруса парусов парусом", "планет": "планета планеты планет планетой",
    "сатурн": "сатурн сатурна сатурне", "комет": "комета кометы комет кометой",
    "метеор": "метеор метеоры метеора метеоров", "спирал": "спираль спирали спиралью",
    "водоворот": "водоворот водоворота водовороты", "лабиринт": "лабиринт лабиринта лабиринты лабиринтов",
    "мост": "мост моста мосты мостов мостом", "переправ": "переправа переправы переправой",
    "фонарь": "фонарь фонаря фонари фонарей фонарем", "маяк": "маяк маяка маяки маяков",
    "дожд": "дождь дождя дожди дождей дождем", "слеза": "слеза слезы слез слезой слезами",
    "капля": "капля капли капель каплей", "снежин": "снежинка снежинки снежинок снежинкой",
    "снег": "снег снега снегом снеги", "зима": "зима зимы зимой",
    "falling": "falling fall falls", "burn": "burn burns burning burned burnt",
    "fly": "fly flies flying", "free": "free freedom", "watch": "watch watches watching",
    "sail": "sail sails sailing", "leaf": "leaf leaves", "wolf": "wolf wolves",
    "butterfly": "butterfly butterflies", "eye": "eye eyes", "key": "key keys",
    "кружит": "кружит кружится кружиться кружусь кружишь кружим кружат кружишься кружимся кружатся кружило кружила кружили кружение",
    "крутит": "крутит крутится крутиться крутят крутятся кручу крутим крутишь крутил крутили",
    "орбит": "орбита орбиты орбит орбите орбитой",
    "вращение": "вращение вращения вращением вращается вращаться вращай вращаюсь вращаются",
    "пульс": "пульс пульса пульсом пульсирует пульсация",
    "ритм": "ритм ритма ритмом ритмы ритмов", "танец": "танец танца танцы танцев танцуй танцует танцевать танцую танцуют",
    "spin": "spin spins spinning spun", "rotate": "rotate rotates rotating rotated",
}


def _forms(cue):
    if cue in _FORMS:
        return tuple(_words(word) for word in _FORMS[cue].split())
    normal = _words(cue)
    # Only regular English plurals; Russian words require explicit forms.
    if not normal.isascii() or " " in normal:
        return (normal,)
    plural = normal + ("es" if normal.endswith(("s","x","z","ch","sh")) else "s")
    return (normal, plural)


_PATTERNS = tuple((name, tuple((cue, re.compile(r"(?<!\w)(?:" +
                    "|".join(re.escape(form) for form in _forms(cue)) + r")(?!\w)"))
                    for cue in dict.fromkeys((name,*cues)))) for name, cues in IMAGERY)


def _imagery_from_words(text, distance):
    text = _words(text)
    choices = []
    for name, patterns in _PATTERNS:
        hits = [(cue, list(pattern.finditer(text))) for cue, pattern in patterns]
        hits = [(cue, matches) for cue, matches in hits if matches]
        if not hits:
            continue
        cue, _ = max(hits, key=lambda hit: len(_words(hit[0]).split()))
        # A phrase is stronger than a single word. Bound repeated lyric evidence
        # and use musical fit to settle ambiguous images rather than family order.
        occurrences = {m.span() for _, matches in hits for m in matches}
        evidence = len(_words(cue).split()) + min(.4, .1 * (len(occurrences)-1))
        choices.append((-evidence, distance(name), name, cue))
    return min(choices)[2:] if choices else (None, "")


def symbol_plan(dna, title="", lyrics=""):
    design = design_from_music(dna)
    vector = (design.angularity,design.mass,design.openness,float(dna.valence),
              float(dna.rhythmic_density),float(dna.tension))
    weights = (1.2,1.,.9,.65,.8,.8)
    def distance(name):
        return sum(weight*(a-b)**2 for weight,a,b in zip(weights,vector,AUDIO_ARCHETYPES[name]))
    motif, cue = _imagery_from_words(title[:1000], distance)
    semantic_source = "title" if motif else ""
    if motif is None:
        motif, cue = _imagery_from_words(lyrics[:4000], distance)
        semantic_source = "lyrics" if motif else ""
    if motif is None:
        motif = min(ABSTRACT_MOTIFS, key=distance)
    mass, flow = design.mass, design.openness
    # The measured mixes occupy a narrow timbral range. Give differences in
    # that range an expressive contour response, while selection stays on the
    # original unmodified evidence above.
    edge = unit((design.angularity-.26)/.24)
    rhythm, tension = unit(dna.rhythmic_density), unit(dna.tension)
    # Actual measured envelopes, not a title hash or a random seed. The same
    # familiar object gets different rhythm, pressure and directional structure.
    envelope = tuple(unit(x) for x in (getattr(dna,"energy_curve",()) or (.5,)))
    activity = tuple(unit(x) for x in (getattr(dna,"activity_curve",()) or envelope))
    envelope = tuple(float(x) for x in np.interp(np.linspace(0,1,12),np.linspace(0,1,len(envelope)),envelope))
    activity = tuple(float(x) for x in np.interp(np.linspace(0,1,12),np.linspace(0,1,len(activity)),activity))
    construction = "outline" if mass < .28 and flow > .62 else "solid"
    return {
        "version": VERSION, "motif": motif,
        "source": "title/lyrics + audio" if cue else "audio",
        "semantic_source": semantic_source,
        "semantic_cue": cue, "angularity": edge, "audio_angularity": design.angularity, "mass": design.mass,
        "flow": flow, "rhythm": rhythm, "tension": tension,
        "dynamic": float(dna.dynamic_complexity),
        "construction": construction, "selection_policy": "meaning-first; abstract audio fallback",
        "energy_profile": envelope, "activity_profile": activity,
        "stroke": .022 + .030*mass + .014*rhythm,
        "aspect": .77 + .28*mass + .10*(1-flow),
        "gesture_angle": (tension-.5)*30 + (rhythm-.5)*16,
        "center": (.5, .48), "size": .37 + .070 * mass,
    }


def bezier(points, count=40):
    points = np.asarray(points, dtype=float)
    t = np.linspace(0, 1, count)[:, None]
    curve = (1-t)**3*points[0] + 3*(1-t)**2*t*points[1] + 3*(1-t)*t*t*points[2] + t**3*points[3]
    return [tuple(point) for point in curve]


def _mask(plan, size):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    edge, mass = plan["angularity"], plan["mass"]
    def xy(points):
        return [(round(x*size), round(y*size)) for x, y in points]
    def polygon(points, fill=255):
        d.polygon(xy(points), fill=fill)
    def path(segments, fill=255):
        samples=round(40-12*edge) if edge<=.68 else max(5,round(14*(1-edge)+3))
        polygon([p for segment in segments for p in bezier(segment,samples)], fill)
    def line(points, width=.01, fill=0):
        pressure=.60+1.1*mass if fill else .80+.45*edge
        d.line(xy(points), fill=fill, width=max(1, round(size*width*pressure)), joint="curve")
    def ellipse(bounds, fill=None, outline=None, width=1):
        if edge <= .68:
            d.ellipse(bounds,fill=fill,outline=outline,width=width)
            return
        left,top,right,bottom=bounds
        count=max(7,round(15-9*edge))
        points=[((left+right)/2+(right-left)/2*math.cos(i*math.tau/count),
                 (top+bottom)/2+(bottom-top)/2*math.sin(i*math.tau/count)) for i in range(count)]
        if fill is not None:
            d.polygon(points,fill=fill)
        if outline is not None:
            d.line(points+[points[0]],fill=outline,width=width,joint="curve")

    motif, mass = plan["motif"], plan["mass"]
    cuts = []
    if motif == "heart":
        if edge>.68:
            polygon([(.5,.28),(.28,.09),(.10,.25),(.08,.46),(.5,.88),(.92,.46),(.90,.25),(.72,.09)])
        else:
            path([((.5,.26),(.15,-.01),(.01,.40),(.5,.86)),
                  ((.5,.86),(.99,.40),(.85,-.01),(.5,.26))])
        # A seam follows musical tension; the outline remains a complete heart.
        if plan["construction"] != "outline":
            depth=.035+.055*plan['tension']
            cuts = [[(.5,.24),(.5-depth,.43),(.5+depth,.56),(.49,.77)]]
    elif motif == "feather":
        if edge>.68:
            polygon([(.23,.84),(.20,.55),(.39,.25),(.65,.09),(.82,.10),(.80,.44),(.60,.73)])
        else:
            path([((.23,.84),(.18,.38),(.49,.02),(.82,.10)),
                  ((.82,.10),(.88,.54),(.47,.78),(.23,.84))])
        cuts = [[(.24,.86),(.48,.47),(.76,.15)]]
        ribs = 4 + round(plan["rhythm"]*8)
        for i in range(1, ribs+1):
            t = i/(ribs+2)
            x, y = .25+.48*t, .80-.63*t
            reach=.055+.12*plan['energy_profile'][min(11,round(t*11))]
            cuts.extend([[(x,y),(x-reach,y-.11)], [(x+.015,y-.02),(x+reach,y+.018)]])
    elif motif == "claw":
        count=2+round(plan['rhythm']*3)
        for i in range(count):
            x = .08+i*.84/count
            width=.84/count
            path([((x,.86),(x+width*.55,.60),(x+width*.10,.23),(x+width*.65,.08)),
                  ((x+width*.65,.08),(x+width,.42),(x+width*.85,.68),(x,.86))])
    elif motif == "prism":
        vertices=([(.5,.05),(.82,.48),(.5,.93),(.18,.48)] if edge<.35 else
                  [(.5,.05),(.85,.36),(.73,.76),(.42,.93),(.14,.64),(.19,.23)] if edge<.68 else
                  [(.30,.08),(.70,.08),(.88,.26),(.88,.73),(.69,.91),(.29,.91),(.11,.72),(.11,.26)])
        polygon(vertices)
        center=(.48,.47)
        cuts=[[vertex,center] for vertex in vertices]
    elif motif == "mirror":
        polygon([(.24,.09),(.73,.12),(.90,.42),(.78,.86),(.25,.91),(.08,.56)])
        cuts = [[(.44,.1),(.48,.37),(.35,.52),(.59,.64),(.52,.9)],
                [(.48,.37),(.87,.43)],[(.35,.52),(.11,.6)],[(.59,.64),(.81,.76)]]
        # An inset keeps this a reflective frame instead of a solid badge.
        polygon([(.28,.19),(.68,.22),(.78,.44),(.69,.75),(.30,.79),(.20,.55)], 85)
    elif motif == "star":
        points = []
        for i in range(16):
            angle = -math.pi/2 + i*math.pi/8
            r = .44 if i % 4 == 0 else .28 if i % 2 == 0 else .11
            points.append((.5+math.cos(angle)*r,.5+math.sin(angle)*r))
        polygon(points)
        ellipse((size*.41,size*.41,size*.59,size*.59), fill=0)
    elif motif == "flame":
        path([((.48,.06),(.72,.37),(.91,.38),(.76,.70)),
              ((.76,.70),(.66,.95),(.18,.95),(.17,.64)),
              ((.17,.64),(.13,.47),(.48,.33),(.48,.06))])
        path([((.51,.37),(.56,.60),(.78,.68),(.53,.82)),
              ((.53,.82),(.23,.86),(.34,.61),(.51,.37))],0)
    elif motif == "moon":
        ellipse((size*.14,size*.08,size*.84,size*.88),fill=255)
        ellipse((size*.39,size*.01,size*.96,size*.73),fill=0)
        polygon([(.75,.59),(.79,.69),(.89,.73),(.79,.77),(.75,.87),(.71,.77),(.61,.73),(.71,.69)])
    elif motif == "sun":
        ellipse((size*.31,size*.31,size*.69,size*.69),fill=255)
        rays=8+round(plan["rhythm"]*6)
        for i in range(rays):
            a=i*math.tau/rays
            nx,ny=math.cos(a),math.sin(a)
            tx,ty=-ny,nx
            polygon([(.5+nx*.27+tx*.015,.5+ny*.27+ty*.015),
                     (.5+nx*.43,.5+ny*.43),
                     (.5+nx*.27-tx*.015,.5+ny*.27-ty*.015)])
    elif motif == "wave":
        path([((.08,.77),(.18,.62),(.29,.16),(.68,.22)),
              ((.68,.22),(.89,.26),(.91,.52),(.65,.56)),
              ((.65,.56),(.91,.39),(.59,.28),(.52,.47)),
              ((.52,.47),(.42,.70),(.68,.71),(.91,.74)),
              ((.91,.74),(.67,.88),(.29,.90),(.08,.77))])
        cuts=[[(.21,.74),(.37,.65),(.44,.49)]]
    elif motif == "mountain":
        polygon([(.05,.84),(.45,.13),(.67,.56),(.77,.36),(.96,.84)])
        polygon([(.35,.31),(.45,.13),(.56,.35),(.45,.28),(.41,.36)],0)
        cuts=[[(.45,.32),(.43,.83)],[(.77,.49),(.70,.82)]]
    elif motif == "eye":
        path([((.06,.5),(.31,.09),(.69,.09),(.94,.5)),
              ((.94,.5),(.69,.91),(.31,.91),(.06,.5))])
        path([((.17,.5),(.35,.25),(.65,.25),(.83,.5)),
              ((.83,.5),(.65,.75),(.35,.75),(.17,.5))],0)
        ellipse((size*.35,size*.35,size*.65,size*.65),fill=255)
        ellipse((size*.44,size*.44,size*.56,size*.56),fill=0)
    elif motif == "hourglass":
        polygon([(.20,.12),(.80,.12),(.80,.18),(.20,.18)])
        polygon([(.20,.82),(.80,.82),(.80,.88),(.20,.88)])
        path([((.26,.18),(.26,.39),(.45,.46),(.49,.50)),
              ((.49,.50),(.40,.57),(.26,.66),(.26,.82)),
              ((.26,.82),(.38,.82),(.62,.82),(.74,.82)),
              ((.74,.82),(.74,.65),(.60,.57),(.51,.50)),
              ((.51,.50),(.60,.43),(.74,.38),(.74,.18))])
        polygon([(.36,.23),(.64,.23),(.50,.43)],0)
        polygon([(.50,.62),(.37,.78),(.63,.78)],0)
    elif motif == "key":
        ellipse((size*.18,size*.09,size*.66,size*.57),fill=255)
        ellipse((size*.30,size*.21,size*.54,size*.45),fill=0)
        polygon([(.37,.52),(.48,.52),(.48,.87),(.69,.87),(.69,.75),(.59,.75),(.59,.67),(.48,.67),(.48,.91),(.37,.91)])
    elif motif == "wing":
        path([((.15,.82),(.22,.26),(.64,.12),(.93,.15)),
              ((.93,.15),(.73,.31),(.67,.38),(.51,.41)),
              ((.51,.41),(.71,.37),(.75,.42),(.77,.42)),
              ((.77,.42),(.58,.58),(.47,.60),(.39,.59)),
              ((.39,.59),(.52,.59),(.56,.63),(.59,.65)),
              ((.59,.65),(.47,.82),(.26,.80),(.15,.82))])
        cuts=[[(.22,.73),(.42,.44),(.71,.26)]]
    elif motif == "flower":
        petals=5+round(plan["rhythm"]*3)
        for i in range(petals):
            a=i*math.tau/petals
            xx,yy=.5+math.cos(a)*.20,.35+math.sin(a)*.20
            ellipse(((xx-.12)*size,(yy-.12)*size,(xx+.12)*size,(yy+.12)*size),fill=255)
        ellipse((size*.42,size*.27,size*.58,size*.43),fill=0)
        line([(.5,.60),(.5,.89)],.035,255)
        path([((.5,.77),(.40,.56),(.25,.66),(.26,.68)),
              ((.26,.68),(.25,.86),(.44,.88),(.5,.77))])
    elif motif == "crown":
        polygon([(.13,.25),(.33,.46),(.50,.13),(.67,.46),(.87,.25),(.78,.76),(.22,.76)])
        polygon([(.24,.80),(.76,.80),(.74,.87),(.26,.87)])
        polygon([(.5,.50),(.56,.60),(.5,.70),(.44,.60)],0)
        cuts=[[(.28,.49),(.32,.70)],[(.72,.49),(.68,.70)]]
    elif motif == "lightning":
        polygon([(.49,.07),(.80,.07),(.59,.41),(.79,.41),(.28,.93),(.42,.56),(.22,.56)])
    elif motif == "tree":
        polygon([(.44,.91),(.47,.43),(.54,.43),(.56,.91)])
        for cx,cy,r in ((.32,.34,.18),(.67,.35,.19),(.49,.19,.18),(.48,.45,.19)):
            ellipse(((cx-r)*size,(cy-r)*size,(cx+r)*size,(cy+r)*size),fill=255)
        cuts=[[(.5,.63),(.5,.29)],[(.5,.49),(.32,.34)],[(.5,.45),(.68,.29)]]
    elif motif == "leaf":
        path([((.50,.08),(.89,.31),(.85,.70),(.50,.83)),
              ((.50,.83),(.15,.70),(.11,.31),(.50,.08))])
        line([(.5,.78),(.5,.92)],.035,255)
        cuts=[[(.5,.19),(.5,.78)]]
        for i in range(3+round(plan['rhythm']*3)):
            yy=.35+i*.065
            cuts.extend([[ (.5,yy+.07),(.30,yy-.015)],[(.5,yy+.07),(.70,yy-.015)]])
    elif motif == "butterfly":
        for flip in (False,True):
            segments=[((.49,.44),(.30,.09),(.05,.12),(.12,.45)),
                      ((.12,.45),(.13,.62),(.28,.62),(.43,.53)),
                      ((.43,.53),(.17,.58),(.19,.91),(.40,.80)),
                      ((.40,.80),(.49,.70),(.46,.58),(.49,.44))]
            if flip:
                segments=[tuple((1-x,y) for x,y in s) for s in segments]
            path(segments)
        line([(.5,.34),(.5,.77)],.036,255)
        line([(.5,.38),(.43,.22)],.017,255)
        line([(.5,.38),(.57,.22)],.017,255)
        cuts=[[(.26,.30),(.39,.45)],[(.74,.30),(.61,.45)]]
    elif motif == "bird":
        path([((.13,.77),(.35,.55),(.28,.19),(.60,.09)),
              ((.60,.09),(.55,.40),(.59,.43),(.69,.41)),
              ((.69,.41),(.73,.27),(.89,.30),(.84,.43)),
              ((.84,.43),(.85,.60),(.67,.73),(.52,.67)),
              ((.52,.67),(.37,.70),(.25,.84),(.13,.77))])
        polygon([(.83,.38),(.95,.44),(.83,.47)])
        ellipse((size*.77,size*.36,size*.80,size*.39),fill=0)
        cuts=[[(.45,.55),(.44,.36),(.53,.21)]]
    elif motif == "dragon":
        path([((.17,.79),(.05,.53),(.47,.43),(.52,.24)),
              ((.52,.24),(.59,.14),(.76,.18),(.83,.28)),
              ((.83,.28),(.66,.26),(.78,.45),(.54,.57)),
              ((.54,.57),(.82,.88),(.28,.94),(.17,.79))])
        polygon([(.57,.24),(.61,.06),(.69,.21)])
        polygon([(.43,.55),(.19,.17),(.54,.34)])
        polygon([(.76,.22),(.91,.34),(.70,.38)])
        path([((.27,.77),(.28,.56),(.67,.68),(.63,.77)),
              ((.63,.77),(.56,.85),(.32,.85),(.27,.77))],0)
        ellipse((size*.68,size*.24,size*.72,size*.28),fill=0)
        cuts=[[(.25,.29),(.43,.50)]]
    elif motif == "skull":
        ellipse((size*.19,size*.10,size*.81,size*.74),fill=255)
        polygon([(.29,.59),(.71,.59),(.67,.88),(.33,.88)])
        ellipse((size*.27,size*.37,size*.45,size*.57),fill=0)
        ellipse((size*.55,size*.37,size*.73,size*.57),fill=0)
        polygon([(.5,.55),(.44,.67),(.56,.67)],0)
        cuts=[[(.42,.74),(.42,.88)],[(.50,.73),(.50,.88)],[(.58,.74),(.58,.88)]]
    elif motif == "mask":
        path([((.16,.18),(.35,.30),(.65,.30),(.84,.18)),
              ((.84,.18),(.91,.67),(.63,.91),(.50,.91)),
              ((.50,.91),(.37,.91),(.09,.67),(.16,.18))])
        path([((.24,.43),(.30,.32),(.42,.36),(.44,.47)),
              ((.44,.47),(.37,.51),(.28,.50),(.24,.43))],0)
        path([((.56,.47),(.58,.36),(.70,.32),(.76,.43)),
              ((.76,.43),(.72,.50),(.63,.51),(.56,.47))],0)
        cuts=[bezier(((.34,.67),(.42,.80),(.58,.80),(.66,.67))) ]
    elif motif == "sword":
        polygon([(.5,.06),(.60,.25),(.55,.64),(.45,.64),(.40,.25)])
        polygon([(.23,.62),(.77,.62),(.73,.70),(.27,.70)])
        polygon([(.45,.69),(.55,.69),(.55,.86),(.45,.86)])
        ellipse((size*.43,size*.85,size*.57,size*.93),fill=255)
        cuts=[[(.5,.20),(.5,.61)]]
    elif motif == "shield":
        path([((.18,.16),(.35,.25),(.65,.25),(.82,.16)),
              ((.82,.16),(.86,.65),(.65,.82),(.5,.94)),
              ((.5,.94),(.35,.82),(.14,.65),(.18,.16))])
        path([((.28,.30),(.40,.35),(.60,.35),(.72,.30)),
              ((.72,.30),(.74,.61),(.61,.73),(.5,.81)),
              ((.5,.81),(.39,.73),(.26,.61),(.28,.30))],0)
        polygon([(.5,.42),(.58,.55),(.5,.69),(.42,.55)])
    elif motif == "anchor":
        line([(.5,.24),(.5,.83)],.035+.07*mass,255)
        line([(.29,.38),(.71,.38)],.030+.07*mass,255)
        belly=.82+.14*plan['flow']
        points=bezier(((.17,.56),(.21,belly),(.79,belly),(.83,.56)),max(5,round(35*(1-edge))))
        line(points,.035+.07*mass,255)
        polygon([(.12,.50),(.30,.61),(.15,.67)])
        polygon([(.88,.50),(.70,.61),(.85,.67)])
        ellipse((size*.40,size*.07,size*.60,size*.27),fill=255)
        ellipse((size*.45,size*.12,size*.55,size*.22),fill=0)
    elif motif == "compass":
        ellipse((size*.14,size*.14,size*.86,size*.86),outline=255,width=round(size*.025))
        polygon([(.50,.07),(.59,.41),(.93,.50),(.59,.59),(.5,.93),(.41,.59),(.07,.5),(.41,.41)])
        polygon([(.5,.20),(.5,.50),(.80,.50),(.57,.43)],0)
        ellipse((size*.455,size*.455,size*.545,size*.545),fill=0)
    elif motif == "ship":
        polygon([(.12,.71),(.88,.71),(.75,.86),(.27,.86)])
        line([(.49,.10),(.49,.71)],.035,255)
        path([((.43,.14),(.37,.29),(.19,.49),(.17,.60)),
              ((.17,.60),(.29,.57),(.35,.57),(.43,.60))])
        path([((.55,.20),(.64,.31),(.82,.46),(.83,.61)),
              ((.83,.61),(.70,.56),(.62,.56),(.55,.61))])
        cuts=[[(.32,.78),(.69,.78)]]
    elif motif == "planet":
        ellipse((size*.29,size*.23,size*.71,size*.76),fill=255)
        ring=Image.new('L',mask.size)
        ImageDraw.Draw(ring).ellipse((size*.07,size*.37,size*.93,size*.64),outline=255,width=round(size*.028))
        ring=ring.rotate(18,resample=Image.Resampling.BICUBIC)
        mask=Image.fromarray(np.maximum(np.asarray(mask),np.asarray(ring)))
        d=ImageDraw.Draw(mask)
        cuts=[[(.35,.57),(.64,.46)]]
    elif motif == "comet":
        polygon([(.16,.15),(.55,.43),(.42,.64)])
        polygon([(.41,.06),(.70,.44),(.57,.51)])
        polygon([(.06,.42),(.51,.61),(.45,.72)])
        ellipse((size*.40,size*.40,size*.86,size*.86),fill=255)
        ellipse((size*.55,size*.53,size*.76,size*.74),fill=0)
    elif motif == "spiral":
        turns=1.3+plan['rhythm']*2.5+plan['dynamic']*.5
        theta=np.linspace(0,math.tau*turns,450)
        progress=np.linspace(0,1,len(theta))
        envelope=np.interp(progress,np.linspace(0,1,12),plan['energy_profile'])
        radius=.035+.39*progress**(.65+.7*plan['flow'])
        points=np.column_stack((.5+radius*np.cos(theta),.5+radius*np.sin(theta)))
        # A single joined ribbon avoids seams between variable-width strokes.
        # Pressure follows the measured energy envelope along the gesture.
        tangent=np.gradient(points,axis=0)
        normal=np.column_stack((-tangent[:,1],tangent[:,0]))
        normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-8)
        half_width=plan['stroke']*(.55+.8*envelope)*(.60+1.1*mass)/2
        half_width=np.minimum(half_width,radius*.7)
        outer=points+normal*half_width[:,None]
        inner=points-normal*half_width[:,None]
        polygon(np.concatenate((outer,inner[::-1])))
        for index in (0,-1):
            cx,cy=points[index]*size;r=half_width[index]*size
            d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=255)
    elif motif == "labyrinth":
        for inset in (.10,.22,.34):
            d.rectangle((size*inset,size*inset,size*(1-inset),size*(1-inset)),outline=255,width=round(size*.033))
        line([(.10,.37),(.22,.37)],.05,0)
        line([(.62,.22),(.62,.34)],.05,0)
        line([(.34,.57),(.46,.57)],.05,0)
        line([(.22,.74),(.34,.74)],.033,255)
        line([(.74,.10),(.74,.22)],.033,255)
        ellipse((size*.46,size*.46,size*.54,size*.54),fill=255)
    elif motif == "bridge":
        polygon([(.10,.63),(.90,.63),(.90,.72),(.10,.72)])
        polygon([(.20,.29),(.26,.29),(.26,.89),(.20,.89)])
        polygon([(.74,.29),(.80,.29),(.80,.89),(.74,.89)])
        line(bezier(((.10,.46),(.34,.63),(.66,.63),(.90,.46))),.035,255)
        for x in (.32,.43,.57,.68):
            line([(x,.56),(x,.64)],.018,255)
    elif motif == "lantern":
        d.arc((size*.38,size*.07,size*.62,size*.29),180,360,fill=255,width=round(size*.027))
        polygon([(.29,.29),(.39,.20),(.61,.20),(.71,.29)])
        polygon([(.28,.29),(.72,.29),(.68,.78),(.32,.78)])
        polygon([(.36,.37),(.64,.37),(.60,.70),(.40,.70)],0)
        polygon([(.5,.42),(.55,.55),(.5,.64),(.45,.55)])
        polygon([(.27,.81),(.73,.81),(.70,.88),(.30,.88)])
    elif motif == "raindrop":
        path([((.50,.08),(.55,.29),(.86,.53),(.79,.72)),
              ((.79,.72),(.72,.98),(.28,.98),(.21,.72)),
              ((.21,.72),(.14,.53),(.45,.29),(.50,.08))])
        cuts=[bezier(((.35,.51),(.28,.65),(.32,.77),(.43,.81))) ]
    elif motif == "snowflake":
        for i in range(6):
            a=i*math.tau/6
            nx,ny=math.cos(a),math.sin(a)
            line([(.5,.5),(.5+nx*.42,.5+ny*.42)],.025+.009*mass,255)
            for r in (.22,.32):
                x,y=.5+nx*r,.5+ny*r
                for direction in (-1,1):
                    b=a+direction*math.pi/3
                    line([(x,y),(x-math.cos(b)*.115,y-math.sin(b)*.115)],.018,255)
    elif motif == "orbit":
        count=2+round(plan['rhythm']*3)
        for i in range(count):
            orbit_layer = Image.new("L", mask.size)
            opening=.09+.17*plan['flow']
            ImageDraw.Draw(orbit_layer).ellipse((size*.10,size*(.5-opening),size*.90,size*(.5+opening)),
                                            outline=255, width=max(1,round(size*plan['stroke']*(.6+.8*plan['energy_profile'][i*2]))))
            orbit_layer = orbit_layer.rotate(i*180/count+12, resample=Image.Resampling.BICUBIC)
            mask = Image.fromarray(np.maximum(np.asarray(mask),np.asarray(orbit_layer)))
        d = ImageDraw.Draw(mask)
        ellipse((size*.45,size*.45,size*.55,size*.55),fill=255)
    else:
        petals = 4 + round(plan["rhythm"]*8)
        theta = np.linspace(0,math.tau,400)
        envelope=np.interp(theta/math.tau,np.linspace(0,1,12),plan['activity_profile'])
        radius = .29 + (.04+.075*(1-plan["flow"]))*np.cos(theta*petals) + .025*plan['dynamic']*(envelope-.5)
        polygon(zip(.5+radius*np.cos(theta),.5+radius*np.sin(theta)))
        ellipse((size*.32,size*.32,size*.68,size*.68),fill=0)
        ellipse((size*.46,size*.46,size*.54,size*.54),fill=255)
    for cut in cuts:
        line(cut, .012+.008*plan["angularity"])
    return _expressive_contour(mask,plan)


def _minimum_filter(mask, diameter):
    """Exact square erosion in linear passes for supersampled open contours."""
    if diameter<=7:
        return mask.filter(ImageFilter.MinFilter(diameter))
    radius=diameter//2
    pixels=np.asarray(mask)
    for axis in (0,1):
        rows=np.moveaxis(pixels,axis,-1)
        length=rows.shape[-1]
        rows=np.pad(rows,((0,0),(radius,radius)),mode='edge')
        extra=(-rows.shape[-1])%diameter
        if extra:
            rows=np.pad(rows,((0,0),(0,extra)),mode='edge')
        blocks=rows.reshape(rows.shape[0],-1,diameter)
        forward=np.minimum.accumulate(blocks,axis=-1).reshape(rows.shape)
        backward=np.minimum.accumulate(blocks[...,::-1],axis=-1)[...,::-1].reshape(rows.shape)
        start=np.arange(length)
        pixels=np.moveaxis(np.minimum(backward[:,start],forward[:,start+diameter-1]),-1,axis)
    return Image.fromarray(pixels)


def _expressive_contour(mask, plan):
    """Change construction and pressure while preserving the object's skeleton."""
    size=mask.width
    # Map the song's progression onto pressure along the central skeleton.
    # Smooth, bounded row scaling keeps recognizable proportions; nothing is
    # displaced at random, and equivalent audio profiles reproduce the shape.
    profile=np.asarray(plan['energy_profile'],dtype=float)
    profile=np.convolve(np.pad(profile,(2,2),mode='edge'),np.array([1,2,3,2,1])/9,mode='valid')
    pressure=np.interp(np.linspace(0,1,size),np.linspace(0,1,len(profile)),profile)
    pressure=1+(pressure-.5)*(.26+.20*plan['dynamic'])
    expanded_width=math.ceil(size*1.26)
    # Warp bounded row strips: large exports must not allocate many full-size
    # float grids simply to preserve the song's pressure along the silhouette.
    pixels=np.asarray(mask)
    warped=np.empty((size,expanded_width),dtype=np.uint8)
    x=np.arange(expanded_width,dtype=np.float32)[None,:]
    for start in range(0,size,64):
        stop=min(size,start+64)
        y=np.arange(start,stop)[:,None]
        source_x=(size-1)/2+(x-(expanded_width-1)/2)/pressure[start:stop,None]
        inside=(source_x>=0)&(source_x<=size-1)
        source_x=np.clip(source_x,0,size-1)
        left=source_x.astype(int);right=np.minimum(left+1,size-1)
        fraction=source_x-left
        values=(pixels[y,left]*(1-fraction)+pixels[y,right]*fraction)*inside
        warped[start:stop]=np.clip(values,0,255).astype(np.uint8)
    mask=Image.fromarray(warped)
    if plan['angularity']<.38:
        softened=mask.filter(ImageFilter.GaussianBlur(size*.0025*plan['flow']))
        mask=softened.point(lambda a:round(max(0,min(1,(a-112)/32))*255))
    if plan['construction']=='outline':
        diameter=max(3,round(size*plan['stroke']*2)|1)
        inner=_minimum_filter(mask,diameter)
        mask=Image.fromarray(np.maximum(0,np.asarray(mask,dtype=int)-np.asarray(inner,dtype=int)).astype(np.uint8))
    bounds=mask.getbbox()
    if not bounds:
        return mask
    body=mask.crop(bounds)
    width=max(1,round(body.width*plan['aspect']))
    height=max(1,round(body.height*(1.02-.18*plan['rhythm']+.07*plan['flow'])))
    body=body.resize((width,height),Image.Resampling.LANCZOS)
    body=body.rotate(plan['gesture_angle'],resample=Image.Resampling.BICUBIC,expand=True)
    # Expanded rotation must never clip tips, wings, rays or thin endings.
    fit=min(1.,size*.94/max(body.size))
    if fit<1:
        body=body.resize((max(1,round(body.width*fit)),max(1,round(body.height*fit))),Image.Resampling.LANCZOS)
    result=Image.new('L',(size,size))
    result.paste(body,((size-body.width)//2,(size-body.height)//2))
    return result


def _symbol_region(image, plan, shape, protected_boxes, scene=None):
    """Prefer the centre; move into quieter upper space when the art needs it."""
    original_gray = image.convert("L")
    gray = original_gray.resize((128,128), Image.Resampling.LANCZOS)
    # Measure edges before reducing: fine texture otherwise averages into a
    # deceptively smooth area, exactly where a small symbol loses its outline.
    edges = original_gray.filter(ImageFilter.FIND_EDGES).resize((128,128),Image.Resampling.BOX)
    sampled=np.asarray(shape.resize((64,64),Image.Resampling.LANCZOS))
    occupied = sampled > 128
    if not occupied.any():
        occupied = sampled > 0
    entries = []
    for scale in (1., .86):
        span = max(30,round(min(image.size)*plan["size"]*scale))
        candidates=((.5,.48),(.5,.27),(.32,.30),(.68,.30),(.4,.43),(.6,.43))
        if scene:
            hx,hy=scene['hero_center']
            candidates=((hx,hy),(hx-.11,hy),(hx+.10,hy),(hx,hy-.045),
                        (hx-.22,hy),(hx+.22,hy),(hx,hy-.17),(hx,hy+.08))
        for index, (x,y) in enumerate(candidates):
            cx,cy=round(image.width*x),round(image.height*y)
            box=(cx-span//2,cy-span//2,cx-span//2+span,cy-span//2+span)
            if box[0]<0 or box[1]<0 or box[2]>image.width or box[3]>image.height:
                continue
            sample_box=(round(box[0]*128/image.width),round(box[1]*128/image.height),
                        round(box[2]*128/image.width),round(box[3]*128/image.height))
            texture=float(np.asarray(gray.crop(sample_box)).std()/100 +
                          np.asarray(edges.crop(sample_box)).mean()/70)
            overlap=max((intersection_fraction(box,b) for b in protected_boxes),default=0)
            if scene and scene['title_zone']:
                reserved=tuple(v*min(image.size) for v in scene['title_zone'])
                # Transparent margins in the rotated symbol are not artwork.
                # Judge actual ink so a slight lift is not sent farther down.
                local=shape.resize((span,span),Image.Resampling.LANCZOS).getbbox()
                ink=tuple(local[i]+box[i%2] for i in range(4))
                overlap=max(overlap,intersection_fraction(ink,reserved))
            pixels=np.asarray(image.crop(box).convert("RGB").resize((64,64)),dtype=float)
            levels=luminance(pixels)[occupied]
            options=[]
            for light,neutral in ((True,(246,238,216)),(False,(20,27,33))):
                # A restrained tint keeps the image palette while retaining a
                # readable silhouette, especially in player thumbnails.
                accent=np.median(pixels.reshape(-1,3),axis=0)
                base=accent*.12 + np.array(neutral)*.88
                final=luminance(base*.95+pixels[occupied]*.05)
                contrast=float(np.percentile((np.maximum(final,levels)+.05)/(np.minimum(final,levels)+.05),5))
                options.append((contrast,light,base))
            contrast,light,base=max(options,key=lambda item:item[0])
            score=texture + overlap*100 + (0 if index==0 else .32) + (1-scale)*1.1 - min(contrast,7)*.035
            entries.append((score,box,(x,y),span,light,base,texture,overlap))
    return min(entries,key=lambda item:item[0])


def compose_song_symbol(image, dna, title="", lyrics="", *, protected_boxes=(), show_title=True):
    """Return integrated artwork plus bounds that typography must protect."""
    plan = symbol_plan(dna, title, lyrics)
    from .composition import spatial_plan, supporting_artwork
    scene=spatial_plan(plan,title,show_title)
    plan['size']=scene['hero_size']
    expected_span=round(min(image.size)*plan['size'])
    # At least 2x the actual exported symbol, up to 4x for player thumbnails.
    # Never enlarge a low-resolution contour for a large PNG.
    work = max(256, round(max(expected_span*2, min(expected_span*4,1536))))
    shape = _mask(plan, work)
    _,box,center,span,light,base,texture,overlap = _symbol_region(image,plan,shape,protected_boxes,scene)
    plan.update(center=center,size=span/min(image.size),background_complexity=round(texture,4),
                protected_overlap=round(overlap,4),placement='composed')
    shape=shape.resize((span,span),Image.Resampling.LANCZOS)
    local_bounds=shape.getbbox()
    plan['bounds']=tuple(local_bounds[i]+box[i%2] for i in range(4))
    image,scene=supporting_artwork(image,plan,scene,protected_boxes)
    plan['composition']=scene
    y,x = np.mgrid[0:span,0:span].astype(np.float32)
    highlight = .88 + .16*(1-y/span) + .08*np.cos((x+y*.6)/span*math.pi)
    material = np.clip(base[None,None,:]*highlight[...,None],0,255).astype(np.uint8)
    # Shallow relief, with light direction shared across the whole sculpture.
    rim_width=max(3,round(span*.004)|1)
    eroded = shape.filter(ImageFilter.MinFilter(rim_width))
    rim = np.clip(np.asarray(shape,dtype=int)-np.asarray(eroded,dtype=int),0,255)/255
    material = np.clip(material.astype(float)+rim[...,None]*(16 if light else -9),0,255).astype(np.uint8)
    symbol = Image.fromarray(material).convert("RGBA")
    symbol.putalpha(shape.point(lambda a: round(a*.95)))
    canvas = image.convert("RGBA")
    shadow = Image.new("RGBA",canvas.size)
    local_shadow = Image.new("RGBA",(span,span),(4,8,12,0))
    local_shadow.putalpha(symbol.getchannel("A").point(lambda a:round(a*.27)).filter(ImageFilter.GaussianBlur(max(1,span*.015))))
    shadow.alpha_composite(local_shadow,(box[0]+round(span*.008),box[1]+round(span*.013)))
    canvas = Image.alpha_composite(canvas,shadow)
    alpha = np.asarray(symbol.getchannel("A"))
    original = canvas.crop(box)
    # Only when the art's bands cross the silhouette, separate their tone in a
    # tightly feathered footprint. Preserve colour and all space outside it.
    footprint = symbol.getchannel("A").filter(ImageFilter.MaxFilter(5))
    footprint = footprint.filter(ImageFilter.GaussianBlur(max(1,span*.012)))
    initial_contrast = None
    for opacity in (0.,.15,.30,.45,.60,.75,.90):
        adjusted = original.copy()
        if opacity:
            veil = Image.new("RGBA",original.size,(0,0,0) if light else (255,255,255))
            veil.putalpha(footprint.point(lambda a:round(a*opacity)))
            adjusted = Image.alpha_composite(adjusted,veil)
        composed = Image.alpha_composite(adjusted,symbol)
        foreground=luminance(np.asarray(composed.convert("RGB")))[alpha>220]
        background=luminance(np.asarray(adjusted.convert("RGB")))[alpha>220]
        ratios=(np.maximum(foreground,background)+.05)/(np.minimum(foreground,background)+.05)
        contrast=float(np.percentile(ratios,5)) if ratios.size else 1.
        if initial_contrast is None:
            initial_contrast=contrast
        if contrast>=3:
            break
    canvas.paste(composed,(box[0],box[1]))
    plan.update(contrast_ratio=round(contrast,3),initial_contrast_ratio=round(initial_contrast,3),
                backing_opacity=opacity,edge_sampling='adaptive-2x-4x-lanczos',contour_resolution=work)
    bounds = symbol.getchannel("A").getbbox()
    plan["bounds"] = tuple(bounds[i]+box[i%2] for i in range(4))
    plan["material_color"] = tuple(int(v) for v in base)
    return canvas.convert("RGB"), plan
