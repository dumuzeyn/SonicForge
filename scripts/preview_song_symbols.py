"""Render a reproducible gallery of every procedural symbol family."""
import argparse
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from PIL import Image,ImageChops,ImageDraw,ImageFont
from cover_engine.song_symbol import AUDIO_ARCHETYPES,IMAGERY,compose_song_symbol
from music2picture_v2.audio_analysis import analyze_audio_array
from music2picture_v2.semantics import build_visual_dna


LABELS=("Зеркало","Сердце","Перо","Когти","Кристалл","Звезда","Пламя","Луна","Солнце",
        "Волна","Горы","Глаз","Песочные часы","Ключ","Крыло","Цветок","Корона","Молния",
        "Орбиты","Розетка","Дерево","Лист","Бабочка","Птица","Дракон","Череп","Маска",
        "Меч","Щит","Якорь","Компас","Корабль","Планета","Комета","Спираль","Лабиринт",
        "Мост","Фонарь","Капля","Снежинка")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'validation/music_symbol/40_symbols.png')
    parser.add_argument('--new-only',action='store_true')
    args=parser.parse_args()
    base=build_visual_dna(analyze_audio_array(np.zeros(22050,dtype=np.float32)))
    entries=list(zip(AUDIO_ARCHETYPES.items(),LABELS))
    if args.new_only:
        entries=entries[20:]
    font=ImageFont.truetype(str(ROOT/'assets/fonts/NotoSans-Variable.ttf'),18)
    rows=(len(entries)+4)//5
    sheet=Image.new('RGB',(1120,rows*245),'#111827');draw=ImageDraw.Draw(sheet)
    images=[]
    for i,((name,vector),label) in enumerate(entries):
        a,m,o,v,r,t=vector
        dna=replace(base,valence=v,rhythmic_density=r,tension=t)
        design=SimpleNamespace(angularity=a,mass=m,openness=o)
        art=Image.new('RGB',(600,600),'#254557')
        with patch('cover_engine.song_symbol.design_from_music',return_value=design):
            title=next(cues[0] for motif,cues in IMAGERY if motif==name)
            image,plan=compose_song_symbol(art,dna,title)
        assert plan['motif']==name
        assert ImageChops.difference(image,art).getbbox() is not None
        images.append(image.tobytes())
        x=(i%5)*224;y=(i//5)*245
        sheet.paste(image.resize((220,220),Image.Resampling.LANCZOS),(x,y))
        draw.text((x+8,y+221),label,font=font,fill='#e2e8f0')
    assert len(set(images))==len(images)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sheet.save(args.output)
    print(f'{len(entries)} distinct symbols rendered: {args.output}')


if __name__=='__main__':
    main()
