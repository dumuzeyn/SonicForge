import math
import shutil
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from audio_editor import Cancelled
from sound_analysis import SoundAnalysisCache, analyze_sound
import music_polisher_gui


class SoundAnalysisTests(unittest.TestCase):
    def test_long_track_has_bounded_spread_excerpts_and_no_artwork_analysis(self):
        events, decoded = [], []
        def decode(path, start, seconds, cancel):
            decoded.append((start, seconds))
            return (.1 * np.sin(np.arange(int(seconds * 22050)) * 2 * math.pi * 110 / 22050)).astype('float32')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'song.mp3'
            path.touch()
            with patch('sound_analysis.probe_audio', return_value={'duration': 3600}), \
                 patch('sound_analysis._decode', side_effect=decode), \
                 patch('music2picture_v2.audio_analysis.analyze_audio_file') as artwork:
                analysis, noise = analyze_sound(path, progress=lambda stage, data: events.append(stage))
        self.assertEqual(len(decoded), 3)
        self.assertEqual(sum(seconds for start, seconds in decoded), 24)
        self.assertEqual([start for start, seconds in decoded], [360, 1620, 2880])
        self.assertEqual(analysis.analyzed_seconds, 24)
        self.assertGreater(analysis.bass_energy, .9)
        self.assertFalse(noise['apply'])
        self.assertEqual(events, ['opening', 'reading', 'reading', 'reading', 'levels', 'spectrum', 'noise', 'recommendation'])
        artwork.assert_not_called()

    def test_cache_is_bounded_reused_and_invalidated_by_file_change(self):
        cache = SoundAnalysisCache()
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{index}.mp3' for index in range(5)]
            for path in paths:
                path.touch()
            with patch('sound_analysis.analyze_sound', return_value=('analysis', 'noise')) as run:
                cache.analyze(paths[0])
                cache.analyze(paths[0])
                self.assertEqual(run.call_count, 1)
                paths[0].write_bytes(b'changed')
                cache.analyze(paths[0])
                self.assertEqual(run.call_count, 2)
                for path in paths[1:]:
                    cache.analyze(path)
                self.assertLessEqual(len(cache.results), 4)

    def test_cancel_prevents_decoding_and_caching(self):
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'song.mp3'
            path.touch()
            with patch('sound_analysis._decode') as decode:
                with self.assertRaises(Cancelled):
                    analyze_sound(path, cancel)
            decode.assert_not_called()

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_real_decode_preserves_source_and_provides_summary_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tone.wav'
            data = (.1 * np.sin(np.arange(24000) * 2 * math.pi * 110 / 8000) * 32767).astype('<i2')
            with wave.open(str(path), 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(data.tobytes())
            before = path.read_bytes()
            analysis, noise = analyze_sound(path)
            self.assertAlmostEqual(analysis.analyzed_seconds, 3, delta=.02)
            self.assertAlmostEqual(analysis.rms_dbfs, -23.0, delta=.2)
            self.assertGreater(analysis.bass_energy, .9)
            self.assertLess(analysis.brightness, .1)
            self.assertEqual(path.read_bytes(), before)


class SoundAnalysisGuiTests(unittest.TestCase):
    def test_cancel_stops_analysis_and_clears_activity(self):
        app = music_polisher_gui.SonicForgeApp()
        try:
            app.update()
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'song.mp3'
                path.touch()
                app.source_var.set(str(path))
                def wait_for_cancel(path, cancel, progress):
                    self.assertTrue(cancel.wait(5))
                    raise Cancelled()
                with patch.object(app._sound_analysis_cache, 'analyze', side_effect=wait_for_cancel):
                    app.analyze_audio_settings()
                    app.view.audio_cancel_button.invoke()
                    deadline = time.monotonic() + 2
                    while app._audio_analysis_active and time.monotonic() < deadline:
                        app.update()
                        time.sleep(.02)
                self.assertFalse(app._audio_analysis_active)
                self.assertFalse(app.view.busy)
                self.assertIn('отменён', app.audio_analysis_var.get())
                self.assertIsNone(app.view._audio_activity_after)
        finally:
            app.destroy()

    def test_cancelled_editor_preparation_does_not_leave_analysis_timer_running(self):
        app = music_polisher_gui.SonicForgeApp()
        try:
            app.update()
            app._audio_analysis_active = True
            app.view.start_audio_activity()
            callback = unittest.mock.Mock()
            app.cancel_event.set()
            app.log_queue.put(('__EDITOR_SOURCE__', Path('C:/Temp/mix.mp3'), callback))
            app._drain_log_queue()
            self.assertFalse(app._audio_analysis_active)
            self.assertIsNone(app.view._audio_activity_after)
            callback.assert_not_called()
        finally:
            app.destroy()

    def test_activity_timer_stages_and_real_result_reach_ui(self):
        app = music_polisher_gui.SonicForgeApp()
        try:
            app.update()
            app.view.show_tab('audio')
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'tone.wav'
                with wave.open(str(path), 'wb') as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(8000)
                    audio.writeframes(np.zeros(24000, dtype='<i2').tobytes())
                app.source_var.set(str(path))
                app.analyze_audio_settings()
                self.assertTrue(app._audio_analysis_active)
                self.assertEqual(str(app.view.audio_cancel_button.cget('state')), 'normal')
                self.assertIn('Открытие', app.view.audio_activity_var.get())
                app.view.set_audio_activity_stage('reading', dict(index=2, total=3))
                self.assertIn('2/3', app.view.audio_activity_var.get())
                app.toggle_language()
                app.view._tick_audio_activity()
                self.assertIn('Reading excerpt', app.view.audio_activity_var.get())
                deadline = time.monotonic() + 10
                while app._audio_analysis_active and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                self.assertFalse(app._audio_analysis_active)
                self.assertIsNotNone(app.audio_analysis_data)
                self.assertIn('Estimated from', app.audio_analysis_var.get())
                self.assertIn('Finished', app.view.audio_activity_var.get())
                self.assertEqual(str(app.view.audio_cancel_button.cget('state')), 'disabled')
                self.assertIsNone(app.view._audio_activity_after)
        finally:
            app.destroy()


if __name__ == '__main__':
    unittest.main()
