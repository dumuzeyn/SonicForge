import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageChops
from PIL import ImageFont

import music2picture
from cover_engine.typography import NOTO_SANS, TypographyEngine
from music2picture_v2 import legacy_music2picture
from music2picture_v2.variants import STYLES, render_variant


class CoverVariantTests(unittest.TestCase):
    @staticmethod
    def _tone(path):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            samples = [int(9000 * math.sin(2 * math.pi * 220 * i / 22050)) for i in range(11025)]
            audio.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    def test_all_five_styles_keep_the_requested_pattern_and_color_source(self):
        width = 64
        x = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (width, 1))
        y = x.T
        current = Image.fromarray(np.stack((x, x // 2, x // 4), axis=-1), "RGB")
        original = Image.fromarray(np.stack((y // 4, y // 2, y), axis=-1), "RGB")
        with patch("music2picture_v2.variants.render_cover", return_value=current), patch(
            "music2picture_v2.variants.render_legacy", return_value=original
        ):
            images = {
                style: render_variant("song.wav", None, None, style=style, size=width)
                for style in STYLES
            }
        self.assertEqual(images["current"].tobytes(), current.tobytes())
        self.assertEqual(images["legacy"].tobytes(), original.tobytes())
        self.assertEqual(images["blend"].tobytes(), Image.blend(current, original, 0.5).tobytes())
        current_colored = np.asarray(images["current_legacy_colors"].convert("L"), dtype=np.float32)
        original_colored = np.asarray(images["legacy_current_colors"].convert("L"), dtype=np.float32)
        self.assertGreater(float(current_colored[:, -1].mean() - current_colored[:, 0].mean()), 25)
        self.assertGreater(float(original_colored[-1, :].mean() - original_colored[0, :].mean()), 25)
        self.assertGreater(float(np.asarray(images["current_legacy_colors"])[..., 2].mean()),
                           float(np.asarray(images["current_legacy_colors"])[..., 0].mean()))
        self.assertGreater(float(np.asarray(images["legacy_current_colors"])[..., 0].mean()),
                           float(np.asarray(images["legacy_current_colors"])[..., 2].mean()))

    def test_title_weight_is_between_regular_and_bold(self):
        text = "Мало тебя"
        medium = TypographyEngine._font(96, (NOTO_SANS,), text)
        regular = ImageFont.truetype(NOTO_SANS, 96)
        regular.set_variation_by_axes([400, 100])
        bold = ImageFont.truetype(NOTO_SANS, 96)
        bold.set_variation_by_axes([700, 100])
        self.assertLess(sum(regular.getmask(text)), sum(medium.getmask(text)))
        self.assertLess(sum(medium.getmask(text)), sum(bold.getmask(text)))

    def test_historical_ffmpeg_never_opens_a_console(self):
        with patch.object(legacy_music2picture.subprocess, "check_output", return_value=np.ones(16, dtype=np.float32).tobytes()) as decode:
            legacy_music2picture.read_audio("song.mp3")
        if sys.platform == "win32":
            self.assertEqual(decode.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required by the historical renderer")
    def test_fifth_style_cleans_historical_artwork_and_exports_music_lettering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Tone.wav"
            self._tone(source)
            expected = root / "original.png"
            actual = root / "variant.png"
            default_style = root / "default_style.png"
            legacy_music2picture.make_cover(source, expected, size=192, seed=7, center_title=False)
            music2picture.make_cover(
                source, actual, size=192, seed=7, style="legacy", text_mode="none",
            )
            music2picture.make_cover(source, default_style, size=192, seed=7,
                                     style="legacy", text_mode="title")
            with Image.open(expected) as reference, Image.open(actual) as result:
                self.assertIsNotNone(ImageChops.difference(reference.convert("RGB"), result.convert("RGB")).getbbox())
            with Image.open(actual) as reference, Image.open(default_style) as result:
                bounds = ImageChops.difference(reference.convert("RGB"), result.convert("RGB")).getbbox()
                self.assertIsNotNone(bounds)
                self.assertGreaterEqual(bounds[0], 0)
                self.assertGreaterEqual(bounds[1], 0)
                self.assertLessEqual(bounds[2], 192)
                self.assertLessEqual(bounds[3], 192)
            titled_profile = json.loads((root / ".sonicforge" / "default_style.profile.json").read_text(encoding="utf-8"))
            self.assertEqual(titled_profile["typography"]["version"], "music-lettering-v3")
            self.assertGreaterEqual(titled_profile["typography"]["contrast_ratio"], 4.5)
            profile = json.loads((root / ".sonicforge" / "variant.profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["legacy_commit"], "342013aaa8bdb4cb86c8c14fec0acb038e50b5ca")
            self.assertEqual(profile['generator_version'], 'classic-crisp-v2')

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for cover analysis")
    def test_three_hybrids_render_from_real_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Tone.wav"
            self._tone(source)
            images = []
            for style in ("current_legacy_colors", "blend", "legacy_current_colors"):
                target = root / f"{style}.png"
                music2picture.make_cover(
                    source, target, size=192, seed=7,
                    style=style, text_mode="none",
                )
                with Image.open(target) as image:
                    self.assertEqual(image.size, (192, 192))
                    images.append(image.tobytes())
            self.assertEqual(len(set(images)), 3)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for cover analysis")
    def test_quick_preview_keeps_only_the_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Tone.wav"
            target = root / "preview.png"
            self._tone(source)
            with patch("music2picture.DescriptionStore.put", side_effect=AssertionError("unexpected write")):
                music2picture.make_cover(source, target, size=384, seed=7, preview=True)
            with Image.open(target) as image:
                self.assertEqual(image.size, (384, 384))
            self.assertFalse((root / ".sonicforge").exists())

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for cover rendering")
    def test_music_titles_are_baked_into_all_styles_and_stay_inside_the_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Tone.wav"
            self._tone(source)
            for style in STYLES:
                bare = root / f"{style}_bare.png"
                titled = root / f"{style}_titled.png"
                music2picture.make_cover(source, bare, size=192, seed=7, style=style, text_mode="none", preview=True)
                music2picture.make_cover(source, titled, size=192, seed=7, style=style, text_mode="title", preview=True)
                with Image.open(bare) as base, Image.open(titled) as label:
                    bounds = ImageChops.difference(base.convert("RGB"), label.convert("RGB")).getbbox()
                self.assertIsNotNone(bounds, style)
                self.assertGreaterEqual(bounds[0], 0, style)
                self.assertGreaterEqual(bounds[1], 0, style)
                self.assertLessEqual(bounds[2], 192, style)
                self.assertLessEqual(bounds[3], 192, style)


if __name__ == "__main__":
    unittest.main()
