import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import music2picture


class CoverLyricsSwitchTests(unittest.TestCase):
    def test_disabled_lyrics_skip_editor_tags_and_sidecars(self):
        self.check_analysis_inputs(False, "")

    def test_enabled_lyrics_enter_analysis_only_once(self):
        self.check_analysis_inputs(True, "Edited test lyrics")

    def check_analysis_inputs(self, enabled, expected):
        tags = {"title": "Test title", "artist": "Test artist", "lyrics": "Old text",
                "unsyncedlyrics": "Old text", "lyrics_language": "ru", "lyrics_alphabet": "ru"}
        bundle = SimpleNamespace(visual_dna=None, visual_plan=None, language="en")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "song.mp3"
            audio.touch()
            with patch("music2picture.require_ffmpeg"), \
                 patch("music_metadata.read_all_metadata", return_value=tags), \
                 patch("lyrics_engine.LyricsService.resolve_for_cover", return_value="Edited test lyrics") as resolve, \
                 patch.object(music2picture.DEFAULT_PIPELINE, "analyse", return_value=bundle) as analyse, \
                 patch("music2picture.render_variant", return_value=Image.new("RGB", (16, 16))):
                result = music2picture.make_cover(audio, root / "cover.png", preview=True,
                                                 lyrics_text="Edited test lyrics", use_lyrics_for_cover=enabled)
            self.assertTrue(result.is_file())
            self.assertEqual(analyse.call_args.kwargs["lyrics"], expected)
            self.assertEqual(analyse.call_args.kwargs["metadata"],
                             {"title": "Test title", "artist": "Test artist"})
            if enabled:
                resolve.assert_called_once_with(audio.resolve(), supplied_text="Edited test lyrics")
            else:
                resolve.assert_not_called()

    def test_batch_forwards_disabled_switch_and_ignores_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "song.mp3"
            audio.touch()
            with patch("music2picture.audio_files", return_value=[audio.resolve()]), \
                 patch("music2picture.make_cover", return_value=root / "cover.png") as render:
                music2picture.make_covers(audio, root / "out", lyrics_text="Editor test text",
                                          lyrics_lookup={"song": "Sidecar test text"}, use_lyrics_for_cover=False)
            self.assertIs(render.call_args.kwargs["use_lyrics_for_cover"], False)
            self.assertEqual(render.call_args.kwargs["lyrics_text"], "")
