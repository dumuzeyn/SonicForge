from pathlib import Path
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class ShellIntegrationTests(unittest.TestCase):
    def test_icon_contains_small_and_large_transparent_sizes(self):
        with Image.open(ROOT / 'assets/sonic_forge_mark.ico') as icon:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes())
            for size in icon.ico.sizes():
                frame = icon.ico.getimage(size).convert('RGBA')
                self.assertEqual(frame.getchannel('A').getextrema(), (0, 255))

    def test_installer_registers_open_with_without_changing_defaults(self):
        script = (ROOT / 'packaging/SonicForge.iss').read_text(encoding='utf-8')
        self.assertIn('ChangesAssociations=yes', script)
        self.assertIn('OpenWithProgids', script)
        self.assertIn('SupportedTypes', script)
        self.assertNotIn('UserChoice', script)
        self.assertIn('IconFilename: "{app}\\_internal\\assets\\sonic_forge_mark.ico"', script)
        self.assertIn('""%1""', script)
        for extension in ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma'):
            self.assertIn('"' + extension + '"', script)

    def test_top_icon_bar_has_contrast_against_white(self):
        with Image.open(ROOT / 'assets/sonic_forge_mark.png') as icon:
            width, height = icon.size
            area = icon.crop((int(width * .60), int(height * .22), int(width * .95), int(height * .31))).convert('RGBA')
            pixels = [pixel for y in range(area.height) for x in range(area.width)
                      if (pixel := area.getpixel((x, y)))[3] >= 240]
            self.assertGreater(len(pixels), 100)
            def linear(value):
                value /= 255
                return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
            luminance = sum(.2126 * linear(r) + .7152 * linear(g) + .0722 * linear(b)
                            for r, g, b, _ in pixels) / len(pixels)
            self.assertGreater(1.05 / (luminance + .05), 3)

    def test_shortcut_refresh_is_target_scoped_and_preserves_pins(self):
        script = (ROOT / 'scripts/refresh_windows_shortcuts.ps1').read_text(encoding='utf-8')
        self.assertIn('$ValidApplications.ContainsKey($TargetPath)', script)
        self.assertIn('Copy-Item -LiteralPath $ShortcutFile.FullName', script)
        self.assertIn('SHChangeNotify', script)
        self.assertNotIn('Remove-Item', script)
        self.assertNotIn('Stop-Process', script)


if __name__ == '__main__':
    unittest.main()
