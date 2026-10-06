import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image
import startup_splash
from startup_splash import TransparentSplash, premultiply_bgra

ROOT = Path(__file__).resolve().parents[1]


class StartupSplashTests(unittest.TestCase):
    def test_premultiplied_pixels_have_no_white_or_magenta_matte(self):
        data = bytes((255, 100, 50, 0, 200, 100, 50, 128, 20, 40, 80, 255))
        self.assertEqual(premultiply_bgra(data), bytes((0, 0, 0, 0, 100, 50, 25, 128, 20, 40, 80, 255)))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows layered window')
    def test_real_window_has_per_pixel_alpha_matches_brand_and_closes_cleanly(self):
        splash = TransparentSplash(ROOT / 'assets/sonic_forge_mark.ico')
        splash.start()
        try:
            self.assertIsNone(splash.error)
            self.assertTrue(splash.hwnd)
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
            style = user32.GetWindowLongW(splash.hwnd, -20)
            self.assertTrue(style & 0x00080000)  # WS_EX_LAYERED
            self.assertTrue(style & 0x00000080)  # No splash taskbar entry
            alphas = splash.pixels[3::4]
            self.assertEqual((min(alphas), max(alphas)), (0, 255))
            self.assertGreater(len(set(alphas)), 100)
            with Image.open(splash.icon_path) as icon:
                artwork = icon.ico.getimage((256, 256)).convert('RGBA')
                expected = premultiply_bgra(artwork.tobytes('raw', 'BGRA'))
            self.assertEqual(splash.pixels, expected)
        finally:
            splash.close()
        self.assertFalse(splash.thread.is_alive())
        self.assertIsNone(splash.hwnd)

    def test_disabled_loading_screen_does_not_create_a_window(self):
        with patch.object(startup_splash.Path, 'exists', return_value=True), \
                patch.object(startup_splash, 'TransparentSplash') as create, \
                patch.object(startup_splash, '_splash', None), \
                patch.dict(os.environ, {'LOCALAPPDATA': 'C:/test-data'}):
            startup_splash.show_splash()
            create.assert_not_called()

    def test_close_without_splash_is_safe(self):
        with patch.object(startup_splash, '_splash', None):
            startup_splash.close_splash()
