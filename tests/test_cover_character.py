from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageChops

from music2picture_v2.audio_analysis import analyze_audio_array
from music2picture_v2.character import accent_mask, musical_character, palette_positions
from music2picture_v2.custom_style import finish_custom_background, palette_rgb
from music2picture_v2.renderer import artistic_parameters, render_cover, _value_noise, _sample_wrapped
from music2picture_v2.semantics import build_visual_dna
from music2picture_v2.variants import render_variant
from music2picture_v2.visual_plan import build_visual_plan


class CoverCharacterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rate = 8000
        t = np.arange(cls.rate * 36) / cls.rate
        cls.calm = ((.06 * np.sin(2 * np.pi * 180 * t) + .035 * np.sin(2 * np.pi * 270 * t))
                    * (.8 + .2 * np.sin(2 * np.pi * .25 * t))).astype(np.float32)
        cls.driven = (.5 * np.sin(2 * np.pi * 65 * t) * np.exp(-np.mod(t, .375) * 24)
                      + np.random.default_rng(8).normal(0, .12, len(t)) * np.exp(-np.mod(t, .1875) * 60)
                      + .15 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        cls.calm_dna = build_visual_dna(analyze_audio_array(cls.calm, cls.rate))
        cls.driven_dna = build_visual_dna(analyze_audio_array(cls.driven, cls.rate))

    def mixed(self, main, opposite):
        return build_visual_dna(analyze_audio_array(np.concatenate(
            (main[:self.rate * 27], opposite[:self.rate * 9])), self.rate))

    def test_real_audio_drive_chooses_left_and_right_without_per_song_stretch(self):
        calm, driven = musical_character(self.calm_dna), musical_character(self.driven_dna)
        self.assertLess(calm.drive, .4)
        self.assertGreater(driven.drive, .6)
        self.assertEqual(calm.accent_share, 0)
        self.assertEqual(driven.accent_share, 0)
        texture = np.tile(np.linspace(0, 1, 256, dtype=np.float32), (256, 1))
        self.assertLess(float(palette_positions(texture, self.calm_dna).max()), .5)
        self.assertGreater(float(palette_positions(texture, self.driven_dna).min()), .5)

    def test_opposite_sections_create_small_accents_in_both_directions(self):
        texture = np.tile(np.linspace(0, 1, 256, dtype=np.float32), (256, 1))
        for main, opposite, reference in ((self.calm, self.driven, self.calm_dna),
                                          (self.driven, self.calm, self.driven_dna)):
            with self.subTest(drive=musical_character(reference).drive):
                mixed = self.mixed(main, opposite)
                character = musical_character(mixed)
                self.assertAlmostEqual(character.drive, musical_character(reference).drive, delta=.08)
                self.assertGreater(character.accent_share, .02)
                self.assertLessEqual(character.accent_share, .12)
                field = palette_positions(texture, mixed)
                # Minority sections tint existing folds; they must not produce
                # an opaque patch filled with the opposite end of the palette.
                plain = palette_positions(texture, replace(mixed, activity_curve=(character.drive,) * 12))
                difference = field - plain
                direction = 1 if character.opposite_drive > character.drive else -1
                self.assertGreater(float(np.mean(difference * direction)), .005)
                self.assertLess(float(np.mean(np.abs(difference))), .09)
                self.assertLess(float(np.max(np.abs(difference))), .25)
                self.assertLess(float(np.mean(field > .5 if character.drive < .5 else field < .5)), .15)
                self.assertEqual(artistic_parameters(mixed, build_visual_plan(mixed)).composition,
                                 artistic_parameters(reference, build_visual_plan(reference)).composition)

    def test_silence_intro_never_creates_false_calm_section(self):
        signal = np.concatenate((np.zeros(self.rate * 9, dtype=np.float32), self.driven[:self.rate * 27]))
        dna = build_visual_dna(analyze_audio_array(signal, self.rate))
        self.assertAlmostEqual(musical_character(dna).drive, musical_character(self.driven_dna).drive, delta=.05)
        self.assertEqual(musical_character(dna).accent_share, 0)

    def test_half_time_tempo_does_not_override_dense_local_rhythm(self):
        half_time = replace(self.driven_dna, tempo=35, tempo_confidence=1)
        profile = musical_character(half_time)
        self.assertGreater(profile.drive, .6)
        self.assertAlmostEqual(profile.drive, musical_character(self.driven_dna).drive, delta=.06)

    def test_single_transients_invalid_values_and_constant_curves_do_not_add_accents(self):
        for curve in ((.2,) * 30, (.2,) * 10 + (.9,) + (.2,) * 19,
                      (0,) * 4 + (.8,) * 24 + (0,) * 4, (float('nan'), float('inf'), 0)):
            with self.subTest(curve=curve):
                profile = musical_character(replace(self.calm_dna, activity_curve=curve))
                self.assertEqual(profile.accent_share, 0)
                self.assertTrue(np.isfinite(profile.drive))

    def test_accent_fraction_is_bounded_even_for_a_large_opposite_section(self):
        dna = replace(self.calm_dna, activity_curve=(.15,) * 35 + (.95,) * 29)
        character = musical_character(dna)
        self.assertLess(character.drive, .3)
        self.assertLessEqual(character.accent_share, .12)
        mask = accent_mask((512, 512), character)
        self.assertLessEqual(float(mask.max()), .34001)
        self.assertLessEqual(float(mask.mean()), character.accent_share + 1e-5)
        self.assertGreater(float(mask.mean()), .02)

    def test_seed_and_fingerprint_do_not_override_musical_pattern_family(self):
        for dna in (self.calm_dna, self.driven_dna):
            families = set()
            schemes = set()
            for seed in range(12):
                changed = replace(dna, fingerprint=f'test-track-{seed}')
                plan = build_visual_plan(changed, variation=seed)
                parameters = artistic_parameters(changed, plan, resolved_seed=seed)
                families.add(parameters.composition)
                schemes.add(plan.palette_scheme)
                self.assertAlmostEqual(parameters.palette_position, musical_character(dna).drive)
            self.assertEqual(len(families), 1)
            self.assertEqual(len(schemes), 1)
        calm = artistic_parameters(self.calm_dna, build_visual_plan(self.calm_dna))
        driven = artistic_parameters(self.driven_dna, build_visual_plan(self.driven_dna))
        self.assertGreater(driven.turbulence, calm.turbulence)
        self.assertGreater(driven.vein_strength, calm.vein_strength)
        self.assertNotEqual(calm.composition, driven.composition)

    def test_custom_color_selection_respects_markers_and_preserves_minor_accents(self):
        gradient = Image.fromarray(np.tile(np.arange(256, dtype=np.uint8), (256, 1)), 'L')
        settings = dict(colors=['#0000ff', '#0000ff', '#ff0000', '#ff0000'],
                        positions=[0, .4, .6, 1])
        for dna, expected_red in ((self.calm_dna, False), (self.driven_dna, True)):
            pixels = np.asarray(finish_custom_background(gradient, settings, dna)).astype(np.int16)
            red_share = float(np.mean(pixels[..., 0] > pixels[..., 2]))
            self.assertGreater(red_share, .99) if expected_red else self.assertLess(red_share, .01)
        for main, opposite, expected_red in ((self.calm, self.driven, False),
                                             (self.driven, self.calm, True)):
            dna = self.mixed(main, opposite)
            pixels = np.asarray(finish_custom_background(gradient, settings, dna)).astype(np.int16)
            plain_dna = replace(dna, activity_curve=(musical_character(dna).drive,) * 12)
            plain = np.asarray(finish_custom_background(gradient, settings, plain_dna)).astype(np.int16)
            # Repeated blue/red stops deliberately create flat hue plateaus;
            # a restrained accent can remain in that hue and change its tone.
            self.assertGreater(float(np.mean(np.abs(pixels - plain))), .05)
            self.assertLess(float(np.mean(np.abs(pixels - plain))), 20)
            fraction = float(np.mean((pixels[..., 0] < pixels[..., 2]) if expected_red
                                    else (pixels[..., 0] > pixels[..., 2])))
            self.assertLess(fraction, .15)
        with patch('music2picture_v2.custom_style.palette_rgb', wraps=palette_rgb) as lookup:
            finish_custom_background(gradient.resize((1024, 1024)), settings, self.driven_dna)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(lookup.call_args.args[1].shape, (4096,))

    def test_classic_custom_pattern_also_receives_song_sensitive_palette(self):
        base = Image.new('RGB', (128, 128), 'gray')
        settings = dict(pattern='legacy', colors=['#0000ff', '#ff0000'])
        with patch('music2picture_v2.variants.render_legacy', return_value=base):
            calm = render_variant('unused', self.calm_dna, build_visual_plan(self.calm_dna),
                                  style='custom', custom_cover_settings=settings)
            driven = render_variant('unused', self.driven_dna, build_visual_plan(self.driven_dna),
                                    style='custom', custom_cover_settings=settings)
        self.assertIsNotNone(ImageChops.difference(calm, driven).getbbox())

    def test_rendering_is_reproducible_and_analysis_profile_serializes(self):
        dna = self.mixed(self.calm, self.driven)
        plan = build_visual_plan(dna)
        self.assertIn('activity_curve', dna.to_dict())
        self.assertIsNone(ImageChops.difference(render_cover(dna, plan, size=192, seed=4),
                                               render_cover(dna, plan, size=192, seed=4)).getbbox())

    def test_accents_follow_existing_contours_not_image_coordinates(self):
        character = musical_character(self.mixed(self.driven, self.calm))
        texture = np.tile(np.linspace(0, 1, 256, dtype=np.float32), (256, 1))
        mask = accent_mask(texture.shape, character, texture)
        np.testing.assert_allclose(mask[0], mask[-1], atol=1e-6)
        self.assertLessEqual(float(mask.max()), .34001)
        self.assertGreater(float(mask[0].max()), .10)
        # Moving geometry moves the accents with it, rather than leaving a blob.
        np.testing.assert_allclose(accent_mask(texture.shape, character, texture[:, ::-1]),
                                   mask[:, ::-1], atol=1e-6)

    def test_palette_has_tonal_and_color_depth_without_using_the_whole_scale(self):
        texture = np.tile(np.linspace(0, 1, 256, dtype=np.float32), (256, 1))
        for dna in (self.calm_dna, self.driven_dna):
            field = palette_positions(texture, dna)
            self.assertGreater(float(np.ptp(field)), .30)
            self.assertLess(float(np.ptp(field)), .45)
            image = render_cover(dna, build_visual_plan(dna), size=256, seed=3,
                                 palette=('#cc6644',), palette_stops=(0,))
            pixels = np.asarray(image, dtype=np.float32)
            light = pixels @ np.array([.2126, .7152, .0722])
            self.assertGreater(float(np.percentile(light, 90) - np.percentile(light, 10)), 30)
            self.assertLess(float(np.mean(pixels >= 250)), .03)

    def test_warped_noise_has_no_wrapping_seam(self):
        noise = _value_noise(256, 4, np.random.default_rng(8))
        ys = np.linspace(-1, 1, 256, dtype=np.float32)[None, :]
        before = _sample_wrapped(noise, np.full(ys.shape, .99999), ys)
        after = _sample_wrapped(noise, np.full(ys.shape, 1.00001), ys)
        self.assertLess(float(np.max(np.abs(before - after))), .001)

    def test_preview_preserves_final_composition_and_colors(self):
        for dna in (self.calm_dna, self.driven_dna):
            plan = build_visual_plan(dna)
            preview = render_cover(dna, plan, size=768, seed=5, preview=True)
            final = render_cover(dna, plan, size=768, seed=5)
            first = np.asarray(preview.resize((384, 384), Image.Resampling.LANCZOS), dtype=np.float32)
            second = np.asarray(final.resize((384, 384), Image.Resampling.LANCZOS), dtype=np.float32)
            self.assertLess(float(np.mean(np.abs(first - second))), 8)

    def test_custom_modern_palette_is_applied_once_and_keeps_rendered_relief(self):
        dna = self.driven_dna
        settings = dict(colors=['#113366', '#338866', '#ff8844'], positions=[0, .3, 1])
        from music2picture_v2.custom_style import finish_custom_background
        with patch('music2picture_v2.variants.render_cover', wraps=render_cover) as renderer, \
             patch('music2picture_v2.custom_style.finish_custom_background',
                   wraps=finish_custom_background) as finish:
            render_variant('unused', dna, build_visual_plan(dna), style='custom',
                           size=192, seed=2, custom_cover_settings=settings)
        self.assertEqual(renderer.call_args.kwargs['palette'], tuple(settings['colors']))
        self.assertEqual(renderer.call_args.kwargs['palette_stops'], tuple(settings['positions']))
        self.assertFalse(finish.call_args.kwargs['recolor'])


if __name__ == '__main__':
    unittest.main()
