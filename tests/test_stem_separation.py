import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from audio_editor import Cancelled, read_waveform
from stem_separation import separate_clip
from test_audio_editor import make_tone


ROOT = Path(__file__).resolve().parents[1]
READY = (ROOT / 'build/stem-python/Scripts/python.exe').is_file() and (ROOT / 'build/stem-model/955717e8-8726e21a.th').is_file()


class StemBridgeTests(unittest.TestCase):
    def test_invalid_bounds_rejected_before_starting_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.wav'
            make_tone(source)
            for start, end in ((-1, 2), (2, 1), (0, float('nan'))):
                with self.assertRaises(ValueError):
                    separate_clip(source, start, end)

    @unittest.skipUnless(READY, 'Isolated separation runtime/model not prepared')
    def test_real_model_returns_four_timed_finite_waveforms_without_touching_original(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.wav'
            make_tone(source)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            progress = []
            paths = separate_clip(source, .5, 1.5, cache_root=Path(directory) / 'cache', progress=progress.append)
            self.assertEqual([p.stem for p in paths], ['vocals', 'drums', 'bass', 'other'])
            for path in paths:
                result = read_waveform(path)
                self.assertAlmostEqual(result.duration, 1, places=2)
                self.assertTrue(all(0 <= peak <= 1 for peak in result.peaks))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertEqual(progress[-1], 1)

    @unittest.skipUnless(READY, 'Isolated separation runtime/model not prepared')
    def test_cancel_removes_own_working_directory_and_never_touches_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.wav'
            make_tone(source)
            before = source.read_bytes()
            cancel = threading.Event()
            cancel.set()
            cache = Path(directory) / 'cache'
            with self.assertRaises(Cancelled):
                separate_clip(source, 0, 1, cancel=cancel, cache_root=cache)
            self.assertEqual(list(cache.iterdir()), [])
            self.assertEqual(source.read_bytes(), before)

    @unittest.skipUnless((ROOT / 'build/separator/SonicForgeSeparator/SonicForgeSeparator.exe').is_file(),
                         'Frozen separation worker not built')
    def test_frozen_worker_runs_offline_and_returns_two_components(self):
        helper = ROOT / 'build/separator/SonicForgeSeparator/SonicForgeSeparator.exe'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.wav'
            make_tone(source)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch('stem_separation.worker_command', return_value=[str(helper)]):
                paths = separate_clip(source, .5, 1.5, mode='two', cache_root=Path(directory) / 'cache')
            self.assertEqual([p.stem for p in paths], ['vocals', 'instrumental'])
            self.assertTrue(all(abs(read_waveform(path).duration - 1) < .01 for path in paths))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
