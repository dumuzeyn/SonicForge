from dataclasses import replace
import unittest

import numpy as np
from PIL import Image

import music2picture
from cover_engine.composition import spatial_plan, supporting_artwork
from cover_engine.materials import cover_material
from cover_engine.song_symbol import symbol_plan, compose_song_symbol
from cover_engine.supporting_shapes import SECONDARY_FAMILIES
from music2picture_v2 import analyze_audio_array, build_visual_dna
from music2picture_v3.renderer import TimelineFields, flowing_timeline, flowing_time_coordinates


class CoverAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dna = build_visual_dna(analyze_audio_array(np.zeros(22050, dtype=np.float32)))

    def test_spectral_pulse_lines_are_suppressed_without_losing_song_sections(self):
        size=256
        stripes=np.zeros((size,size),dtype=np.float32);stripes[:,::4]=1
        level=np.ones((1,size),dtype=np.float32)*.6
        fields=flowing_timeline(TimelineFields(stripes,level,level,level),size)
        before=np.abs(np.diff(stripes,axis=1)).mean()
        after=np.abs(np.diff(fields.spectrum,axis=1)).mean()
        self.assertLess(after,before*.10)
        regions=np.zeros_like(stripes);regions[:,size//2:]=1
        fields=flowing_timeline(TimelineFields(regions,level,level,level),size)
        self.assertGreater(fields.spectrum[:,-32:].mean()-fields.spectrum[:,:32].mean(),.9)
        boundary=np.argmax(fields.spectrum>.5,axis=1)
        self.assertGreater(np.ptp(boundary),8)

    def test_curved_mapping_preserves_chronology_and_anchored_ends(self):
        coords=flowing_time_coordinates(256,256,.8)
        self.assertTrue((np.diff(coords,axis=1)>0).all())
        self.assertEqual(float(coords[:,0].max()),0)
        np.testing.assert_allclose(coords[:,-1],1,atol=1e-6)
        original=np.linspace(0,1,256)[None,:]
        self.assertLess(float(np.max(np.abs(coords-original))),.04)

    def test_text_and_symbol_share_a_colored_ink_with_readable_contrast(self):
        for color in ('#183a65','#3c6b48','#914a68','#dae9f4'):
            with self.subTest(color=color):
                base=Image.new('RGB',(384,384),color)
                art,symbol=compose_song_symbol(base,self.dna,'Lotus',variation=4)
                layout={}
                music2picture._add_cover_text(art,'Lotus','',text_mode='title',language='en',
                    visual_dna=self.dna,layout_out=layout,symbol_layout=symbol)
                self.assertEqual(layout['ink_color'],symbol['material_color'])
                self.assertGreater(max(layout['ink_color'])-min(layout['ink_color']),15)
                self.assertGreaterEqual(layout['contrast_ratio'],4.5)
                self.assertGreaterEqual(symbol['contrast_ratio'],3)

    def test_all_sixty_secondary_schemes_render_distinct_artwork(self):
        self.assertEqual(sum(len(values) for values in SECONDARY_FAMILIES.values()),60)
        self.assertEqual(len(set(name for values in SECONDARY_FAMILIES.values() for name in values)),60)
        base=Image.new('RGB',(192,192),'#314768')
        plan=symbol_plan(self.dna,'Heart')
        plan.update(center=(.5,.48),bounds=(72,60,120,130),material_color=(185,209,236),
                    material_palette=cover_material(base))
        results=[]
        for language,families in SECONDARY_FAMILIES.items():
            for variant,family in enumerate(families):
                with self.subTest(family=family):
                    scene=spatial_plan(plan,'',show_title=False)
                    scene.update(language=language,secondary_variant=variant,secondary_family=family)
                    image,scene=supporting_artwork(base,plan,scene)
                    self.assertGreater(scene['secondary_count'],2)
                    self.assertFalse(image.tobytes()==base.tobytes())
                    results.append(image.tobytes())
        self.assertEqual(len(set(results)),60)

    def test_seed_changes_secondary_layout_and_repeat_is_identical(self):
        first=symbol_plan(self.dna,'Heart',variation=0)
        other=symbol_plan(self.dna,'Heart',variation=1)
        self.assertEqual(first['motif'],other['motif'])
        a=spatial_plan(first,'Heart');b=spatial_plan(other,'Heart')
        self.assertNotEqual((a['secondary_family'],a['secondary_phase']),
                            (b['secondary_family'],b['secondary_phase']))
        self.assertEqual(a,spatial_plan(first,'Heart'))


if __name__=='__main__':
    unittest.main()
