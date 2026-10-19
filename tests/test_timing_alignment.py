from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

import numpy as np
from lyrics_alignment_backend import align_existing, local_ranges
from lyrics_engine.formats import timing_input, load_sidecar, save_lyrics
from lyrics_engine.models import LyricsResult, TranscriptSegment
from lyrics_engine.service import LyricsService
from lyrics_engine.batch import recognize_batch


class TimingAlignmentTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_full_folder_pipeline_changes_only_tag_times_and_keeps_audio(self):
        from audio_tags import read_id3, text_frame, update_id3
        import music_metadata
        from easy_music_process import process_music
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source'; output = root/'result'
            source.mkdir(); song=source/'song.mp3'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=220:duration=2',str(song)], check=True)
            original=timing_input('[00:00.20]Repeat\n[00:01.00]Middle\n[00:01.50]Repeat')
            save_lyrics(song,original)
            update_id3(song,[text_frame('TIT2','Original title')])
            before=song.read_bytes(); offset=read_id3(song)[1]
            service=LyricsService(provider=Mock(),metadata_reader=music_metadata.read_all_metadata,separate_vocals=False)
            def align(path,existing,**kwargs):
                return replace(existing,segments=tuple(replace(s,start=s.start+.05,end=s.end+.05) if i != 1 else s
                                                        for i,s in enumerate(existing.segments)),timings_preserved=1)
            with patch.object(service,'align',side_effect=align):
                process_music(source,output,process_steps={'lyrics'},lyrics_mode='align',lyrics_service=service)
            self.assertEqual(song.read_bytes(),before)
            written=output/'song.mp3'
            self.assertEqual(written.read_bytes()[read_id3(written)[1]:],before[offset:])
            self.assertEqual(music_metadata.read_all_metadata(written)['title'],'Original title')
            result=service.load_for_timing(written)
            self.assertEqual(result.text,original.text)
            self.assertEqual([s.start for s in result.segments],[.25,1.,1.55])
            service.provider.transcribe.assert_not_called()

    def test_repeat_windows_never_cross_other_occurrence(self):
        original = timing_input('[00:10]Chorus!\n[00:12]Other\n[00:14]Chorus!')
        windows = local_ranges(asdict(original), original.text.splitlines(), 40)
        self.assertEqual(windows[0]['end'], 12)
        self.assertEqual(windows[2]['start'], 12)
        self.assertLess(windows[0]['end'], original.segments[2].start)

    def test_bad_old_times_do_not_reorder_or_remove_words(self):
        original = timing_input('[offset:100]\n[00:20]First\n[00:10]Repeat\n[00:30]Repeat')
        self.assertEqual(original.text, 'First\nRepeat\nRepeat')
        self.assertAlmostEqual(original.segments[0].start, 20.1)
        self.assertIsNone(local_ranges(asdict(original), original.text.splitlines(), 40))

    def test_only_model_times_are_used_words_and_repeats_are_immutable(self):
        original = timing_input('[00:10]Keep punctuation!\n[00:20]Repeat\n[00:30]Repeat')
        word = SimpleNamespace(probability=.9, start=1, end=2)
        times = iter((11, 21, 31))
        def aligner(model, audio, windows, **kwargs):
            start = next(times)
            return SimpleNamespace(segments=[SimpleNamespace(start=start, end=start+2, words=[word], text='MODEL CHANGED IT')])
        model = Mock()
        with patch('faster_whisper.audio.decode_audio', return_value=np.ones(16000*45)):
            result = align_existing(model, 'audio.mp3', asdict(original), 'en', aligner=Mock(), local_aligner=aligner)
        self.assertEqual(result['text'], original.text)
        self.assertEqual([s['text'] for s in result['segments']], original.text.splitlines())
        self.assertEqual([s['start'] for s in result['segments']], [10.9,20.9,30.9])
        model.transcribe.assert_not_called()
        model.generate.assert_not_called()

    def test_bad_line_keeps_its_time_but_other_lines_are_corrected(self):
        original = timing_input('[00:10]one\n[00:20]two')
        word = SimpleNamespace(probability=.9, start=1, end=2)
        times = iter((11, 9))
        def aligner(*args, **kwargs):
            start = next(times)
            return SimpleNamespace(segments=[SimpleNamespace(start=start, end=start+1, words=[word])])
        with patch('faster_whisper.audio.decode_audio', return_value=np.ones(16000*40)):
            result = align_existing(Mock(), 'audio', asdict(original), 'en', aligner=Mock(), local_aligner=aligner)
        self.assertEqual(result['segments'][0]['start'], 10.9)
        self.assertEqual(result['segments'][1], asdict(original)['segments'][1])
        self.assertEqual(result['timings_preserved'], 1)
        self.assertEqual(result['review_reason'], '')

    def test_missing_repeated_line_retains_it_and_keeps_other_occurrence(self):
        original = timing_input('[00:10]Repeat!\n[00:20]Middle\n[00:30]Repeat!')
        word = SimpleNamespace(probability=.9, start=1, end=2)
        def aligner(model, audio, windows, **kwargs):
            start = windows[0]['start'] + 5
            if windows[0]['text'] == 'Middle': raise ValueError('not found')
            return SimpleNamespace(segments=[SimpleNamespace(start=start, end=start+1, words=[word])])
        with patch('faster_whisper.audio.decode_audio', return_value=np.ones(16000*50)):
            result = align_existing(Mock(), 'audio', asdict(original), 'en', aligner=Mock(), local_aligner=aligner)
        self.assertEqual([s['start'] for s in result['segments']], [10.9,20,30.9])
        self.assertEqual([s['text'] for s in result['segments']], original.text.splitlines())
        self.assertEqual(result['timings_preserved'], 1)

    def test_service_rejects_changed_supplied_words(self):
        service = LyricsService(provider=Mock(), separate_vocals=False)
        original = timing_input('[00:10]existing words')
        service._timing_provider = Mock()
        service._timing_provider.align.return_value = replace(original, text='new words')
        with self.assertRaisesRegex(ValueError, 'changed'):
            service.align('audio', original)
        service.provider.transcribe.assert_not_called()

    def test_folder_uses_each_text_and_preserves_failed_uncertain_and_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source'; staged = root/'output'
            source.mkdir(); staged.mkdir()
            for name in ('good', 'uncertain', 'failed', 'missing'):
                (source/(name+'.wav')).write_bytes(b'unchanged source audio')
                (staged/(name+'.wav')).write_bytes(b'unchanged output audio')
                if name != 'missing':
                    save_lyrics(source/(name+'.wav'), timing_input('[00:10]'+name+'\n[00:20]Repeat\n[00:30]Repeat'), 'lrc')
            service = LyricsService(provider=Mock(), separate_vocals=False)
            def align(path, original, **kwargs):
                if path.stem == 'failed': raise RuntimeError('model fault')
                if path.stem == 'uncertain': return replace(original, review_reason='alignment')
                return replace(original, segments=tuple(replace(s, start=s.start+1, end=s.end+1) for s in original.segments))
            with patch.object(service, 'align', side_effect=align):
                result = recognize_batch(source, staged, service=service, mode='align')
            self.assertEqual(set(result), {'good'})
            for name in ('good', 'uncertain', 'failed'):
                old = service.load_for_timing(source/(name+'.wav'))
                new = load_sidecar(staged/(name+'.wav'))
                self.assertEqual(new.text, old.text)
                self.assertEqual(new.segments[0].start, 11 if name == 'good' else 10)
            for name in ('good', 'uncertain', 'failed', 'missing'):
                self.assertEqual((source/(name+'.wav')).read_bytes(), b'unchanged source audio')
                self.assertEqual((staged/(name+'.wav')).read_bytes(), b'unchanged output audio')
            self.assertFalse((staged/'missing.lrc').exists())
            service.provider.transcribe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
