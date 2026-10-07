from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import os
from unittest.mock import patch
import wave

import numpy as np

from lyrics_engine.audio import decode_song_audio
from lyrics_engine.isolated import IsolatedLyricsProvider
from lyrics_engine.models import LyricsResult
from lyrics_engine.providers import FasterWhisperProvider
from lyrics_engine.service import LyricsService
from test_lyrics_verification import segment
from lyrics_engine.verification import verified_segments

FAKE_WORKER = """
import json, os, sys, time
for line in sys.stdin:
    request = json.loads(line)
    mode = request.get('language')
    if mode == 'crash':
        os._exit(37)
    if mode == 'invalid':
        print('invalid JSON', flush=True)
        continue
    if mode == 'wait':
        print(json.dumps(dict(event='progress', id=request['id'], stage='transcribing')), flush=True)
        time.sleep(30)
    result = dict(text='A synthetic practice line', segments=[], source=str(os.getpid()))
    print(json.dumps(dict(event='result', id=request['id'], result=result)), flush=True)
"""


class IsolatedRecognitionTests(unittest.TestCase):
    def setUp(self):
        logs = tempfile.TemporaryDirectory(prefix='sonicforge-test-logs-')
        self.addCleanup(logs.cleanup)
        environment = patch.dict(os.environ, LOCALAPPDATA=logs.name)
        environment.start()
        self.addCleanup(environment.stop)
        self.provider = IsolatedLyricsProvider()
        self.addCleanup(self.provider.close)
        command = patch('lyrics_engine.isolated.worker_command', return_value=[sys.executable, '-u', '-c', FAKE_WORKER])
        command.start()
        self.addCleanup(command.stop)

    def test_worker_is_reused_and_165_files_survive_one_native_crash(self):
        successes, failures, workers = 0, 0, set()
        for index in range(165):
            try:
                result = self.provider.transcribe('test.wav', language='crash' if index == 80 else 'en')
                successes += 1
                workers.add(result.source)
            except RuntimeError:
                failures += 1
        self.assertEqual((successes, failures), (164, 1))
        self.assertGreaterEqual(len(workers), 9)
        self.assertLessEqual(len(workers), 11)

    def test_native_fault_does_not_break_next_request(self):
        self.assertTrue(self.provider.transcribe('test.wav').text)
        with self.assertRaises(RuntimeError):
            self.provider.transcribe('test.wav', language='crash')
        self.assertTrue(self.provider.transcribe('test.wav').text)

    def test_invalid_protocol_is_contained(self):
        with self.assertRaises(RuntimeError):
            self.provider.transcribe('test.wav', language='invalid')
        self.assertIsNone(self.provider._process)

    def test_cancellation_stops_only_our_worker_promptly(self):
        event = threading.Event()
        timer = threading.Timer(.2, event.set)
        timer.start()
        self.addCleanup(timer.cancel)
        started = time.monotonic()
        with self.assertRaises(InterruptedError):
            self.provider.transcribe('test.wav', language='wait', cancel_event=event)
        self.assertLess(time.monotonic() - started, 4)
        self.assertIsNone(self.provider._process)

    def test_source_default_uses_isolation_without_loading_a_model(self):
        service = LyricsService()
        self.assertIsInstance(service.provider, IsolatedLyricsProvider)
        self.assertIsNone(service.provider._process)


class RecognitionEfficiencyTests(unittest.TestCase):
    def test_digital_silence_does_not_load_the_recognition_model(self):
        provider = FasterWhisperProvider()
        with patch.object(provider, 'available', return_value=True), \
             patch.object(provider, '_get_model') as model, \
             patch('lyrics_engine.providers.decode_song_audio', return_value=np.zeros(16000, dtype=np.float32)):
            result = provider.transcribe('silent.wav')
        self.assertTrue(result.instrumental)
        self.assertFalse(result.text)
        model.assert_not_called()

    def test_decode_is_bounded_and_original_wave_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original.wav'
            with wave.open(str(path), 'wb') as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b'\0\0' * 8000 * 2)
            before = path.read_bytes()
            decoded = decode_song_audio(path)
            self.assertEqual(decoded.shape, (16000,))
            self.assertEqual(decoded.dtype, np.float32)
            self.assertEqual(path.read_bytes(), before)
            with patch('lyrics_engine.audio.MAX_SECONDS', .5):
                with self.assertRaises(ValueError):
                    decode_song_audio(path)

    def test_recheck_uses_a_short_array_and_restores_global_word_times(self):
        original = segment('A synthetic practice line', start=40, end=45, probabilities=[.4, .9, .9, .9])
        corrected = segment('A synthetic practice line', start=5, end=10)
        from unittest.mock import Mock
        model = Mock()
        model.transcribe.return_value = (iter([corrected]), None)
        waveform = np.zeros(16000 * 180, dtype=np.float32)
        result = list(verified_segments(model, waveform, [original], {}, audio_duration=180))
        self.assertLessEqual(len(model.transcribe.call_args.args[0]), 16000 * 30)
        self.assertEqual(corrected.start, 5)  # Original decoder object is untouched.
        self.assertEqual(result[0].start, 40)

    def test_implausible_loop_is_replaced_by_acoustic_lines_not_a_dictionary(self):
        from unittest.mock import Mock
        bad = segment('A ' * 300, start=30, end=40)
        real = segment('A synthetic practice line', start=3, end=10)
        model = Mock()
        model.transcribe.return_value = (iter([real]), None)
        waveform = np.zeros(16000 * 80, dtype=np.float32)
        result = list(verified_segments(model, waveform, [bad], {},
                                       is_implausible=lambda s: len(s.text) > 100))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, real.text)
        self.assertEqual(result[0].start, 30)

    def test_empty_singing_gets_one_controlled_retry(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        provider = FasterWhisperProvider()
        model = Mock()
        raw = SimpleNamespace(start=3, end=6, text='A synthetic practice line', words=(), no_speech_prob=.05)
        model.transcribe.side_effect = [(iter(()), SimpleNamespace(language='en')),
                                       (iter([raw]), SimpleNamespace(language='en'))]
        with patch.object(provider, 'available', return_value=True), \
             patch.object(provider, '_get_model', return_value=model), \
             patch('lyrics_engine.providers.decode_song_audio', return_value=np.ones(16000 * 10, dtype=np.float32) * .1) as decode:
            result = provider.transcribe('test.wav', language='en')
        self.assertTrue(result.text)
        self.assertFalse(result.instrumental)
        self.assertEqual(model.transcribe.call_count, 2)
        self.assertIsNone(model.transcribe.call_args.kwargs['no_speech_threshold'])
        decode.assert_called_once()
