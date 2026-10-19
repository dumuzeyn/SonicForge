import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
import genre_classifier as gc
import music_metadata as metadata


class GenrePolicyTests(unittest.TestCase):
    def test_filename_never_establishes_an_acoustic_genre(self):
        for name in ('Classic Rock.mp3', 'Dopamine.mp3', 'Edited.mp3', 'Poppies.mp3', 'Nightcore.mp3'):
            self.assertIsNone(metadata.keyword_genre_from_name(name, metadata.DEFAULT_GENRES))
        self.assertEqual(gc.context_tags('Dopamine - edited - footsteps.mp3'), ())
        self.assertEqual(gc.context_tags('Anime_OST [Edit] Nightcore Slowed.mp3'),
                         ('Anime', 'OST', 'Edit', 'Nightcore', 'Slowed'))

    def test_no_first_allowed_genre_or_token_overlap_fallback(self):
        self.assertIsNone(metadata.choose_allowed_genre('Classical', ['Classic Rock', 'Pop']))
        self.assertIsNone(metadata.choose_allowed_genre('Techno', []))
        self.assertEqual(metadata.choose_allowed_genre('R&B', ['rnb']), 'rnb')

    def test_rock_and_classic_rock_are_separate_native_labels(self):
        genres, alternatives = gc.aggregate(np.array([[.7, .6]]), ['rock', 'classic rock'], ['Rock', 'Classic Rock', 'Classical'])
        self.assertEqual(genres, ('Rock', 'Classic Rock'))
        self.assertNotIn('Classical', [c.genre for c in alternatives])

    def test_electronic_subgenres_only_from_native_vocabulary(self):
        genres, _ = gc.aggregate(np.array([[.8, .7, .6]]), ['house', 'electro', 'electronic'],
                                 ['House', 'Electro', 'Electronic', 'Techno', 'Drum and Bass'])
        self.assertEqual(genres, ('House', 'Electro', 'Electronic'))
        self.assertEqual(gc.aggregate(np.array([[.9]]), ['electronic'], ['Techno'])[0], ())

    def test_mixed_styles_retain_evidence_from_multiple_patches(self):
        genres, _ = gc.aggregate(np.array([[.8, .05], [.75, .03], [.03, .8], [.04, .85]]),
                                 ['rock', 'electronic'])
        self.assertEqual(set(genres), {'Rock', 'Electronic'})

    def test_low_scores_and_one_outlier_abstain(self):
        self.assertEqual(gc.aggregate(np.array([[.19, .18]]), ['rock', 'pop'])[0], ())
        self.assertEqual(gc.aggregate(np.array([[.9], [0], [0], [0], [0]]), ['rock'])[0], ())

    def test_short_regions_are_unique_and_long_regions_are_bounded(self):
        self.assertEqual(gc.sample_regions(2), [(0, 2)])
        for duration in (10, 29, 1000, 10000):
            regions = gc.sample_regions(duration)
            self.assertLessEqual(len(regions), 5)
            self.assertLessEqual(sum(w for _, w in regions), 45)
            for (start, width), (next_start, _) in zip(regions, regions[1:]):
                self.assertLessEqual(start + width, next_start + 1e-6)

    def test_model_has_valid_provenance_and_reuses_session(self):
        folder = gc.model_directory()
        manifest = json.loads((folder / 'manifest.json').read_text())
        self.assertEqual(manifest['license'], 'ISC')
        self.assertEqual(hashlib.sha256((folder / 'msd_musicnn.onnx').read_bytes()).hexdigest(), manifest['sha256'])
        self.assertIs(gc.model_session()[0], gc.model_session()[0])
        self.assertTrue(set(gc.GENRE_LABELS).issubset({l.casefold() for l in manifest['labels']}))

    def test_frontend_is_finite_without_peak_normalization(self):
        audio = np.random.default_rng(1).normal(0, .05, 48000).astype(np.float32)
        mel = gc.log_mel(audio)
        self.assertEqual(mel.shape, (187, 96))
        self.assertTrue(np.isfinite(mel).all())
        self.assertGreater(float(mel.mean()), float(gc.log_mel(audio / 10).mean()))

    def test_decode_fragment_is_bounded(self):
        with self.assertRaises(ValueError):
            gc.decode_fragment('x.mp3', seconds=31)

    def test_missing_model_is_explicit_and_never_uses_filename(self):
        with patch.object(gc, 'duration_seconds', return_value=3), \
             patch.object(gc, 'decode_fragment', return_value=np.ones(48000, dtype=np.float32)*.01), \
             patch.object(gc, 'model_session', side_effect=FileNotFoundError('missing weights')):
            result = gc.classify_genre('House.mp3')
        self.assertFalse(result.genres)
        self.assertIn('unavailable:', result.reason)


class MetadataGenreTests(unittest.TestCase):
    def process(self, tags, **options):
        with patch.object(metadata, 'audio_files', return_value=[Path('song.mp3')]), \
             patch.object(metadata, 'read_all_metadata', return_value=tags), \
             patch.object(metadata, 'write_metadata') as write, \
             patch.object(gc, 'classify_genre', return_value=gc.GenreResult(reason='low_confidence_or_unsupported')) as classify:
            metadata.update_music_metadata('.', **options)
            return write.call_args, classify.call_count

    def test_old_user_tags_are_kept_without_loading_model(self):
        args, calls = self.process({'title': 'User title', 'genre': 'Anime; CustomTag'})
        self.assertEqual(args.args[1:3], ('User title', 'Anime; CustomTag'))
        self.assertEqual(calls, 0)

    def test_overwrite_abstention_preserves_existing_genre(self):
        args, calls = self.process({'genre': 'Classic Rock'}, overwrite_genre=True)
        self.assertEqual(args.args[2], 'Classic Rock')
        self.assertEqual(calls, 1)

    def test_explicit_manual_override_never_requires_model(self):
        args, calls = self.process({}, genre_override='Nightcore')
        self.assertEqual(args.args[2], 'Nightcore')
        self.assertEqual(calls, 0)

    def test_unknown_genre_is_not_written_as_none_string_or_empty_tag(self):
        args, _ = self.process({})
        self.assertIsNone(args.args[2])
        with patch.object(metadata, 'run') as run, patch.object(Path, 'replace'):
            metadata.write_metadata('song.mp3', 'Title', None)
        self.assertFalse(any(str(v).startswith('genre=') for v in run.call_args.args[0]))

    def test_automatic_multilabel_and_progress_are_forwarded(self):
        result = gc.GenreResult(('Rock', 'Classic Rock'))
        progress = []
        with patch.object(metadata, 'audio_files', return_value=[Path('song.mp3')]), \
             patch.object(metadata, 'read_all_metadata', return_value={}), \
             patch.object(metadata, 'write_metadata') as write, \
             patch.object(gc, 'classify_genre', return_value=result):
            metadata.update_music_metadata('.', genre_progress=lambda p, r: progress.append(r))
        self.assertEqual(write.call_args.args[2], 'Rock; Classic Rock')
        self.assertEqual(progress, [result])

    def test_cancellation_prevents_metadata_write(self):
        event = threading.Event()
        with patch.object(metadata, 'audio_files', return_value=[Path('song.mp3')]), \
             patch.object(metadata, 'read_all_metadata', return_value={}), \
             patch.object(metadata, 'write_metadata') as write, \
             patch.object(gc, 'classify_genre', return_value=gc.GenreResult()):
            with self.assertRaises(InterruptedError):
                metadata.update_music_metadata('.', cancel_event=event,
                    genre_progress=lambda p, r: event.set())
        write.assert_not_called()

    def test_metadata_batch_continues_after_remux_error(self):
        with patch.object(metadata, 'audio_files', return_value=[Path('bad.mp3'), Path('good.mp3')]), \
             patch.object(metadata, 'read_all_metadata', return_value={'genre': 'User genre'}), \
             patch.object(metadata, 'write_metadata', side_effect=[subprocess.CalledProcessError(1, 'ffmpeg'), None]) as write:
            metadata.update_music_metadata('.')
        self.assertEqual(write.call_count, 2)

    def test_failed_remux_removes_temporary_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'song.mp3'
            path.write_bytes(b'original')
            temporary = path.with_name('song.metadata_tmp.mp3')
            def failure(command):
                temporary.write_bytes(b'partial result')
                raise subprocess.CalledProcessError(1, command)
            with patch.object(metadata, 'run', side_effect=failure):
                with self.assertRaises(subprocess.CalledProcessError):
                    metadata.write_metadata(path, 'Title', 'Rock')
            self.assertEqual(path.read_bytes(), b'original')
            self.assertFalse(temporary.exists())


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class DecoderGenreTests(unittest.TestCase):
    def test_silence_and_short_tracks_do_not_load_neural_model(self):
        with tempfile.TemporaryDirectory() as folder:
            for seconds in (.2, 2, 20):
                path = Path(folder) / f'silence_{seconds}.wav'
                subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                                'anullsrc=r=16000:cl=mono', '-t', str(seconds), str(path)], check=True)
                with patch.object(gc, 'model_session') as session:
                    result = gc.classify_genre(path)
                self.assertEqual(result.reason, 'silent_or_too_short')
                session.assert_not_called()

    def test_real_decoding_all_existing_formats(self):
        codecs = {'.mp3': 'libmp3lame', '.flac': 'flac', '.wav': 'pcm_s16le', '.m4a': 'aac',
                  '.aac': 'aac', '.ogg': 'libvorbis', '.opus': 'libopus', '.wma': 'wmav2'}
        with tempfile.TemporaryDirectory() as folder:
            for extension, codec in codecs.items():
                with self.subTest(extension=extension):
                    path = Path(folder) / ('format' + extension)
                    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=220:duration=4', '-c:a', codec, str(path)], check=True)
                    audio = metadata.read_audio(path, sample_rate=16000, seconds=2)
                    self.assertLessEqual(audio.size, 32000)
                    self.assertGreater(audio.size, 30000)
                    self.assertLess(float(np.max(np.abs(audio))), .3)
                    self.assertGreater(gc.duration_seconds(path), 3.9)

    def test_decode_error_does_not_abort_following_batch_tracks(self):
        with tempfile.TemporaryDirectory() as folder:
            broken, silent = Path(folder)/'broken.mp3', Path(folder)/'silent.wav'
            broken.write_bytes(b'corrupt audio')
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'anullsrc=r=16000:cl=mono', '-t', '2', str(silent)], check=True)
            results = list(gc.classify_batch([broken, silent]))
            self.assertIn('unavailable:', results[0][1].reason)
            self.assertEqual(results[1][1].reason, 'silent_or_too_short')

    def test_cancel_interrupts_live_subprocess_and_batch(self):
        event = threading.Event()
        timer = threading.Timer(.15, event.set)
        timer.start()
        started = time.monotonic()
        try:
            with self.assertRaises(InterruptedError):
                gc.capture([sys.executable, '-c', 'import time; time.sleep(20)'], event)
            self.assertLess(time.monotonic()-started, 3)
            with self.assertRaises(InterruptedError):
                list(gc.classify_batch(['song.wav'], cancel_event=event))
        finally:
            timer.cancel()


if __name__ == '__main__':
    unittest.main()
