import copy
import hashlib
import math
import shutil
import struct
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from audio_editor import Cancelled, Timeline, read_waveform, run_ffmpeg
from editor_pipeline import EditorPipelineSource, project_signature
from easy_music_process import process_music
from lyrics_engine import LyricsResult, TranscriptSegment
import music_metadata
import music_polisher_gui


def tone(path):
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b''.join(struct.pack('<h', int(6000 * math.sin(i * 2 * math.pi * 330 / 8000)))
                                   for i in range(24000)))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class EditorPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.wav = self.root / 'Original song.wav'
        tone(self.wav)
        self.mp3 = self.root / 'Original song.mp3'
        run_ffmpeg(['-i', str(self.wav), '-metadata', 'title=Original title',
                    '-metadata', 'artist=Test artist', '-c:a', 'libmp3lame', str(self.mp3)])
        self.original_hash = digest(self.mp3)
        self.project = Timeline()
        self.clip = self.project.add(read_waveform(self.mp3), 0, 0)
        self.project.update(self.clip.id, start=.5, end=2, gain=-3)
        self.cache = EditorPipelineSource()

    def tearDown(self):
        self.cache.close()
        self.temp.cleanup()

    def test_formats_preserve_edit_duration_tags_and_original(self):
        import av
        for extension in ('.mp3', '.wav', '.m4a'):
            with self.subTest(extension=extension):
                path = self.cache.prepare(self.project, extension)
                self.assertEqual(path.suffix, extension)
                with av.open(str(path)) as audio:
                    self.assertAlmostEqual(audio.duration / 1e6, 1.5, delta=.12)
                tags = music_metadata.read_all_metadata(path)
                self.assertEqual(tags['title'], 'Original title')
                self.assertEqual(tags['artist'], 'Test artist')
        self.assertEqual(digest(self.mp3), self.original_hash)

    def test_cache_reuse_and_invalidation(self):
        first = self.cache.prepare(self.project, '.mp3')
        with patch('editor_pipeline.render') as render:
            self.assertEqual(self.cache.prepare(copy.deepcopy(self.project), '.mp3'), first)
            render.assert_not_called()
        self.project.update(self.clip.id, gain=-10)
        self.assertIsNone(self.cache.current(self.project, '.mp3'))
        second = self.cache.prepare(self.project, '.mp3')
        self.assertNotEqual(first, second)
        self.project.undo()
        self.assertIsNone(self.cache.current(self.project, '.mp3'))
        self.assertNotEqual(project_signature(self.project, '.mp3'), project_signature(self.project, '.wav'))

    def test_source_change_cancellation_and_empty_mix_never_use_original(self):
        self.cache.prepare(self.project, '.mp3')
        self.project.muted.add(0)
        with self.assertRaisesRegex(ValueError, 'No audible clips'):
            self.cache.prepare(self.project, '.mp3')
        self.project.muted.clear()
        self.project.update(self.clip.id, gain=-6)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.cache.prepare(self.project, '.mp3', cancel)
        self.mp3.touch()
        with self.assertRaisesRegex(ValueError, 'Source audio changed'):
            self.cache.current(self.project, '.mp3')
        with self.assertRaises(ValueError):
            self.cache.prepare(self.project, '.exe')

    def test_metadata_cover_and_manual_lyrics_reach_edited_result_without_audio_change(self):
        from audio_tags import read_id3
        source = self.cache.prepare(self.project, '.mp3')
        original_bytes = source.read_bytes()[read_id3(source)[1]:]
        cover = self.root / 'cover.png'
        Image.new('RGB', (128, 128), '#6750bd').save(cover)
        lyrics = LyricsResult(text='A manually checked test line',
                              segments=(TranscriptSegment(.1, 1.2, 'A manually checked test line'),))
        with patch('lyrics_engine.recognize_batch') as recognize:
            process_music(source, self.root / 'result', process_steps={'metadata', 'cover', 'lyrics'},
                          title='Edited title', extra_metadata={'artist': 'Edited artist'},
                          custom_cover_path=cover, cover_size=128, edited_lyrics_result=lyrics)
            recognize.assert_not_called()
        result = self.root / 'result' / source.name
        tags = music_metadata.read_all_metadata(result)
        self.assertEqual(tags['title'], 'Edited title')
        self.assertEqual(tags['artist'], 'Edited artist')
        self.assertIn('A manually checked test line', tags['lyrics'])
        # Metadata remux may rebuild MPEG headers; compare decoded audio instead.
        import av
        def pcm(path):
            with av.open(str(path)) as audio:
                return b''.join(frame.to_ndarray().tobytes() for frame in audio.decode(audio=0))
        self.assertEqual(pcm(result), pcm(source))
        self.assertTrue(any(frame.name == 'APIC' for frame in read_id3(result)[2]))
        self.assertEqual(digest(self.mp3), self.original_hash)
        self.assertTrue(original_bytes)


class EditorPipelineGuiTests(unittest.TestCase):
    def setUp(self):
        self.app = music_polisher_gui.SonicForgeApp()
        self.app.update()

    def tearDown(self):
        self.app.destroy()

    def test_toggle_preserves_original_and_export_and_localizes(self):
        self.app.source_var.set('C:/Music/original.mp3')
        self.app.toggle_editor_pipeline()
        self.assertTrue(self.app.editor_pipeline_var.get())
        self.assertEqual(self.app.source_var.get(), 'C:/Music/original.mp3')
        self.assertEqual(str(self.app.view.source_entry.cget('state')), 'disabled')
        self.app.toggle_language()
        modes = [widget for widget, kind in self.app.view.editor_link_controls if kind == 'mode']
        self.assertTrue(all(widget.cget('text') == 'Link editor: on' for widget in modes))
        self.app.toggle_editor_pipeline()
        self.assertEqual(str(self.app.view.source_entry.cget('state')), 'normal')
        self.assertFalse(self.app.editor_pipeline_var.get())
        export = next(widget for widget, key in self.app.view.editor.localized if key == 'export')
        self.assertEqual(str(export.cget('state')), 'normal')

    def test_all_source_consumers_route_through_link(self):
        self.app.toggle_editor_pipeline()
        self.app.output_var.set('C:/Music/results')
        for action in (self.app.load_metadata, self.app.analyze_audio_settings,
                       self.app.create_audio_preview, self.app.load_existing_lyrics,
                       self.app.recognize_lyrics, self.app.preview_cover, self.app.save_lyrics_file,
                       lambda: self.app._run_process({'metadata', 'lyrics', 'cover'})):
            with self.subTest(action=action), patch.object(self.app, '_prepare_editor_source') as prepare:
                action()
                prepare.assert_called_once()

    def test_empty_linked_project_does_not_fall_back_to_original(self):
        self.app.source_var.set('C:/Music/original.mp3')
        self.app.toggle_editor_pipeline()
        callback = unittest.mock.Mock()
        with patch('music_polisher_gui.messagebox.showerror') as error:
            self.app._prepare_editor_source(callback)
        callback.assert_not_called()
        error.assert_called_once()

    def test_processing_refuses_to_overwrite_an_editor_original(self):
        from audio_editor import AudioSource
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'song.mp3'
            original.touch()
            self.app.view.editor.project.add(AudioSource(str(original), 2), 0, 0)
            self.app.toggle_editor_pipeline()
            self.app.output_var.set(str(root))
            with patch('music_polisher_gui.messagebox.showerror') as error, \
                 patch.object(self.app, '_process_worker') as process:
                self.app._run_process({'metadata'}, _prepared_source=root / 'temporary' / 'song.mp3')
            error.assert_called_once()
            process.assert_not_called()

    def test_uncertain_lyrics_are_not_silently_embedded_by_processing(self):
        self.app.toggle_editor_pipeline()
        self.app.output_var.set('C:/Music/results')
        self.app.lyrics_result = LyricsResult(text='Uncertain test text', review_reason='confidence')
        self.app.view.set_lyrics_text(self.app.lyrics_result.text)
        with patch('music_polisher_gui.messagebox.askyesno', return_value=False) as confirm, \
             patch.object(self.app, '_process_worker') as process:
            self.app._run_process({'lyrics'}, _prepared_source=Path('C:/Temp/song.mp3'))
        confirm.assert_called_once()
        process.assert_not_called()

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_background_preparation_cache_busy_and_final_input(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / 'song.wav'
            tone(original)
            editor = self.app.view.editor
            clip = editor.project.add(read_waveform(original), 0, 0)
            editor.project.update(clip.id, start=1, end=2)
            self.app.source_var.set(str(original))
            self.app.toggle_editor_pipeline()
            sources = []
            self.app._prepare_editor_source(sources.append)
            self.assertTrue(editor.is_busy)
            deadline = time.monotonic() + 10
            while not sources and time.monotonic() < deadline:
                self.app.update()
                time.sleep(.02)
            self.assertEqual(len(sources), 1)
            self.assertFalse(editor.is_busy)
            self.assertNotEqual(sources[0], original)
            self.assertEqual(self.app.source_var.get(), str(original))
            with patch('editor_pipeline.render') as render:
                self.app._prepare_editor_source(sources.append)
                render.assert_not_called()
            self.app.view.set_lyrics_text('Checked manual text')
            captured = []
            with patch.object(self.app, '_process_worker', side_effect=captured.append):
                self.app._run_process({'metadata', 'lyrics'})
                self.app.worker.join(2)
            self.assertEqual(captured[0]['source'], str(sources[0]))
            self.assertEqual(captured[0]['edited_lyrics_result'].text, 'Checked manual text')
            self.assertTrue(captured[0]['overwrite_lyrics'])
            self.app.view.set_busy(False)
            editor.project.update(clip.id, gain=-8)
            editor.changed()
            self.assertEqual(self.app.view.get_lyrics_text(), '')
            self.assertIsNone(self.app._editor_source.current(editor.project, '.mp3'))


if __name__ == '__main__':
    unittest.main()
