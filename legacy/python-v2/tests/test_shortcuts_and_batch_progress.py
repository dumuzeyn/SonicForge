import unittest
from unittest.mock import patch

import music_polisher_gui


class ProcessingWorkerProgressTests(unittest.TestCase):
    def test_background_worker_forwards_lyrics_stage_and_completion(self):
        app = music_polisher_gui.SonicForgeApp()
        try:
            app.view.reset_lyrics_execution(True)
            def process(**kwargs):
                kwargs["lyrics_progress"]("loading_model", dict(file="test.mp3", index=1, total=1))
                kwargs["lyrics_progress"]("completed", dict(total=1, saved=1, preserved=0, uncertain=0, failed=0))
            with patch("easy_music_process.process_music", side_effect=process):
                app._process_worker({})
            app._drain_log_queue()
            self.assertEqual(app.view.lyrics_execution_stage, "completed")
            self.assertIn("Записано: 1", app.view.lyrics_execution_status.get())
        finally:
            app.destroy()

    def test_background_error_does_not_report_lyrics_completed(self):
        app = music_polisher_gui.SonicForgeApp()
        try:
            app.view.reset_lyrics_execution(True)
            with patch("easy_music_process.process_music", side_effect=RuntimeError("Synthetic failure")):
                app._process_worker({})
            app._drain_log_queue()
            self.assertEqual(app.view.lyrics_execution_stage, "error")
            self.assertIn("не завершена", app.view.lyrics_execution_status.get())
        finally:
            app.destroy()
