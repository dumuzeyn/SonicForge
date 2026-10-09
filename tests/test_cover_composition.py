import unittest
import math
from dataclasses import replace

import numpy as np
from PIL import Image,ImageChops
import music2picture
from cover_engine.song_symbol import compose_song_symbol
from cover_engine.music_lettering import intersection_fraction
from cover_engine.titles import resolve_title
from music2picture_v2.audio_analysis import analyze_audio_array
from music2picture_v2.semantics import build_visual_dna


class CoverCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dna=build_visual_dna(analyze_audio_array(np.zeros(22050,dtype=np.float32)))

    def test_secondary_shapes_fill_outer_space_and_change_with_musical_language(self):
        base=Image.new('RGB',(384,384),'#83374e')
        for title,language in (('Spin','motion'),('Crystal','facets'),('Heart','organic')):
            with self.subTest(title=title):
                image,plan=compose_song_symbol(base,self.dna,title)
                scene=plan['composition']
                self.assertEqual(scene['language'],language)
                self.assertGreaterEqual(scene['secondary_count'],5)
                difference=ImageChops.difference(base,image)
                difference.paste((0,0,0),plan['bounds'])
                self.assertGreater(np.count_nonzero(np.asarray(difference).max(axis=2)>15),384*384*.03)

    def test_long_title_and_artist_fit_the_reserved_space_at_small_export_sizes(self):
        dna=replace(self.dna,roughness=.6,arousal=.9,brightness=.8,attack_strength=.85)
        title='Кружит — Очень длинное название / Another long title'
        for size in (192,384,1000):
            base=Image.new('RGB',(size,size),'#83374e')
            artwork,symbol=compose_song_symbol(base,dna,title)
            layout={}
            music2picture._add_cover_text(artwork,title,'Исполнитель / Artist',text_mode='title_artist',language='mixed',
                                         visual_dna=dna,layout_out=layout,symbol_layout=symbol)
            self.assertEqual(intersection_fraction(layout['ink_bounds'],symbol['bounds']),0)
            zone=symbol['composition']['title_zone_pixels'];ink=layout['ink_bounds']
            self.assertGreaterEqual(ink[0],zone[0]);self.assertGreaterEqual(ink[1],zone[1])
            self.assertLessEqual(ink[2],zone[2]);self.assertLessEqual(ink[3],zone[3])
            self.assertGreaterEqual(layout['contrast_ratio'],4.5)

    def test_scene_respects_protected_artwork_and_hidden_title_has_no_reserved_zone(self):
        base=Image.new('RGB',(384,384),'#83374e')
        box=(10,10,45,45)
        image,plan=compose_song_symbol(base,self.dna,'Spin',protected_boxes=(box,),show_title=False)
        self.assertIsNone(plan['composition']['title_zone_pixels'])
        self.assertIsNone(ImageChops.difference(base.crop(box),image.crop(box)).getbbox())

    def test_title_and_optional_artist_survive_a_round_player_crop(self):
        soft=replace(self.dna,roughness=.08,arousal=.2,rhythmic_density=.1,attack_strength=.05,
                     crest_factor=.9,bass_mass=.3,absolute_loudness=.3,relaxation=.9,
                     brightness=.15,spectral_flux=.02)
        titles=('КРУЖИТ','Ёлки — Another very long song title / Ночная история')
        for dna in (self.dna,soft):
            for title in titles:
                for size in (192,384,1000):
                    for mode in ('title','title_artist'):
                        with self.subTest(title=title,size=size,mode=mode):
                            base=Image.new('RGB',(size,size),'#83374e')
                            art,symbol=compose_song_symbol(base,dna,title)
                            layout={}
                            music2picture._add_cover_text(art,title,'Исполнитель / Artist',text_mode=mode,
                                                         language='mixed',visual_dna=dna,layout_out=layout,
                                                         symbol_layout=symbol)
                            self.assertEqual(' '.join(layout['display_lines']),resolve_title(title,'stylized').selected)
                            self.assertEqual(layout['round_safe_radius'],.46)
                            x0,y0,x1,y1=layout['ink_bounds']
                            for x,y in ((x0,y0),(x0,y1),(x1,y0),(x1,y1)):
                                self.assertLessEqual(math.hypot(x-size/2,y-size/2),size*.46+2)
                            self.assertGreaterEqual(layout['contrast_ratio'],4.5)


if __name__=='__main__':
    unittest.main()
