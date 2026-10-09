import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cover_preferences import load_custom_cover_settings, preference_path, save_custom_cover_settings
from music2picture_v2.custom_style import CustomCoverSettings


class CoverPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'preferences' / 'custom_cover.json'
        self.path_patch = patch('cover_preferences.preference_path', return_value=self.path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_complete_large_palette_is_saved_and_restored(self):
        settings = dict(pattern='legacy', colors=[f'#{i:06x}' for i in range(1025)],
                        positions=[(i / 1024) ** 2 for i in range(1025)],
                        detail=83, contrast=128, saturation=74, softness=16)
        expected = CustomCoverSettings.parse(settings).to_dict()
        self.assertEqual(save_custom_cover_settings(settings), expected)
        self.assertEqual(load_custom_cover_settings(), expected)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), expected)
        self.assertFalse(list(self.path.parent.glob('.custom-cover-*')))

    def test_missing_or_corrupt_preferences_do_not_block_startup(self):
        self.assertIsNone(load_custom_cover_settings())
        self.path.parent.mkdir()
        for data in (b'', b'{partial', b'\xff', b'[]', b'{"colors":[]}',
                     b'{"positions":[0,2]}', b'{"detail":NaN}', b'{"execute":"anything"}'):
            with self.subTest(data=data):
                self.path.write_bytes(data)
                self.assertIsNone(load_custom_cover_settings())
                self.assertEqual(self.path.read_bytes(), data)

    def test_old_two_color_preferences_are_compatible(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(dict(color_low='#112233', color_high='#ddeeff', detail=75)))
        settings = load_custom_cover_settings()
        self.assertEqual(settings['colors'], ['#112233', '#ddeeff'])
        self.assertEqual(settings['positions'], [0, 1])
        self.assertEqual(settings['detail'], 75)

    def test_invalid_edits_do_not_overwrite_last_saved_settings(self):
        save_custom_cover_settings(dict(detail=75))
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            save_custom_cover_settings(dict(colors=['not a color']))
        self.assertEqual(self.path.read_bytes(), original)

    def test_failed_atomic_save_keeps_previous_settings_and_cleans_temporary(self):
        save_custom_cover_settings(dict(detail=75))
        original = self.path.read_bytes()
        with patch.object(Path, 'replace', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                save_custom_cover_settings(dict(detail=10))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.path.parent.glob('.custom-cover-*')))

    def test_preference_size_limit_is_enforced_before_replacing_file(self):
        save_custom_cover_settings(dict(detail=75))
        original = self.path.read_bytes()
        with patch('cover_preferences.MAX_PREFERENCE_BYTES', 10):
            self.assertIsNone(load_custom_cover_settings())
            with self.assertRaises(ValueError):
                save_custom_cover_settings(dict(detail=10))
        self.assertEqual(self.path.read_bytes(), original)

    def test_preferences_are_outside_program_and_project_directories(self):
        with patch.dict('os.environ', {'LOCALAPPDATA': str(Path(self.directory.name) / 'user-data')}):
            self.assertEqual(preference_path(), Path(self.directory.name) / 'user-data/SonicForge/custom_cover.json')


if __name__ == '__main__':
    unittest.main()
