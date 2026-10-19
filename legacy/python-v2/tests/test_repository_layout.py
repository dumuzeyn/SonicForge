"""Keep source and frozen resource paths valid when reorganizing the repository."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from cover_engine import typography
from easy_music_process import normalize_music_file
from music_polisher_gui import resource_path
from stem_separation import worker_command

ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_runtime_sources_and_build_files_are_outside_root(self):
        self.assertEqual(list(ROOT.glob('*.py')), [])
        self.assertEqual(list(ROOT.glob('*.spec')), [])
        self.assertEqual(list(ROOT.glob('*.ps1')), [])
        for path in ('src/music_polisher_gui.py', 'src/Normalize-Music.py',
                     'requirements/runtime.txt', 'requirements/development.txt',
                     'scripts/build_windows.ps1', 'scripts/build_stems.ps1',
                     'packaging/SonicForge.spec', 'packaging/SonicForgeSeparator.spec'):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_source_icon_fonts_and_dynamic_audio_module_resolve(self):
        self.assertEqual(resource_path('assets/sonic_forge_mark.ico'), ROOT / 'assets/sonic_forge_mark.ico')
        self.assertEqual(typography.FONT_ROOT, ROOT / 'assets/fonts')
        self.assertTrue(Path(typography.NOTO_SANS).is_file())
        self.assertEqual(Path(normalize_music_file.__file__), ROOT / 'src/Normalize-Music.py')

    def test_frozen_resources_use_the_bundle_instead_of_source_directory(self):
        with patch.object(sys, '_MEIPASS', str(ROOT / 'build/mock-bundle'), create=True):
            self.assertEqual(resource_path('assets/icon.ico'), ROOT / 'build/mock-bundle/assets/icon.ico')

    def test_source_worker_uses_repository_build_and_script_directories(self):
        with patch('stem_separation.Path.is_file', return_value=True):
            command = worker_command()
        self.assertEqual(Path(command[0]), ROOT / 'build/stem-python/Scripts/python.exe')
        self.assertEqual(Path(command[1]), ROOT / 'scripts/stem_worker.py')
        self.assertEqual(Path(command[3]), ROOT / 'build/stem-model')
