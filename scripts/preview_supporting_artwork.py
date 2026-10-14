"""Preview all sixty secondary compositions against the same cover material."""
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cover_engine.song_symbol import symbol_plan
from cover_engine.composition import spatial_plan,supporting_artwork
from cover_engine.materials import cover_material
from cover_engine.supporting_shapes import SECONDARY_FAMILIES
from music2picture_v2 import analyze_audio_array,build_visual_dna


def main():
    size=240
    base=Image.new('RGB',(size,size),'#314768')
    dna=build_visual_dna(analyze_audio_array(np.zeros(22050,dtype=np.float32)))
    plan=symbol_plan(dna,'Heart')
    plan.update(center=(.5,.48),bounds=(84,76,156,165),material_color=(185,209,236),
                material_palette=cover_material(base))
    sheet=Image.new('RGB',(1440,2700),'#f4f4fa');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype(str(ROOT/'assets/fonts/NotoSans-Variable.ttf'),12)
    results=[]
    for index,(language,variant,family) in enumerate((language,variant,family)
            for language,families in SECONDARY_FAMILIES.items() for variant,family in enumerate(families)):
        scene=spatial_plan(plan,'',show_title=False)
        scene.update(language=language,secondary_variant=variant,secondary_family=family)
        image,_=supporting_artwork(base,plan,scene)
        results.append(image.tobytes())
        x=(index%6)*240;y=(index//6)*270
        sheet.paste(image,(x,y+30))
        draw.text((x+6,y+4),f'{index+1:02d} {family}',font=font,fill='#292938')
    assert len(set(results))==60
    target=ROOT/'validation/cover-adaptation/60-secondary-schemes.png'
    target.parent.mkdir(parents=True,exist_ok=True)
    sheet.save(target)
    print(f'60 distinct secondary compositions: {target}')


if __name__=='__main__':
    main()
