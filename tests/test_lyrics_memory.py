from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from lyrics_engine.memory import (GIB, MIB, MemorySnapshot, MemoryWatch,
                                  RecognitionMemoryError, recycle_when_idle)
from lyrics_engine.isolated import IsolatedLyricsProvider
from lyrics_engine.models import LyricsResult


class MemoryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.healthy = MemorySnapshot(total=16 * GIB, available=6 * GIB,
                                      rss=5 * GIB, private=5 * GIB, commit_available=8 * GIB)

    def test_large_working_set_with_available_memory_is_not_an_error(self):
        watch = MemoryWatch()
        for now in (0, 2, 4, 6, 20):
            watch.check(self.healthy, now)
        self.assertTrue(recycle_when_idle(self.healthy))

    def test_transient_physical_pressure_can_recover(self):
        watch = MemoryWatch()
        low = replace(self.healthy, available=256 * MIB)
        watch.check(low, 0)
        watch.check(low, 2)
        watch.check(self.healthy, 4)
        watch.check(low, 8)
        watch.check(low, 10)

    def test_sustained_physical_pressure_has_precise_diagnostics(self):
        watch = MemoryWatch()
        low = replace(self.healthy, available=256 * MIB)
        watch.check(low, 0)
        watch.check(low, 4)
        with self.assertRaisesRegex(RecognitionMemoryError, 'available RAM: 256 MB'):
            watch.check(low, 6)

    def test_commit_pressure_is_detected_even_with_plenty_of_physical_ram(self):
        watch = MemoryWatch()
        low = replace(self.healthy, commit_available=256 * MIB)
        watch.check(low, 0)
        with self.assertRaisesRegex(RecognitionMemoryError, 'system commit'):
            watch.check(low, 6)

    def test_critical_pressure_is_stopped_immediately(self):
        for low in (replace(self.healthy, available=64 * MIB),
                    replace(self.healthy, commit_available=64 * MIB)):
            with self.assertRaises(RecognitionMemoryError):
                MemoryWatch().check(low, 0)

    def test_missing_commit_measurement_is_supported(self):
        MemoryWatch().check(replace(self.healthy, commit_available=None), 0)

    def test_normal_sized_model_is_reused(self):
        self.assertFalse(recycle_when_idle(replace(self.healthy, private=2 * GIB)))

    def test_large_worker_delivers_result_before_recycling(self):
        provider = IsolatedLyricsProvider()
        process = Mock()
        process.poll.return_value = None
        provider._process = process
        provider._events = Mock()
        def response(**kwargs):
            return dict(event='result', id='test-request', result=dict(text='A synthetic test line'))
        provider._events.get.side_effect = response
        with patch('lyrics_engine.isolated.uuid.uuid4', return_value=Mock(hex='test-request')), \
             patch('lyrics_engine.isolated.time.monotonic', side_effect=[0, 3]), \
             patch('lyrics_engine.isolated.memory_snapshot', return_value=self.healthy), \
             patch.object(provider, 'close') as close:
            result = provider.transcribe('test.wav')
        self.assertIsInstance(result, LyricsResult)
        self.assertEqual(result.text, 'A synthetic test line')
        close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
