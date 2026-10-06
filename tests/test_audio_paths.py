import tempfile
import unittest
from pathlib import Path

from audio_paths import default_output_path, find_audio_files


class AudioPathsTests(unittest.TestCase):
    def test_default_output_is_sibling_for_file_and_folder(self):
        base = Path(tempfile.gettempdir()) / "Music"
        self.assertEqual(default_output_path(base / "Album"), base / "SonicForgeProgect")
        self.assertEqual(default_output_path(base / "song.mp3"), base / "SonicForgeProgect")

    def test_discovery_prunes_generated_projects_and_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("Album/original.MP3", "second.wav", "notes.txt",
                             "SonicForgeProgect/Album/original.mp3",
                             "Album/sonicforgeprogect/nested.mp3",
                             "musicpolisher_pending/processed/song.mp3"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            extensions = {".mp3", ".wav"}
            self.assertEqual(find_audio_files(root, extensions),
                             [root / "Album/original.MP3", root / "second.wav"])
            # Explicitly selecting a previously processed project still works.
            project = root / "SonicForgeProgect"
            self.assertEqual(find_audio_files(project, extensions), [project / "Album/original.mp3"])
            self.assertEqual(find_audio_files(root / "missing", extensions), [])
            self.assertEqual(find_audio_files(root / "notes.txt", extensions), [])

    def test_all_processing_stages_use_the_same_discovery(self):
        import easy_music_process
        import music_metadata
        from music2picture_v2 import batch, legacy_music2picture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.mp3"
            original.touch()
            project = root / "SonicForgeProgect"
            project.mkdir()
            (project / "processed.mp3").touch()
            for discover in (music_metadata.audio_files, batch.audio_files,
                             legacy_music2picture.audio_files,
                             easy_music_process.normalize_music_file.audio_files):
                with self.subTest(stage=discover.__module__):
                    self.assertEqual(discover(root), [original])
