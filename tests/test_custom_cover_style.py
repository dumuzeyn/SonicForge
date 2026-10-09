import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import numpy as np
from PIL import Image, ImageChops

import music2picture
from cover_engine.titles import resolve_title
from cover_engine.typography import TypographyEngine
from music2picture_v2.custom_style import CustomCoverSettings, finish_custom_background, palette_rgb
from music2picture_v2.variants import render_variant


class CustomCoverTests(unittest.TestCase):
    def test_invalid_settings_rejected(self):
        for settings in ({"pattern": "unknown"}, {"color_low": "file://anything"},
                         {"color_high": "#fff"}, {"detail": -1}, {"softness": 101},
                         {"contrast": float("nan")}, {"saturation": float("inf")},
                         {"detail": "50"}, {"detail": True}, {"unexpected": 1}, [1],
                         {"colors": []}, {"colors": "#123456"}, {"colors": ["#123456", "bad"]}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                CustomCoverSettings.parse(settings)

    def test_arbitrary_palette_length_and_stop_order(self):
        for count in (1, 10, 25, 1024):
            colors = [f"#{(index * 491 + 819) % 0x1000000:06x}" for index in range(count)]
            settings = CustomCoverSettings.parse(dict(colors=colors))
            self.assertEqual(list(settings.colors), colors)
            self.assertEqual(CustomCoverSettings.parse(json.loads(json.dumps(settings.to_dict()))), settings)
            samples = palette_rgb(settings.colors, np.linspace(0, 1, count))
            if count > 1:
                expected = np.asarray([[int(color[index:index + 2], 16) for index in (1, 3, 5)]
                                       for color in colors])
                np.testing.assert_allclose(samples, expected, atol=1)
        colors = ["#ff0000", "#00ff00", "#0000ff"]
        np.testing.assert_equal(palette_rgb(colors, [0, .5, 1]), [[255, 0, 0], [0, 255, 0], [0, 0, 255]])

    def test_previous_two_color_profile_migrates_without_losing_colors(self):
        settings = CustomCoverSettings.parse(dict(color_low="#112233", color_high="#ddeeff", detail=75))
        self.assertEqual(settings.colors, ("#112233", "#ddeeff"))
        self.assertEqual(settings.detail, 75)
        self.assertNotIn("color_low", settings.to_dict())
        self.assertEqual(settings.positions, (0, 1))

    def test_positions_validate_round_trip_and_change_rendered_gradient(self):
        for positions in ("bad", [0], [0, .8, .5], [0, False, 1], [0, float("nan"), 1],
                          [0, float("inf"), 1], [-.1, .5, 1], [0, .5, 1.1], [0, "0.5", 1]):
            with self.subTest(positions=positions), self.assertRaises(ValueError):
                CustomCoverSettings.parse(dict(colors=["#ff0000", "#00ff00", "#0000ff"], positions=positions))
        settings = CustomCoverSettings.parse(dict(colors=["#ff0000", "#00ff00", "#0000ff"], positions=[0, .25, 1]))
        self.assertEqual(CustomCoverSettings.parse(json.loads(json.dumps(settings.to_dict()))), settings)
        np.testing.assert_equal(palette_rgb(settings.colors, [0, .25, 1], settings.positions),
                                [[255, 0, 0], [0, 255, 0], [0, 0, 255]])
        np.testing.assert_equal(palette_rgb(settings.colors, [.125], settings.positions), [[127, 127, 0]])
        base = Image.fromarray(np.tile(np.arange(256, dtype=np.uint8), (10, 1)), "L").convert("RGB")
        shifted = finish_custom_background(base, settings)
        even = finish_custom_background(base, dict(colors=settings.colors))
        self.assertIsNotNone(ImageChops.difference(shifted, even).getbbox())
        for positions in ([.2, .2, .8], [0, 0, 0], [1, 1, 1]):
            duplicate = CustomCoverSettings.parse(dict(colors=settings.colors, positions=positions))
            self.assertEqual(finish_custom_background(base, duplicate).size, base.size)

    def test_single_color_keeps_texture_and_many_color_order_changes_output(self):
        gradient = np.tile(np.arange(256, dtype=np.uint8), (256, 1))
        base = Image.fromarray(gradient, "L").convert("RGB")
        one = finish_custom_background(base, dict(colors=["#336699"]))
        self.assertNotEqual(one.getpixel((0, 128)), one.getpixel((255, 128)))
        colors = [f"#{index * 11273 % 0x1000000:06x}" for index in range(1000)]
        forward = finish_custom_background(base, dict(colors=colors))
        reverse = finish_custom_background(base, dict(colors=colors[::-1]))
        self.assertIsNotNone(ImageChops.difference(forward, reverse).getbbox())

    def test_palette_range_and_filters_work(self):
        gradient = np.tile(np.arange(256, dtype=np.uint8), (256, 1))
        base = Image.fromarray(gradient, "L").convert("RGB")
        settings = dict(color_low="#112233", color_high="#ddeeff")
        colored = finish_custom_background(base, settings)
        self.assertEqual(colored.getpixel((0, 128)), (17, 34, 51))
        self.assertEqual(colored.getpixel((255, 128)), (221, 238, 255))
        gray = finish_custom_background(base, dict(settings, saturation=0))
        self.assertTrue(np.all(np.asarray(gray)[..., 0] == np.asarray(gray)[..., 2]))
        self.assertIsNotNone(ImageChops.difference(colored, finish_custom_background(base, dict(settings, contrast=150))).getbbox())
        checker = Image.fromarray(np.uint8((np.indices((256, 256)).sum(axis=0) % 2) * 255), "L")
        sharp = finish_custom_background(checker, settings)
        soft = finish_custom_background(checker, dict(settings, softness=100))
        self.assertIsNotNone(ImageChops.difference(sharp, soft).getbbox())

    def test_large_output_uses_a_small_palette_lookup(self):
        with patch("music2picture_v2.custom_style.palette_rgb", wraps=palette_rgb) as interpolate:
            finish_custom_background(Image.new("RGB", (1024, 1024), "#778899"),
                                     dict(colors=[f"#{index:06x}" for index in range(1024)]))
        self.assertEqual(interpolate.call_count, 1)
        self.assertEqual(interpolate.call_args.args[1].shape, (256,))

    def test_selected_renderer_and_detail_reach_pattern_generation(self):
        base = Image.new("RGB", (64, 64), "red")
        for pattern in ("modern", "legacy"):
            with patch("music2picture_v2.variants.render_cover", return_value=base) as modern, \
                 patch("music2picture_v2.variants.render_legacy", return_value=base) as legacy:
                result = render_variant("song.wav", None, None, style="custom", size=64,
                                        custom_cover_settings=dict(pattern=pattern, detail=100))
                self.assertEqual(result.size, (64, 64))
                if pattern == "modern":
                    legacy.assert_not_called()
                    self.assertEqual(modern.call_args.kwargs["detail"], 100)
                else:
                    modern.assert_not_called()
                    self.assertEqual(legacy.call_args.kwargs["patterns"], 2)
                    self.assertEqual(legacy.call_args.kwargs["detail"], 100)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_real_generation_saves_reproducible_settings_and_changes_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Im so sorry.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(22050)
                samples = [int(8000 * math.sin(2 * math.pi * 220 * i / 22050)) for i in range(11025)]
                audio.writeframes(struct.pack(f"<{len(samples)}h", *samples))
            original = source.read_bytes()
            images = []
            for pattern in ("modern", "legacy"):
                for detail in (0, 100):
                    target = root / f"{pattern}-{detail}.png"
                    settings = dict(pattern=pattern, detail=detail,
                                    colors=["#003344", "#4466aa", "#559988", "#ffcc66"])
                    music2picture.make_cover(source, target, size=192, seed=38, text_mode="title",
                                             style="custom", custom_cover_settings=settings)
                    with Image.open(target) as image:
                        images.append(image.tobytes())
                    profile = json.loads((root / ".sonicforge" / f"{target.stem}.profile.json").read_text(encoding="utf-8"))
                    self.assertEqual(profile["custom_cover_settings"], CustomCoverSettings.parse(settings).to_dict())
            self.assertEqual(len(set(images)), 4)
            self.assertEqual(source.read_bytes(), original)


class TitleWrappingTests(unittest.TestCase):
    @staticmethod
    def compose(title, size=1000, artist=""):
        engine = TypographyEngine()
        resolved = resolve_title(title, "stylized")
        engine.compose(Image.new("RGB", (size, size), "#553388"), resolved.selected, artist,
                       profile=SimpleNamespace(typography_style="artistic title", typography_locked=True,
                                               text_position="center"), title_treatment=resolved,
                       show_artist=bool(artist), placement_override="center")
        return engine.last_layout, resolved

    def test_im_so_sorry_uses_large_balanced_wrapping(self):
        for size in (192, 384, 1000):
            layout, resolved = self.compose("Im so sorry", size)
            self.assertGreaterEqual(layout["font_size"], size * .12)
            self.assertEqual(layout["line_count"], 2)
            self.assertEqual(" ".join(layout["display_lines"]), resolved.selected)

    def test_short_real_words_do_not_force_tiny_text(self):
        for title in ("Я", "Мы", "So", "Im", "Я и ты", "No More", "Я не могу забыть тебя"):
            with self.subTest(title=title):
                layout, resolved = self.compose(title)
                self.assertGreater(layout["font_size"], 95)
                self.assertEqual(" ".join(layout["display_lines"]), resolved.selected)
                left, top, right, bottom = layout["safe_area"]
                self.assertGreaterEqual(left, 0)
                self.assertGreaterEqual(top, 0)
                self.assertLessEqual(right, 1000)
                self.assertLessEqual(bottom, 1000)

    def test_artist_remains_secondary(self):
        layout, _ = self.compose("Im so sorry", artist="Imagine Dragons")
        self.assertGreater(layout["font_size"], 120)
        self.assertGreater(layout["title_artist_ratio"], 3)


if __name__ == "__main__":
    unittest.main()
