import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from lyrics_engine.language_identifier import model_files
from lyrics_engine.providers import FasterWhisperProvider


class WindowlessDownloadTests(unittest.TestCase):
    def assert_windowless_progress(self, progress_class):
        # PyInstaller's windowed EXE has neither console stream. Exercise actual
        # progress construction and iteration, not only the download mock.
        with patch.object(sys, "stdout", None), patch.object(sys, "stderr", None):
            with progress_class(total=2, disable=False) as progress:
                progress.update(1)
                progress.update(1)
            self.assertEqual(list(progress_class(range(2))), [0, 1])

    def test_native_model_download_without_console(self):
        with patch("huggingface_hub.snapshot_download", return_value="cached-model") as download, \
             patch("faster_whisper.WhisperModel"):
            FasterWhisperProvider()._get_native_model("ka")
        self.assert_windowless_progress(download.call_args.kwargs["tqdm_class"])

    def test_language_identifier_download_without_console(self):
        with patch("huggingface_hub.hf_hub_download", return_value="cached-file") as download, \
             patch.object(sys, "frozen", False, create=True):
            self.assertEqual(model_files(), (Path("cached-file"), Path("cached-file")))
        self.assertEqual(download.call_count, 2)
        for call in download.call_args_list:
            self.assert_windowless_progress(call.kwargs["tqdm_class"])
