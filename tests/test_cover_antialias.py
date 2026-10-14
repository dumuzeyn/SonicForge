import unittest

import numpy as np
from PIL import Image, ImageDraw

from cover_engine.raster import downsample_coverage
from cover_engine.music_lettering import design_from_music, line_mask
from cover_engine.typography import TypographyEngine
from music2picture_v2 import analyze_audio_array, build_visual_dna


class CoverAntialiasTests(unittest.TestCase):
    def test_diagonal_coverage_matches_a_high_resolution_reference(self):
        def diagonal(scale):
            mask=Image.new('L',(64*scale,64*scale))
            ImageDraw.Draw(mask).polygon([(5*scale,10*scale),(57*scale,48*scale),
                                          (57*scale,52*scale),(5*scale,14*scale)],fill=255)
            return mask
        reference=np.asarray(downsample_coverage(diagonal(24),(64,64)),dtype=float)
        antialiased=np.asarray(downsample_coverage(diagonal(6),(64,64)),dtype=float)
        hard=np.asarray(diagonal(1),dtype=float)
        error=np.abs(antialiased-reference).mean()
        self.assertLess(error,np.abs(hard-reference).mean()*.35)
        self.assertGreater(np.count_nonzero((antialiased>0)&(antialiased<255)),150)
        self.assertAlmostEqual(float(antialiased.sum()/reference.sum()),1,delta=.035)

    def test_area_sampling_keeps_edges_bounded_without_ringing(self):
        mask=Image.new('L',(384,384))
        ImageDraw.Draw(mask).rectangle((96,72,287,311),fill=255)
        sampled=np.asarray(downsample_coverage(mask,(64,64)))
        self.assertEqual(int(sampled[:,:14].max()),0)
        self.assertEqual(int(sampled[:,50:].max()),0)
        self.assertEqual(int(sampled[20:44,20:44].min()),255)
        row=sampled[32].astype(int)
        self.assertTrue((np.diff(row[:32])>=0).all())
        self.assertTrue((np.diff(row[32:])<=0).all())

    def test_cyrillic_and_latin_glyphs_retain_subpixel_edge_coverage(self):
        dna=build_visual_dna(analyze_audio_array(np.zeros(22050,dtype=np.float32)))
        design=design_from_music(dna)
        for title in ('Swan','Ёлки и свет','AV КРУЖИТ'):
            mask,_,_=line_mask(TypographyEngine(),title,48,design)
            alpha=np.asarray(mask)
            self.assertGreater(np.count_nonzero((alpha>0)&(alpha<255)),150)
            self.assertGreater(int(alpha.max()),220)


if __name__=='__main__':
    unittest.main()
