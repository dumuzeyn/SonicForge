from array import array
import errno
import hashlib
import math
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

from audio_editor import AudioSource, Cancelled, Timeline, read_waveform, render, run_ffmpeg


def make_tone(path, duration=2, hz=220):
    rate = 8000
    values = array("h", (int(3000 * math.sin(2 * math.pi * hz * n / rate)) for n in range(round(duration * rate))))
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(values.tobytes())


def samples(path):
    with wave.open(str(path), "rb") as audio:
        rate = audio.getframerate()
        channels = audio.getnchannels()
        # FFmpeg's mono-to-stereo conversion preserves total signal energy:
        # each stereo channel is -3 dB. Compare energy-equivalent mono levels.
        values = [v * math.sqrt(channels) for v in array("h", audio.readframes(audio.getnframes()))[::channels]]
        return values, rate


def rms(values):
    return math.sqrt(sum(v * v for v in values) / max(1, len(values)))


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.project = Timeline()
        self.source = AudioSource("song.wav", 10)
        self.clip = self.project.add(self.source)

    def test_split_is_contiguous_and_undo_redo_restore(self):
        right = self.project.split(self.clip.id, 4)
        left = self.project.get(self.clip.id)
        self.assertEqual((left.start, left.end, right.start, right.position, right.end), (0, 4, 4, 4, 10))
        self.project.undo()
        self.assertEqual(self.project.clips, [self.clip])
        self.project.redo()
        self.assertEqual(len(self.project.clips), 2)

    def test_trim_move_volume_and_fades(self):
        clip = self.project.update(self.clip.id, start=2, end=7, position=12, lane=7, gain=-6, fade_in=.5, fade_out=1)
        self.assertEqual(clip.duration, 5)
        self.assertEqual(self.project.duration, 17)
        self.assertEqual(clip.lane, 7)

    def test_invalid_changes_do_not_affect_project_or_history(self):
        for changes in (dict(start=10), dict(end=11), dict(position=-1), dict(lane=-1),
                        dict(gain=19), dict(fade_in=11), dict(end=float("nan"))):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.project.update(self.clip.id, **changes)
                self.assertEqual(self.project.clips, [self.clip])
                self.assertEqual(len(self.project._undo), 1)

    def test_delete_duplicate_mute_are_reversible(self):
        duplicate = self.project.duplicate(self.clip.id)
        self.assertEqual(duplicate.position, 10)
        self.project.delete(duplicate.id)
        self.project.undo()
        self.assertIn(duplicate, self.project.clips)
        self.project.toggle_mute(0)
        self.assertEqual(self.project.muted, {0})
        self.project.undo()
        self.assertEqual(self.project.muted, set())

    def test_same_lane_imports_follow_each_other(self):
        self.assertEqual(self.project.add(self.source).position, 10)
        self.assertEqual(self.project.add(self.source, lane=1).position, 0)

    def test_split_outside_clip_is_rejected(self):
        for position in (0, 10, 11, -.1):
            with self.assertRaises(ValueError):
                self.project.split(self.clip.id, position)

    def test_explicit_import_and_move_snap_past_occupied_intervals(self):
        second = self.project.add(self.source, position=2)
        self.assertEqual(second.position, 10)
        third = self.project.add(self.source, position=5)
        self.assertEqual(third.position, 20)
        moved = self.project.update(third.id, position=3)
        self.assertEqual(moved.position, 20)
        moved = self.project.update(third.id, lane=100, position=3)
        self.assertEqual((moved.lane, moved.position), (100, 3))

    def test_duplicate_uses_free_space_without_overlapping_next_clip(self):
        self.project.add(self.source)
        duplicate = self.project.duplicate(self.clip.id)
        self.assertEqual(duplicate.position, 20)

    def test_duration_extension_into_next_clip_is_rejected(self):
        self.project.update(self.clip.id, end=5)
        self.project.add(self.source, position=5)
        before = list(self.project.clips)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            self.project.update(self.clip.id, end=8)
        self.assertEqual(self.project.clips, before)

    def test_free_interval_before_later_clip_is_used(self):
        project = Timeline()
        project.add(self.source, position=20)
        short = project.add(AudioSource('short.wav', 3), position=4)
        self.assertEqual(short.position, 4)

    def test_draft_round_trip_and_peaks_are_not_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.sfproject"
            self.project.update(self.clip.id, gain=-4, position=2)
            self.project.toggle_mute(1)
            self.project.save(path)
            self.assertNotIn("peaks", path.read_text(encoding="utf-8"))
            with patch("audio_editor.read_waveform", return_value=self.source):
                loaded = Timeline.load(path)
            self.assertEqual(loaded.clips, self.project.clips)
            self.assertEqual(loaded.muted, {1})


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
class EditorRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.source_path = self.directory / "original.wav"
        make_tone(self.source_path)
        self.hash_before = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        self.source = read_waveform(self.source_path)
        self.project = Timeline()
        self.clip = self.project.add(self.source)

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source_path.read_bytes()).hexdigest(), self.hash_before)
        self.temp.cleanup()

    def test_waveform_is_real_and_bounded(self):
        self.assertAlmostEqual(self.source.duration, 2)
        self.assertLessEqual(len(self.source.peaks), 2400)
        self.assertGreater(max(self.source.peaks), .08)

    def test_render_trimmed_audio_with_correct_duration_and_gain(self):
        self.project.update(self.clip.id, start=.5, end=1.5, gain=-6)
        path = render(self.project, self.directory / "trim.wav")
        values, rate = samples(path)
        self.assertAlmostEqual(len(values) / rate, 1, places=2)
        self.assertAlmostEqual(rms(values) / (3000 / math.sqrt(2)), 10 ** (-6 / 20), delta=.04)

    def test_render_contains_timeline_silence_and_mix(self):
        self.project.update(self.clip.id, end=1, position=1)
        second = self.project.add(self.source, lane=1, position=1)
        self.project.update(second.id, end=1)
        values, rate = samples(render(self.project, self.directory / "mix.wav"))
        self.assertAlmostEqual(len(values) / rate, 2, places=2)
        self.assertLess(rms(values[:int(rate * .9)]), 1)
        self.assertGreater(rms(values[int(rate * 1.1):int(rate * 1.9)]), 3900)

    def test_muted_lane_is_not_in_render(self):
        second = self.project.add(self.source, lane=1, position=0)
        self.project.toggle_mute(1)
        values, rate = samples(render(self.project, self.directory / "mute.wav"))
        self.assertAlmostEqual(rms(values) / (3000 / math.sqrt(2)), 1, delta=.04)

    def test_fades_work_in_export_and_offset_preview(self):
        self.project.update(self.clip.id, fade_in=1, fade_out=1)
        values, rate = samples(render(self.project, self.directory / "fades.wav"))
        self.assertLess(rms(values[:int(rate * .1)]), 250)
        self.assertLess(rms(values[-int(rate * .1):]), 250)
        self.assertGreater(rms(values[int(rate * .9):int(rate * 1.1)]), 1800)
        partial, partial_rate = samples(render(self.project, self.directory / "partial.wav", start=1, length=.5))
        self.assertAlmostEqual(len(partial) / partial_rate, .5, places=2)
        self.assertGreater(rms(partial[:int(partial_rate * .1)]), 1800)

    def test_export_formats_mp3_and_m4a(self):
        for suffix in (".mp3", ".m4a"):
            path = render(self.project, self.directory / ("output" + suffix))
            self.assertGreater(path.stat().st_size, 1000)
            source = read_waveform(path)
            self.assertAlmostEqual(source.duration, 2, delta=.1)

    def test_cancellation_removes_incomplete_output(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            render(self.project, self.directory / "cancel.wav", cancel)
        self.assertFalse((self.directory / "cancel.wav").exists())
        self.assertEqual(list(self.directory.glob(".sonicforge-*")), [])

    def test_existing_file_and_original_cannot_be_overwritten(self):
        for path in (self.source_path, self.directory / "exists.wav"):
            if not path.exists():
                path.write_bytes(b"existing")
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                render(self.project, path)
            self.assertEqual(path.read_bytes(), before)

    def test_new_export_race_cannot_replace_target(self):
        target = self.directory / "race.wav"
        real_run = run_ffmpeg
        def race(args, cancel):
            real_run(args, cancel)
            target.write_bytes(b"concurrent file")
        with patch("audio_editor.run_ffmpeg", side_effect=race):
            with self.assertRaises(FileExistsError):
                render(self.project, target)
        self.assertEqual(target.read_bytes(), b"concurrent file")
        self.assertEqual(list(self.directory.glob(".sonicforge-*")), [])

    def test_export_without_hardlink_support_still_works(self):
        target = self.directory / "external.wav"
        with patch("audio_editor.os.link", side_effect=OSError(errno.ENOTSUP, "No hardlinks")):
            render(self.project, target)
        self.assertTrue(target.exists())
        self.assertGreater(target.stat().st_size, 1000)

    def test_source_changed_since_import_requires_reload(self):
        make_tone(self.source_path, duration=1)
        self.hash_before = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "changed"):
            render(self.project, self.directory / "changed.wav")

    def test_ffmpeg_is_windowless_and_cancelled_child_is_reaped(self):
        cancel = threading.Event()
        cancel.set()
        with patch("audio_editor.subprocess.Popen") as popen:
            popen.return_value.poll.return_value = None
            with self.assertRaises(Cancelled):
                run_ffmpeg(["-i", "test"], cancel)
            self.assertIn("creationflags", popen.call_args.kwargs)
            popen.return_value.kill.assert_called_once()
            popen.return_value.wait.assert_called_once()
