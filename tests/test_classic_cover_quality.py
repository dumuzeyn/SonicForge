"""Classic artwork keeps its musical geometry without pixel-grain overload."""
from unittest.mock import patch
import unittest

import numpy as np
from PIL import Image, ImageChops

from music2picture_v2 import legacy_music2picture as legacy
from music2picture_v2.variants import automatic_classic_detail, render_legacy


class ClassicCoverQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(14)
        t = np.linspace(0, 1, 160, dtype=np.float32)
        cls.spec = rng.uniform(.1, .95, (64, 160)).astype(np.float32)
        cls.rms = (.55 + .28 * np.sin(t * 29)).astype(np.float32)
        cls.bass = (.4 + .24 * np.sin(t * 14)).astype(np.float32)
        cls.mids = (.48 + .23 * np.sin(t * 22)).astype(np.float32)
        cls.highs = (.5 + .3 * np.sin(t * 31)).astype(np.float32)
        cls.centroid = np.full(160, .3, dtype=np.float32)
        cls.features = (cls.spec, cls.rms, cls.bass, cls.mids, cls.highs, cls.centroid)

    def render(self, detail, mode='plasma', seed=3):
        size = 384
        return legacy.render_random_cover(self.spec, self.rms, self.bass, self.mids, self.highs,
                                          size, bpm=136, bpm_curve=np.full(size, 136, dtype=np.float32),
                                          energy_curve=np.linspace(.25, .75, size, dtype=np.float32),
                                          global_energy=.6, color_mode=mode,
                                          detail=detail, rng=np.random.default_rng(seed))

    @staticmethod
    def chatter(pixels):
        pixels = np.asarray(pixels, dtype=np.float32) / 255
        neighbors = (pixels[:-2, 1:-1] + pixels[2:, 1:-1]
                     + pixels[1:-1, :-2] + pixels[1:-1, 2:]) * .25
        return float(np.mean(np.abs(pixels[1:-1, 1:-1] - neighbors)))

    def test_clean_generation_reduces_pixel_chatter_without_flattening_the_pattern(self):
        for seed in (0, 3, 42):
            original = self.render(None, seed=seed)
            clean = self.render(35, seed=seed)
            self.assertLess(self.chatter(clean), self.chatter(original) * .40)
            small = np.asarray(Image.fromarray(clean).resize((32, 32)), dtype=np.float32)
            self.assertGreater(float(small.std()), 15)

    def test_classic_detail_is_continuous_not_five_values_collapsed_into_two(self):
        pictures = [self.render(detail) for detail in (0, 25, 50, 75, 100)]
        self.assertEqual(len({picture.tobytes() for picture in pictures}), 5)
        for detail in (0, 50, 100):
            np.testing.assert_array_equal(self.render(detail), self.render(detail))

    def test_short_or_uniform_tracks_do_not_receive_maximum_detail(self):
        uniform = np.full(100, .55, dtype=np.float32)
        varied = np.linspace(.1, .9, 100, dtype=np.float32)
        self.assertEqual(automatic_classic_detail(10, uniform), 20)
        self.assertLess(automatic_classic_detail(80, varied), 50)
        self.assertGreater(automatic_classic_detail(240, varied), 50)
        self.assertLess(automatic_classic_detail(240, uniform), 50)
        self.assertLessEqual(automatic_classic_detail(7200, varied), 60)

    def test_all_classic_color_modes_still_have_color_and_structure(self):
        for mode in ('ocean', 'plasma', 'fusion', 'aurora'):
            with self.subTest(mode=mode):
                result = self.render(40, mode=mode)
                self.assertEqual(result.shape, (384, 384, 3))
                self.assertEqual(result.dtype, np.uint8)
                self.assertGreater(float(result.std()), 15)
                self.assertGreater(float(np.abs(result[..., 0].astype(np.int16)
                                                - result[..., 2]).mean()), 10)

    def test_wrapper_preserves_rich_historical_geometry_even_for_short_tracks(self):
        for duration in (20, 240):
            with patch.object(legacy, 'read_audio', return_value=np.zeros(duration * 22050, dtype=np.float32)), \
                 patch.object(legacy, 'stft_features', return_value=self.features), \
                 patch.object(legacy, 'estimate_energy_profile', return_value=(np.linspace(.1, .9, 128), .6, {})), \
                 patch.object(legacy, 'render_random_cover', return_value=np.zeros((128, 128, 3), dtype=np.uint8)) as render:
                render_legacy('unused.mp3', size=128, seed=0)
            self.assertEqual(render.call_args.kwargs['patterns'], 2)
            self.assertLessEqual(render.call_args.kwargs['detail'], 60)

    def test_cleanup_does_not_change_historical_warp_coordinates(self):
        # Preserve seed-specific fields and all angular/stripe geometry. Noise
        # reduction must not substitute a simpler, generic-looking pattern.
        coordinates = []
        sampler = legacy.sample_map_bilinear

        def record(song_map, part, frequency):
            coordinates.append((part.copy(), frequency.copy()))
            return sampler(song_map, part, frequency)

        with patch.object(legacy, 'sample_map_bilinear', side_effect=record):
            self.render(None)
            self.render(0)
            self.render(100)
        self.assertEqual(len(coordinates), 3)
        for part, frequency in coordinates[1:]:
            np.testing.assert_array_equal(part, coordinates[0][0])
            np.testing.assert_array_equal(frequency, coordinates[0][1])

    def test_grain_filter_preserves_sharp_boundaries_without_blur(self):
        pixels = np.zeros((32, 32, 3), dtype=np.uint8)
        pixels[:, 16:] = 255
        pixels[8, 8] = 255  # Isolated grit, not a contour.
        result = legacy.remove_classic_pixel_grain(pixels)
        self.assertEqual(set(np.unique(result)), {0, 255})
        self.assertEqual(int(result[8, 8].max()), 0)
        np.testing.assert_array_equal(result[:, 15], 0)
        np.testing.assert_array_equal(result[:, 16], 255)

    def test_large_output_does_not_expand_renderer_complexity_or_working_arrays(self):
        with patch.object(legacy, 'read_audio', return_value=np.zeros(22050, dtype=np.float32)), \
             patch.object(legacy, 'stft_features', return_value=self.features), \
             patch.object(legacy, 'render_random_cover', return_value=np.zeros((64, 64, 3), dtype=np.uint8)) as render:
            result = render_legacy('unused.mp3', size=4096, seed=0)
        self.assertEqual(render.call_args.args[5], 1000)
        self.assertEqual(result.size, (4096, 4096))

    def test_detail_errors_are_reported_and_filters_preserve_seed(self):
        with patch.object(legacy, 'read_audio', return_value=np.zeros(22050, dtype=np.float32)), \
             patch.object(legacy, 'stft_features', return_value=self.features):
            for invalid in (-1, 101, float('nan'), float('inf')):
                with self.subTest(detail=invalid), self.assertRaises(ValueError):
                    render_legacy('unused.mp3', size=128, detail=invalid)
            first = render_legacy('unused.mp3', size=192, detail=50, seed=9)
            repeated = render_legacy('unused.mp3', size=192, detail=50, seed=9)
        self.assertIsNone(ImageChops.difference(first, repeated).getbbox())

    def test_smoothing_never_wraps_opposite_image_edges(self):
        field = np.zeros((32, 32), dtype=np.float32)
        field[:, 0] = 1
        smoothed = legacy.smooth_artwork_field(field, passes=3)
        self.assertGreater(float(smoothed[:, 0].mean()), 0)
        self.assertEqual(float(smoothed[:, -1].max()), 0)


if __name__ == '__main__':
    unittest.main()
