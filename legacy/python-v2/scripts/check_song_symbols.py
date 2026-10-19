"""Render the real-song focal-symbol audit through the public PNG exporter."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image,ImageChops,ImageDraw,ImageFont
import music2picture
import music_metadata
from music2picture_v2 import DEFAULT_PIPELINE
from music2picture_v2.variants import render_variant
from cover_engine.music_lettering import intersection_fraction


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--music-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'validation/music_symbol')
    parser.add_argument('--size',type=int,default=1000)
    parser.add_argument('--baseline-covers',type=Path,help='Previous exported 01_after.png…05_after.png for comparison')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    names=('Fallen Down','Another Love','Animal I Have Become','Android Dubstep','Я тебе не верю')
    files=sorted(args.music_root.rglob('*.mp3'))
    sheet=Image.new('RGB',(1590,810),'#111827');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype(str(ROOT/'assets/fonts/NotoSans-Variable.ttf'),19)
    draw.text((9,9),'ДО — прежняя система символов' if args.baseline_covers else 'ДО — свободный центр',font=font,fill='#e2e8f0')
    draw.text((9,409),'ПОСЛЕ — подбор и композиция',font=font,fill='#e2e8f0')
    results=[]
    for index,name in enumerate(names,1):
        path=min((p for p in files if p.stem==name),key=lambda p:(len(p.parts),str(p)))
        tags=music_metadata.read_all_metadata(path)
        bundle=DEFAULT_PIPELINE.analyse(path,metadata={k:v for k,v in tags.items() if 'lyrics' not in str(k).lower()},variation=7)
        title=tags.get('title') or path.stem;artist=tags.get('artist','')
        bare=render_variant(path,bundle.visual_dna,bundle.visual_plan,size=args.size,seed=7,preview=True)
        before=music2picture._add_cover_text(bare,title,artist,text_mode='title_artist',language=bundle.language,visual_dna=bundle.visual_dna)
        if args.baseline_covers:
            before=Image.open(args.baseline_covers/f'{index:02d}_after.png').convert('RGB')
        before.save(args.output/f'{index:02d}_before.png')
        target=args.output/f'{index:02d}_after.png'
        music2picture.make_cover(path,target,size=args.size,seed=7,preview=True,text_mode='title_artist')
        after=Image.open(target).convert('RGB')
        artwork,symbol=music2picture._add_cover_symbol(bare,bundle.visual_dna,title)
        layout={}
        expected=music2picture._add_cover_text(artwork,title,artist,text_mode='title_artist',language=bundle.language,
                                            visual_dna=bundle.visual_dna,layout_out=layout,symbol_layout=symbol)
        assert ImageChops.difference(expected,after).getbbox() is None
        assert intersection_fraction(layout['ink_bounds'],symbol['bounds'])==0
        assert layout['contrast_ratio']>=4.5
        assert symbol['contrast_ratio']>=3
        results.append(dict(title=title,source=str(path),symbol=symbol,typography=layout,export_verified=True))
        for row,image in enumerate((before,after)):
            x=(index-1)*318+9;y=row*400+45
            sheet.paste(image.resize((300,300),Image.Resampling.LANCZOS),(x,y))
            draw.text((x,y+310),title,font=font,fill='#e2e8f0')
        print(name,symbol['motif'],layout['contrast_ratio'],flush=True)
    sheet.save(args.output/'comparison.png')
    (args.output/'measurements.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
