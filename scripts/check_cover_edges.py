"""Verify exported contours and title safety under a circular player crop."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image,ImageChops,ImageDraw,ImageFont
import numpy as np
import music2picture,music_metadata
from music2picture_v2 import DEFAULT_PIPELINE
from music2picture_v2.variants import render_variant
from cover_engine.music_lettering import design_from_music,line_mask,intersection_fraction
from cover_engine.song_symbol import _mask,symbol_plan
from cover_engine.typography import TypographyEngine


def circular(image):
    size=image.width
    mask=Image.new('L',(size*3,size*3))
    ImageDraw.Draw(mask).ellipse((0,0,size*3-1,size*3-1),fill=255)
    mask=mask.resize(image.size,Image.Resampling.LANCZOS)
    return Image.composite(image,Image.new('RGB',image.size,'#111827'),mask)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--music-root',type=Path,required=True)
    parser.add_argument('--spin',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'validation/cover_antialias')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    files=sorted(args.music_root.rglob('*.mp3'));results=[]
    names=('КРУЖИТ','Fallen Down','Another Love','Animal I Have Become','Android Dubstep','Я тебе не верю')
    gallery=Image.new('RGB',(1200,840),'#111827');draw=ImageDraw.Draw(gallery)
    font=ImageFont.truetype(str(ROOT/'assets/fonts/NotoSans-Variable.ttf'),20)
    for index,name in enumerate(names):
        path=args.spin if index==0 else min((p for p in files if p.stem==name),key=lambda p:(len(p.parts),str(p)))
        tags=music_metadata.read_all_metadata(path);title=tags.get('title') or path.stem
        seed=0 if index==0 else 7;style='current_legacy_colors' if index==0 else 'current'
        bundle=DEFAULT_PIPELINE.analyse(path,metadata={k:v for k,v in tags.items() if 'lyrics' not in k.lower()},variation=seed)
        for size in ((192,384,1000,3000) if index==0 else (192,384,1000)):
            start=time.perf_counter()
            bare=render_variant(path,bundle.visual_dna,bundle.visual_plan,style=style,size=size,seed=seed,preview=True)
            art,symbol=music2picture._add_cover_symbol(bare,bundle.visual_dna,title)
            layout={}
            expected=music2picture._add_cover_text(art,title,tags.get('artist',''),text_mode='title',language=bundle.language,
                                                 visual_dna=bundle.visual_dna,layout_out=layout,symbol_layout=symbol)
            output=args.output/f'{index+1:02d}_after_{size}.png'
            music2picture.make_cover(path,output,size=size,seed=seed,style=style,preview=True,text_mode='title')
            after=Image.open(output).convert('RGB')
            assert ImageChops.difference(expected,after).getbbox() is None
            assert intersection_fraction(layout['ink_bounds'],symbol['bounds'])==0
            assert layout['contrast_ratio']>=4.5 and symbol['contrast_ratio']>=3
            x0,y0,x1,y1=layout['ink_bounds']
            radius=max(math.hypot(x-size/2,y-size/2) for x,y in ((x0,y0),(x0,y1),(x1,y0),(x1,y1)))
            assert radius<=size*.46+2
            results.append(dict(title=title,size=size,source=str(path),seconds=round(time.perf_counter()-start,2),
                                title_radius=radius/size,symbol=symbol,typography=layout,export_verified=True))
            if size==384:
                x=(index%3)*400;y=(index//3)*420
                draw.text((x+10,y+5),title,font=font,fill='#e2e8f0')
                gallery.paste(circular(after),(x+8,y+33))
                if index==0:
                    comparison=Image.new('RGB',(816,445),'#111827');d=ImageDraw.Draw(comparison)
                    d.text((12,10),'ДО',font=font,fill='#e2e8f0');d.text((420,10),'ПОСЛЕ',font=font,fill='#e2e8f0')
                    comparison.paste(circular(Image.open(args.output/'before_384.png').convert('RGB')),(12,49))
                    comparison.paste(circular(after),(420,49));comparison.save(args.output/'round_comparison.png')
                    # Glyph masks at the same nominal size isolate edge quality
                    # from the new placement, palette and circular safe area.
                    spec=importlib.util.spec_from_file_location('cover_engine._old_lettering',args.output/'baseline_music_lettering_v2.py')
                    old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
                    design=design_from_music(bundle.visual_dna)
                    old_ink=old.line_mask(TypographyEngine(),title,48,old.LetteringDesign(**design.to_dict()))[0]
                    new_ink=line_mask(TypographyEngine(),title,48,design)[0]
                    edges=Image.new('RGB',(1000,500),'#172333');e=ImageDraw.Draw(edges)
                    e.text((12,8),'ДО · края ×4',font=font,fill='white');e.text((512,8),'ПОСЛЕ · края ×4',font=font,fill='white')
                    for col,mask in enumerate((old_ink,new_ink)):
                        tile=Image.new('RGB',mask.size,'#172333');tile.paste('#f3e8d0',(0,0,*mask.size),mask)
                        tile=tile.resize((tile.width*4,tile.height*4),Image.Resampling.NEAREST)
                        edges.paste(tile.crop((0,0,480,180)),(12+col*500,45))
                    spec=importlib.util.spec_from_file_location('cover_engine._old_symbols',args.output/'baseline_song_symbol_v6.py')
                    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
                    plan=symbol_plan(bundle.visual_dna,title);span=1000
                    masks=(old._mask(plan,768).resize((span,span),Image.Resampling.LANCZOS),
                           _mask(plan,span*2).resize((span,span),Image.Resampling.LANCZOS))
                    for col,mask in enumerate(masks):
                        tile=Image.new('RGB',mask.size,'#172333');tile.paste('#f3e8d0',(0,0,*mask.size),mask)
                        middle=span//2
                        occupied=np.flatnonzero(np.asarray(mask)[middle]>128)
                        edge=int(occupied[0])
                        tile=tile.crop((edge-16,middle-30,edge+104,middle+30))
                        edges.paste(tile.resize((480,240),Image.Resampling.NEAREST),(12+col*500,245))
                    edges.save(args.output/'edges_comparison.png')
            print(title,size,round(radius/size,4),layout['contrast_ratio'],flush=True)
    gallery.save(args.output/'round_gallery.png')
    (args.output/'measurements.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
