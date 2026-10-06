from array import array
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

from audio_editor import AudioSource, Cancelled, Clip, Timeline, read_waveform, remove_audio_selection, run_ffmpeg
from test_audio_editor import samples


class AudioCutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'song.wav'
        with wave.open(str(self.path), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(array('h', [8000] * 8000 + [24000] * 8000 + [-8000] * 8000).tobytes())
        self.source = read_waveform(self.path)
        self.clip = Clip('clip', str(self.path), 0, 0, 3, position=5)
        self.cache = self.root / 'cache'
        self.before = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def check_unchanged(self):
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), self.before)

    def test_removes_middle_marker_closes_gap_and_smooths_discontinuity(self):
        result = remove_audio_selection(self.source, self.clip, 6, 7, cache_root=self.cache)
        self.assertAlmostEqual(result.duration, 1.96, places=2)
        decoded = self.root / 'decoded.wav'
        run_ffmpeg(['-i', result.path, '-c:a', 'pcm_s16le', str(decoded)])
        values, rate = samples(decoded)
        self.assertAlmostEqual(sum(values[:200]) / 200, 8000, delta=15)
        self.assertAlmostEqual(sum(values[-200:]) / 200, -8000, delta=15)
        self.assertLess(max(abs(v) for v in values), 8100)
        join = values[int(.95 * rate):int(1.01 * rate)]
        self.assertLess(max(abs(b - a) for a, b in zip(join, join[1:])), 100)
        self.assertTrue(Path(result.path).is_file())
        self.check_unchanged()

    def test_edge_removal_does_not_insert_gap_or_extra_crossfade(self):
        for start, end in ((5, 6), (7, 8)):
            result = remove_audio_selection(self.source, self.clip, start, end, cache_root=self.cache)
            self.assertAlmostEqual(result.duration, 2, places=2)
        self.check_unchanged()

    def test_clip_source_offsets_and_short_remainders_are_respected(self):
        clip = Clip('clip', str(self.path), 0, .2, 2.8, position=5)
        result = remove_audio_selection(self.source, clip, 5.5, 6.5, cache_root=self.cache)
        self.assertAlmostEqual(result.duration, 1.56, places=2)
        result = remove_audio_selection(self.source, self.clip, 5.02, 7, cache_root=self.cache)
        self.assertAlmostEqual(result.duration, 1.01, places=2)
        self.check_unchanged()

    def test_cancel_and_source_change_do_not_commit_edits(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            remove_audio_selection(self.source, self.clip, 6, 7, cancel, self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])
        changed = AudioSource(self.source.path, 3, stamp=(0, 0))
        with self.assertRaises(ValueError):
            remove_audio_selection(changed, self.clip, 6, 7, cache_root=self.cache)
        self.check_unchanged()

    def test_replace_audio_preserves_controls_and_is_one_undoable_edit(self):
        project = Timeline()
        clip = project.add(self.source, lane=3, position=5)
        clip = project.update(clip.id, gain=-6, fade_in=.5, fade_out=.3)
        other = project.add(self.source, lane=4, position=5)
        result = remove_audio_selection(self.source, clip, 6, 7, cache_root=self.cache)
        before = project._snapshot()
        edited = project.replace_audio(clip.id, result)
        self.assertEqual((edited.lane, edited.position, edited.gain, edited.fade_in, edited.fade_out), (3, 5, -6, .5, .3))
        self.assertEqual(project.get(other.id), other)
        project.undo()
        self.assertEqual(project._snapshot(), before)
        project.redo()
        self.assertEqual(project.get(clip.id), edited)
        draft = self.root / 'draft.sfproject'
        project.save(draft)
        self.assertEqual(Timeline.load(draft).clips, project.clips)
        self.check_unchanged()

    def test_invalid_empty_full_and_nonfinite_ranges_rejected(self):
        for a, b in ((6, 6), (7, 6), (0, 1), (5, 8), (float('nan'), 7)):
            with self.subTest(a=a, b=b):
                with self.assertRaises(ValueError):
                    remove_audio_selection(self.source, self.clip, a, b, cache_root=self.cache)
        self.check_unchanged()
