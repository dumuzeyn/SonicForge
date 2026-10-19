import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lyrics_engine.formats import format_timestamp, parse_lrc, render_lrc, result_from_text, save_lyrics
from lyrics_engine.models import LyricsResult, TranscriptSegment
from lyrics_engine.service import LyricsService
from lyrics_engine.vocals import VocalCache
from audio_editor import Cancelled


class TimedLyricsTests(unittest.TestCase):
    def test_lrc_fractions_offsets_repeated_lines_and_order(self):
        segments = parse_lrc('[ti:Test]\n[offset:100]\n[01:02.123]Later\n[00:03.12][00:01.1]Earlier', strict=True)
        self.assertEqual([s.text for s in segments], ['Earlier', 'Earlier', 'Later'])
        for value, expected in zip([s.start for s in segments], [1.2, 3.22, 62.223]):
            self.assertAlmostEqual(value, expected)
        self.assertEqual(segments[0].end, segments[1].start)
        self.assertEqual(format_timestamp(59.999), '01:00.00')

    def test_invalid_and_mixed_input_is_rejected_without_losing_lines(self):
        for text in ('[00:60]wrong', '[00:01]yes\nuntimed', '[00:01]yes[00:1bad]',
                     '[offset:-2000]\n[00:01]negative', '[00:01.1234]bad', '[nonsense]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                result_from_text(text, force_timed=True)

    def test_plain_edit_retains_times_only_for_same_line_count(self):
        previous = result_from_text('[00:01.25]one\n[00:05.50]two')
        edited = result_from_text('first edited\nsecond edited', previous)
        self.assertEqual([s.start for s in edited.segments], [1.25, 5.5])
        self.assertEqual(edited.text, 'first edited\nsecond edited')
        self.assertFalse(result_from_text('single line', previous).segments)
        with self.assertRaises(ValueError):
            render_lrc(LyricsResult(text='untimed'))

    def test_manual_timing_roundtrips_mp3_and_lrc_without_overwriting_other_tags(self):
        from mutagen.id3 import ID3, TIT2
        from lyrics_engine.formats import load_sidecar
        from music_metadata import read_all_metadata
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mp3 = root / 'song.mp3'
            tags = ID3()
            tags.add(TIT2(encoding=3, text='User title'))
            tags.save(mp3)
            result = result_from_text('[00:20.62]Первая строка\n[00:26.28]Вторая строка')
            save_lyrics(mp3, result)
            self.assertEqual(ID3(mp3)['TIT2'].text, ['User title'])
            reopened = LyricsService(provider=Mock(), metadata_reader=read_all_metadata).load_existing(mp3)
            self.assertEqual([s.start for s in reopened.segments], [20.62, 26.28])
            wav = root / 'song.wav'
            wav.touch()
            save_lyrics(wav, result, 'lrc')
            self.assertEqual(load_sidecar(wav).segments, reopened.segments)


class VocalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / 'original.mp3'
        self.source.write_bytes(b'Original stays unchanged')
        self.cache = VocalCache()
        self.addCleanup(self.cache.close)
        self.probe = patch('lyrics_engine.vocals.probe_audio', return_value={'duration': 12.5})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    @staticmethod
    def separate(source, start, duration, **options):
        assert (start, duration, options['mode']) == (0, 12.5, 'four')
        paths = [Path(options['cache_root']) / f'{name}.wav' for name in ('vocals', 'bass', 'drums', 'other')]
        for path in paths:
            path.write_bytes(b'Synthetic separated fixture')
        return paths

    def test_actual_service_passes_vocals_to_asr_reuses_cache_and_cleans_up(self):
        provider = Mock()
        provider.transcribe.return_value = LyricsResult(text='one two three', segments=(TranscriptSegment(2, 5, 'one two three'),))
        service = LyricsService(provider=provider, separate_vocals=True)
        service._vocal_cache = self.cache
        with patch('lyrics_engine.vocals.separate_clip', side_effect=self.separate) as separation:
            service.recognize(self.source)
            vocal = provider.transcribe.call_args.args[0]
            self.assertEqual(vocal.name, 'vocals.wav')
            self.assertEqual(list(vocal.parent.iterdir()), [vocal])
            service.recognize(self.source)
            separation.assert_called_once()
            self.assertEqual(provider.transcribe.call_count, 2)
            self.source.write_bytes(b'Changed audio')
            service.recognize(self.source)
            self.assertEqual(separation.call_count, 2)
        self.assertFalse(vocal.exists())
        latest = provider.transcribe.call_args.args[0]
        service.close()
        self.assertFalse(latest.parent.exists())

    def test_cancellation_and_decoder_errors_never_fall_back_to_mix(self):
        event = threading.Event()
        event.set()
        with patch('lyrics_engine.vocals.separate_clip') as separation, self.assertRaises(InterruptedError):
            self.cache.prepare(self.source, event)
        separation.assert_not_called()
        provider = Mock()
        service = LyricsService(provider=provider, separate_vocals=True)
        service._vocal_cache = self.cache
        for failure, expected in ((Cancelled('stop'), InterruptedError), (RuntimeError('decode failed'), RuntimeError)):
            with patch('lyrics_engine.vocals.separate_clip', side_effect=failure), self.assertRaises(expected):
                service.recognize(self.source)
        provider.transcribe.assert_not_called()
        self.assertIsNone(self.cache._temporary)
        self.assertEqual(self.source.read_bytes(), b'Original stays unchanged')

    def test_timeline_mismatch_is_rejected(self):
        with patch('lyrics_engine.vocals.separate_clip', side_effect=self.separate), \
             patch('lyrics_engine.vocals.probe_audio', side_effect=[{'duration': 12.5}, {'duration': 10}]), \
             self.assertRaisesRegex(RuntimeError, 'timeline'):
            self.cache.prepare(self.source)
        self.assertIsNone(self.cache._temporary)

    def test_separation_is_enabled_by_default_and_can_be_disabled(self):
        service = LyricsService()
        self.addCleanup(service.close)
        self.assertTrue(service.separate_vocals)
        provider = Mock()
        provider.transcribe.return_value = LyricsResult(text='one two three')
        LyricsService(provider=provider, separate_vocals=False).recognize(self.source)
        self.assertEqual(provider.transcribe.call_args.args[0], self.source)

    def test_batch_prepares_each_song_and_reports_vocal_stage(self):
        from lyrics_engine.batch import recognize_batch
        root = Path(self.directory.name)
        self.source.unlink()
        for name in ('first.wav', 'second.wav'):
            (root / name).write_bytes(b'Synthetic audio fixture')
        provider = Mock()
        provider.transcribe.return_value = LyricsResult(text='one two three', segments=(TranscriptSegment(2, 5, 'one two three'),))
        service = LyricsService(provider=provider, separate_vocals=False)
        service._vocal_cache = self.cache
        self.addCleanup(service.close)
        events = []
        with patch('lyrics_engine.vocals.separate_clip', side_effect=self.separate) as separation:
            recognize_batch(root, root, service=service, export_format='lrc', separate_vocals=True,
                            progress=lambda stage, details: events.append((stage, details)))
        self.assertEqual(separation.call_count, 2)
        self.assertTrue(all(call.args[0].name == 'vocals.wav' for call in provider.transcribe.call_args_list))
        self.assertEqual(len([event for event in events if event[0] == 'separating_vocals']), 2)
        self.assertEqual(events[-1][1]['saved'], 2)
        self.assertIn('[00:01.90]one two three', (root / 'second.lrc').read_text())


if __name__ == '__main__':
    unittest.main()
