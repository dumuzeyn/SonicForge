import unittest
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from cover_engine.music_lettering import clusters, design_from_music, intersection_fraction, positions
from cover_engine.typography import NOTO_SANS, TypographyEngine
from music2picture_v2.audio_analysis import analyze_audio_array
from music2picture_v2.semantics import build_visual_dna


class MusicLetteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = build_visual_dna(analyze_audio_array(np.zeros(22050, dtype=np.float32)))
        cls.soft = replace(cls.base, tempo=120, tempo_confidence=1, roughness=.10, brightness=.08,
                           attack_strength=.16, spectral_flux=.05, arousal=.28, relaxation=.88,
                           crest_factor=.85, bass_mass=.28, rhythmic_density=.12, valence=.58)
        cls.hard = replace(cls.soft, roughness=.73, brightness=.63, attack_strength=.88,
                           spectral_flux=.72, arousal=.86, relaxation=.12, crest_factor=.18,
                           bass_mass=.84, rhythmic_density=.85, valence=.28, tension=.82)

    def test_same_tempo_can_have_opposite_letterforms(self):
        calm, force = design_from_music(self.soft), design_from_music(self.hard)
        self.assertGreater(force.weight - calm.weight, 250)
        self.assertGreater(force.angularity - calm.angularity, .5)
        self.assertGreater(calm.width, force.width)
        self.assertGreater(calm.tracking, force.tracking)
        self.assertNotEqual(calm.family, force.family)
        self.assertNotEqual(calm.preferred_placement, force.preferred_placement)

    def test_dynamic_vocal_and_timbre_controls_are_continuous(self):
        moderate = replace(self.soft, roughness=.24, arousal=.5, crest_factor=.3,
                           absolute_loudness=.8, bass_mass=.5, attack_strength=.55)
        base = design_from_music(moderate)
        changed = design_from_music(replace(moderate, roughness=.25))
        self.assertNotEqual(base.weight, changed.weight)
        self.assertLess(abs(base.weight-changed.weight), 30)
        dynamic = design_from_music(replace(self.soft, dynamic_complexity=.9, original_dynamic_range=.9))
        self.assertGreater(dynamic.line_contrast, design_from_music(self.soft).line_contrast)
        absent = design_from_music(replace(self.soft, vocal_probability=0))
        likely = design_from_music(replace(self.soft, vocal_probability=1, acousticness=1))
        self.assertNotEqual(absent.slant, likely.slant)
        self.assertLessEqual(likely.vocal_influence, .15)

    def test_kerning_and_combining_marks_use_the_same_fit_and_draw_metrics(self):
        font = TypographyEngine._font(80, (NOTO_SANS,), "AV Ёж")
        items, width = positions("AV", font, 0)
        self.assertAlmostEqual(width, font.getlength("AV"), places=5)
        self.assertLess(width, font.getlength("A") + font.getlength("V"))
        self.assertEqual(clusters("е\u0301ж"), ["е\u0301", "ж"])
        self.assertEqual(len(positions("е\u0301ж", font, 2)[0]), 2)
        self.assertTrue(TypographyEngine._supports_text(font, "Ёж AV"))
        self.assertFalse(TypographyEngine._supports_text(font, "\U0010ffff"))

    def test_mixed_script_titles_export_without_clipping_or_missing_text(self):
        title = "Ёлки и Ещё Один Очень Долгий Ночной Сон — After Midnight"
        for size in (192, 384, 1000):
            with self.subTest(size=size):
                engine = TypographyEngine()
                image = Image.new("RGB", (size, size), "#182536")
                result = engine.compose(image, title, "Исполнитель / Artist", visual_dna=self.hard)
                layout = engine.last_layout
                self.assertEqual(" ".join(layout["display_lines"]), title)
                left, top, right, bottom = layout["ink_bounds"]
                self.assertGreaterEqual(min(left, top), 0)
                self.assertLessEqual(max(right, bottom), size)
                self.assertGreaterEqual(layout["contrast_ratio"], 4.5)
                self.assertIsNotNone(ImageChops.difference(image, result).getbbox())

    def test_busy_background_has_measured_linear_srgb_contrast(self):
        pixels = np.random.default_rng(14).integers(0, 256, (384, 384, 3), dtype=np.uint8)
        engine = TypographyEngine()
        engine.compose(Image.fromarray(pixels), "Мало тебя / Stay", visual_dna=self.hard)
        self.assertGreaterEqual(engine.last_layout["contrast_ratio"], 4.5)
        self.assertTrue(engine.last_layout["adaptive_veil"])
        self.assertEqual(engine.last_layout["decoration"], "none")

    def test_actual_ink_avoids_supplied_subject_bounds(self):
        image = Image.new("RGB", (600, 600), "#1b2935")
        protected = (120, 100, 480, 450)
        ImageDraw.Draw(image).ellipse(protected, fill="#cfa588")
        engine = TypographyEngine()
        engine.compose(image, "Тихий Свет", visual_dna=self.soft,
                       profile=SimpleNamespace(candidate_type="portrait", protected_boxes=(protected,)))
        self.assertEqual(intersection_fraction(engine.last_layout["ink_bounds"], protected), 0)

    def test_repeatability_and_disabled_text(self):
        image = Image.new("RGB", (384, 384), "#123544")
        engine = TypographyEngine()
        first = engine.compose(image, "Песня / Song", visual_dna=self.soft)
        layout = dict(engine.last_layout)
        second = engine.compose(image, "Песня / Song", visual_dna=self.soft)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(layout, engine.last_layout)
        self.assertIs(engine.compose(image, "Песня", enabled=False, visual_dna=self.hard), image)
        self.assertEqual(engine.last_layout, {})


if __name__ == "__main__":
    unittest.main()
