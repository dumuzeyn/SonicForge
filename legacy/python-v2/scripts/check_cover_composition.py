"""Audit shared cover composition on six real recordings and two PNG sizes."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image,ImageChops,ImageDraw,ImageFont
import music2picture,music_metadata
from music2picture_v2 import DEFAULT_PIPELINE
from music2picture_v2.variants import render_variant
from cover_engine.music_lettering import intersection_fraction


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--music-root',type=Path,required=True)
    parser.add_argument('--spin',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'validation/music_symbol/composed')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('cover_engine._symbols_v5',args.baseline)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    names=('КРУЖИТ','Fallen Down','Another Love','Animal I Have Become','Android Dubstep','Я тебе не верю')
    files=sorted(args.music_root.rglob('*.mp3'));results=[]
    sheet=Image.new('RGB',(1530,720),'#111827');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype(str(ROOT/'assets/fonts/NotoSans-Variable.ttf'),19)
    for index,name in enumerate(names):
        path=args.spin if index==0 else min((p for p in files if p.stem==name),key=lambda p:(len(p.parts),str(p)))
        tags=music_metadata.read_all_metadata(path);seed=0 if index==0 else 7
        title=tags.get('title') or path.stem;artist=tags.get('artist','')
        bundle=DEFAULT_PIPELINE.analyse(path,metadata={k:v for k,v in tags.items() if 'lyrics' not in str(k).lower()},variation=seed)
        for size in (1000,192):
            bare=render_variant(path,bundle.visual_dna,bundle.visual_plan,size=size,seed=seed,preview=True)
            artwork,symbol=music2picture._add_cover_symbol(bare,bundle.visual_dna,title)
            layout={}
            expected=music2picture._add_cover_text(artwork,title,artist,text_mode='title_artist',language=bundle.language,
                                                 visual_dna=bundle.visual_dna,layout_out=layout,symbol_layout=symbol)
            output=args.output/f'{index+1:02d}_after_{size}.png'
            music2picture.make_cover(path,output,size=size,seed=seed,preview=True,text_mode='title_artist')
            after=Image.open(output).convert('RGB')
            assert ImageChops.difference(expected,after).getbbox() is None
            assert intersection_fraction(layout['ink_bounds'],symbol['bounds'])==0
            assert layout['contrast_ratio']>=4.5
            assert symbol['contrast_ratio']>=3
            zone=symbol['composition']['title_zone_pixels'];ink=layout['ink_bounds']
            assert ink[0]>=zone[0] and ink[1]>=zone[1] and ink[2]<=zone[2] and ink[3]<=zone[3]
            results.append(dict(title=title,source=str(path),size=size,symbol=symbol,typography=layout,export_verified=True))
            if size==1000:
                old_art,old_symbol=old.compose_song_symbol(bare,bundle.visual_dna,title)
                before=music2picture._add_cover_text(old_art,title,artist,text_mode='title_artist',language=bundle.language,
                                                    visual_dna=bundle.visual_dna,symbol_layout=old_symbol)
                before.save(args.output/f'{index+1:02d}_before.png')
                x=(index%3)*510;y=(index//3)*360
                draw.text((x+8,y+5),title,font=font,fill='#e2e8f0')
                draw.text((x+8,y+32),'ДО',font=font,fill='#e2e8f0');draw.text((x+263,y+32),'ПОСЛЕ',font=font,fill='#e2e8f0')
                sheet.paste(before.resize((250,250),Image.Resampling.LANCZOS),(x+3,y+63))
                sheet.paste(after.resize((250,250),Image.Resampling.LANCZOS),(x+258,y+63))
                if index==0:
                    comparison=Image.new('RGB',(1020,555),'#111827');d=ImageDraw.Draw(comparison)
                    d.text((10,8),'ДО',font=font,fill='#e2e8f0');d.text((525,8),'ПОСЛЕ',font=font,fill='#e2e8f0')
                    comparison.paste(before.resize((500,500),Image.Resampling.LANCZOS),(5,45))
                    comparison.paste(after.resize((500,500),Image.Resampling.LANCZOS),(515,45))
                    comparison.save(args.output/'spin_comparison.png')
            print(title,size,symbol['composition']['language'],layout['contrast_ratio'],flush=True)
    sheet.save(args.output/'six_comparisons.png')
    (args.output/'measurements.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
