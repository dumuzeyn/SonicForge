"""Create actual titled covers from synthetic tracks for visual review."""
from dataclasses import replace
from pathlib import Path
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from music2picture_v2 import DEFAULT_PIPELINE
from music2picture_v2.variants import render_variant
from music2picture import _add_cover_symbol, _add_cover_text


def main():
    output=ROOT/'validation/cover-adaptation'
    output.mkdir(parents=True,exist_ok=True)
    rate=22050;t=np.arange(rate*24)/rate
    titles=('Ночной свет','Тихое море','Новый день','Crystal rain','Lotus','Swan')
    palettes=(('#213D65','#8FBDC9','#F0BF92'),('#24484C','#77B0A8','#CDDCAF'),
              ('#7A415D','#CA8193','#EDBD9C'),None,None,None)
    sheet=Image.new('RGB',(1200,876),'#f4f4fa');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype(str(ROOT/'assets/fonts/NotoSans-Variable.ttf'),17)
    for index,(title,palette) in enumerate(zip(titles,palettes)):
        bpm=72+index*21
        pad=np.sin(2*np.pi*(110+index*17)*t)*.08
        kick=np.sin(2*np.pi*90*t)*np.exp(-(t%(60/bpm))*25)*.48
        mix=np.interp(t,(0,8,16,24),(.15,.3,1,.3))
        samples=pad+kick*mix
        source=output/f'synthetic-{index}.wav'
        with wave.open(str(source),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(rate)
            stream.writeframes((samples*32767).astype('<i2').tobytes())
        bundle=DEFAULT_PIPELINE.analyse(source)
        settings=dict(pattern='timeline',color_source='speed' if palette is None else 'custom')
        if palette:settings['colors']=palette
        art=render_variant(source,bundle.visual_dna,bundle.visual_plan,size=1000,seed=index*11,
            style='custom' if palette else 'generated',custom_cover_settings=settings)
        art,symbol=_add_cover_symbol(art,bundle.visual_dna,title,variation=index*11)
        layout={}
        art=_add_cover_text(art,title,'',text_mode='title',language='mixed',visual_dna=bundle.visual_dna,
                            symbol_layout=symbol,layout_out=layout)
        assert layout['ink_color']==symbol['material_color']
        assert layout['contrast_ratio']>=4.5 and symbol['contrast_ratio']>=3
        art.save(output/f'cover-{index+1}.png')
        x=(index%3)*400;y=(index//3)*438
        sheet.paste(art.resize((400,400),Image.Resampling.LANCZOS),(x,y+38))
        draw.text((x+8,y+6),f'{title} / {symbol["composition"]["secondary_family"]}',font=font,fill='#292938')
    sheet.save(output/'covers.png')
    print(f'6 covers verified: shared ink, readable contrast, organic chronological background. {output}')


if __name__=='__main__':
    main()
