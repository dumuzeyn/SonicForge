"""Compare a fixed symbol under real audio profiles and audit SPIN's PNG export."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont
import music2picture
import music_metadata
from music2picture_v2 import DEFAULT_PIPELINE
from music2picture_v2.variants import render_variant
from cover_engine.song_symbol import compose_song_symbol, symbol_plan, _mask
from cover_engine.music_lettering import intersection_fraction


def analyse(path):
    tags=music_metadata.read_all_metadata(path)
    bundle=DEFAULT_PIPELINE.analyse(path,metadata={k:v for k,v in tags.items() if 'lyrics' not in str(k).lower()},variation=7)
    return tags,bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--music-root',type=Path,required=True)
    parser.add_argument('--spin',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'validation/music_symbol/expressive')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('cover_engine._baseline_symbols_v4',args.baseline)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    files=sorted(args.music_root.rglob('*.mp3'))
    names=('Fallen Down','Another Love','КРУЖИТ')
    profiles=[]
    for name in names:
        path=args.spin if name=='КРУЖИТ' else min((p for p in files if p.stem==name),key=lambda p:(len(p.parts),str(p)))
        _,bundle=analyse(path)
        profiles.append((name,path,bundle))

    # Deliberately hold the semantic family and artwork fixed here, so that
    # changes in music alone can be seen. These are not the songs' chosen covers.
    font_path=str(ROOT/'assets/fonts/NotoSans-Variable.ttf')
    font=ImageFont.truetype(font_path,18);heading=ImageFont.truetype(font_path,23)
    rows=(('Heart','Сердце'),('Feather','Перо'),('Prism','Кристалл'),('Anchor','Якорь'))
    sheet=Image.new('RGB',(1020,1580),'#111827');draw=ImageDraw.Draw(sheet)
    draw.text((12,10),'Один образ — разные реальные аудиопрофили',font=heading,fill='#e2e8f0')
    draw.text((12,44),'Образ задан одинаковый; форма меняется только от звучания.',font=font,fill='#aab6c4')
    for col,(name,_,_) in enumerate(profiles):
        draw.text((col*340+12,80),name,font=font,fill='#e2e8f0')
    records=[]
    for row,(cue,label) in enumerate(rows):
        masks=[]
        for col,(name,path,bundle) in enumerate(profiles):
            base=Image.new('RGB',(600,600),'#28495a')
            image,plan=compose_song_symbol(base,bundle.visual_dna,cue)
            assert plan['motif']==cue.casefold(),(cue,plan['motif'])
            assert plan['contrast_ratio']>=3
            x=col*340+10;y=112+row*365
            sheet.paste(image.resize((320,320),Image.Resampling.LANCZOS),(x,y))
            draw.text((x,y+323),label+' · '+plan['construction'],font=font,fill='#e2e8f0')
            neutral=symbol_plan(bundle.visual_dna,cue)
            neutral.update(aspect=1,gesture_angle=0)
            masks.append(np.asarray(_mask(neutral,384))>128)
            records.append(dict(forced_family=plan['motif'],source=str(path),plan=plan))
        difference=float(np.count_nonzero(masks[0]^masks[-1])/max(1,np.count_nonzero(masks[0]|masks[-1])))
        assert difference>.3,(cue,difference)
        print(cue,'structural difference',round(difference,3),flush=True)
    sheet.save(args.output/'same_symbols_real_audio.png')

    tags,bundle=analyse(args.spin)
    title=tags.get('title') or args.spin.stem;artist=tags.get('artist','')
    assert symbol_plan(bundle.visual_dna,title)['motif']=='spiral'
    covers=[]
    for size in (1000,192):
        bare=render_variant(args.spin,bundle.visual_dna,bundle.visual_plan,size=size,seed=7,preview=True)
        old_art,old_symbol=baseline.compose_song_symbol(bare,bundle.visual_dna,title)
        before=music2picture._add_cover_text(old_art,title,artist,text_mode='title_artist',language=bundle.language,
                                            visual_dna=bundle.visual_dna,symbol_layout=old_symbol)
        target=args.output/f'spin_after_{size}.png'
        music2picture.make_cover(args.spin,target,size=size,seed=7,preview=True,text_mode='title_artist')
        after=Image.open(target).convert('RGB')
        art,symbol=compose_song_symbol(bare,bundle.visual_dna,title)
        layout={}
        expected=music2picture._add_cover_text(art,title,artist,text_mode='title_artist',language=bundle.language,
                                             visual_dna=bundle.visual_dna,layout_out=layout,symbol_layout=symbol)
        assert ImageChops.difference(expected,after).getbbox() is None
        assert intersection_fraction(layout['ink_bounds'],symbol['bounds'])==0
        assert layout['contrast_ratio']>=4.5
        assert symbol['contrast_ratio']>=3
        before.save(args.output/f'spin_before_{size}.png')
        covers.append(dict(size=size,before_motif=old_symbol['motif'],after=symbol,typography=layout,export_verified=True))
        if size==1000:
            comparison=Image.new('RGB',(1020,555),'#111827');d=ImageDraw.Draw(comparison)
            d.text((12,8),'ДО: якорь',font=heading,fill='#e2e8f0')
            d.text((522,8),'ПОСЛЕ: вращение',font=heading,fill='#e2e8f0')
            comparison.paste(before.resize((500,500),Image.Resampling.LANCZOS),(5,45))
            comparison.paste(after.resize((500,500),Image.Resampling.LANCZOS),(515,45))
            comparison.save(args.output/'spin_before_after.png')
        print('КРУЖИТ',size,symbol['motif'],layout['contrast_ratio'],flush=True)
    (args.output/'expression_audit.json').write_text(json.dumps(dict(fixed_family_examples=records,spin=covers),ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
