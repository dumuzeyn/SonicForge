import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from lyrics_engine.language_detection import detect_song_language, wide_language_windows
from lyrics_engine.language_identifier import LocalLanguageIdentifier
from lyrics_engine.models import LyricsResult, TranscriptSegment
from lyrics_engine.providers import FasterWhisperProvider, MockLyricsProvider, _implausible_text
from lyrics_engine.service import LyricsService
from lyrics_engine.transliteration import sound_spelling
from lyrics_engine.verification import duplicate_boundary_segment, verified_segments


class ForeignLyricsTests(unittest.TestCase):
    def setUp(self):
        self.audio = np.ones(16000 * 100, dtype=np.float32) * 0.1
        decoder = patch('lyrics_engine.providers.decode_song_audio', return_value=self.audio)
        decoder.start()
        self.addCleanup(decoder.stop)

    def test_strong_russian_id_does_not_load_secondary_model(self):
        model = Mock()
        model.detect_language.return_value = ('ru', .95, [('ru', .95), ('en', .05)])
        classifier = Mock()
        language, probability = detect_song_language(model, self.audio, identifier=classifier)
        self.assertEqual(language, 'ru')
        self.assertAlmostEqual(probability, .95)
        classifier.detect_language.assert_not_called()

    def test_weak_english_guess_is_resolved_by_independent_audio_id(self):
        model = Mock()
        model.detect_language.side_effect = [
            ('en', .465, [('en', .465), ('ka', .02)]),
            ('hy', .132, [('hy', .132), ('en', .036), ('ka', .01)]),
            ('en', .345, [('en', .345), ('ka', .01)]),
        ]
        classifier = Mock()
        classifier.detect_language.side_effect = [
            ('ka', .396, [('ka', .396), ('br', .1)]),
            ('ka', .631, [('ka', .631), ('br', .095)]),
            ('ka', .541, [('ka', .541), ('br', .15)]),
            ('ka', .289, [('ka', .289), ('br', .263)]),
            ('br', .320, [('br', .320), ('ka', .258)]),
        ]
        language, probability = detect_song_language(model, self.audio, identifier=classifier)
        self.assertEqual(language, 'ka')
        self.assertAlmostEqual(probability, (.396 + .631 + .541) / 3)

    def test_uncertain_id_does_not_force_english_or_autosave(self):
        provider = FasterWhisperProvider()
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(start=2, end=5,
            text='A detected practice line', no_speech_prob=.05, words=())]), SimpleNamespace(language='en'))
        with patch.object(provider, 'available', return_value=True), \
             patch.object(provider, '_get_model', return_value=model), \
             patch.object(provider, '_detect_song_language', return_value=(None, .28)):
            result = LyricsService(provider=provider).recognize('unused.mp3')
        model.transcribe.assert_called_once()
        self.assertIsNone(model.transcribe.call_args.kwargs['language'])
        self.assertTrue(result.text)
        self.assertFalse(result.instrumental)
        self.assertEqual(result.review_reason, 'language')
        self.assertFalse(LyricsService.is_usable(result))

    def test_missing_or_inconclusive_classifier_does_not_restore_english_guess(self):
        model = Mock()
        model.detect_language.return_value = ('en', .28, [('en', .28), ('ka', .20)])
        classifier = Mock()
        classifier.detect_language.return_value = ('br', .30, [('br', .30), ('ka', .25)])
        self.assertIsNone(detect_song_language(model, self.audio, identifier=classifier)[0])
        classifier.detect_language.side_effect = OSError('Offline model unavailable')
        self.assertIsNone(detect_song_language(model, self.audio, identifier=classifier)[0])

    def test_language_classifier_is_lazy_and_cancel_does_not_load_it(self):
        identifier = LocalLanguageIdentifier()
        self.assertIsNone(identifier._session)
        model = Mock()
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            detect_song_language(model, self.audio, cancel_event=event, identifier=identifier)
        self.assertIsNone(identifier._session)

    def test_longer_audio_windows_do_not_exceed_song_or_repeat(self):
        windows = wide_language_windows(np.ones(200, dtype=np.float32), sampling_rate=1)
        self.assertEqual([start for start, _ in windows], [10, 50, 90, 130, 160])
        self.assertTrue(all(len(sample) == 40 for _, sample in windows))
        self.assertEqual(len(wide_language_windows(np.ones(15), sampling_rate=1)), 1)
        self.assertEqual(wide_language_windows(np.array([])), [])

    def test_georgian_sound_spelling_is_not_semantic_english_translation(self):
        # A greeting, not a song lyric.
        self.assertEqual(sound_spelling('გამარჯობა', 'en', 'ka'), 'gamarjoba')
        self.assertEqual(sound_spelling('გამარჯობა', 'ru', 'ka'), 'гамарджоба')

    def test_foreign_sound_output_keeps_acoustic_language_and_timestamps(self):
        provider = FasterWhisperProvider()
        model = Mock()
        raw = SimpleNamespace(start=1.25, end=3.0, text='გამარჯობა მეგობარო', no_speech_prob=.01,
                              avg_logprob=-.2, words=())
        model.transcribe.return_value = (iter([raw]), SimpleNamespace(language='ka'))
        streamed = []
        with patch.object(provider, 'available', return_value=True), \
             patch.object(provider, '_get_model', return_value=model), \
             patch.object(provider, '_get_native_model', return_value=model), \
             patch.object(provider, '_detect_song_language', return_value=('ka', .423)):
            result = LyricsService(provider=provider).recognize('unused.mp3', on_segment=streamed.append)
        self.assertEqual(model.transcribe.call_args.kwargs['language'], 'ka')
        self.assertEqual(result.language, 'ka')
        self.assertEqual(result.transcription_alphabet, 'ru')
        self.assertEqual(result.segments[0].start, 1.25)
        self.assertEqual(tuple(streamed), result.segments)
        self.assertIn('гамарджоба', result.text)
        self.assertAlmostEqual(result.language_confidence, .423)

    def test_native_acoustic_model_is_lazy_pinned_and_reuses_single_slot(self):
        provider = FasterWhisperProvider()
        with patch('huggingface_hub.snapshot_download', return_value='cached-model') as download, \
             patch('faster_whisper.WhisperModel') as factory:
            download.assert_not_called()
            provider._get_model()
            foreign = provider._get_native_model('ka')
            self.assertIs(provider._get_native_model('ka'), foreign)
            self.assertEqual(factory.call_count, 2)
            self.assertEqual(download.call_args.kwargs['revision'], 'a99c5dfd889a2ffca19908d99e8b4ffec7de433a')
            provider._get_model()
            self.assertEqual(factory.call_count, 3)
            self.assertEqual(provider._loaded_model_name, 'large-v3-turbo')

    def test_unreliable_text_is_not_mislabelled_high_quality_english(self):
        raw = SimpleNamespace(start=1, end=2.4, text='ა' * 90, compression_ratio=2.8)
        self.assertTrue(_implausible_text(raw, 'ka'))
        self.assertTrue(_implausible_text(SimpleNamespace(start=1, end=29,
            text='ანინანანინაოტ' * 6, compression_ratio=5.6), 'ka'))
        self.assertTrue(_implausible_text(SimpleNamespace(start=1, end=5, text='Invented English phrase'), 'ka'))
        result = LyricsService(provider=MockLyricsProvider(LyricsResult(
            text='gamarjoba megobaro megobaro', segments=(TranscriptSegment(1, 3, 'gamarjoba megobaro megobaro', .99),),
            source='faster-whisper', language='ka', transcription_alphabet='en', review_reason='text',
        ))).recognize('unused.mp3')
        self.assertEqual(result.language, 'ka')
        self.assertEqual(result.quality, 'low')
        self.assertFalse(LyricsService.is_usable(result))

    def test_looped_syllables_need_review_despite_normal_timing_and_high_probability(self):
        raw = SimpleNamespace(start=1, end=29, text='ანი ნანანი ნაოტ ' * 6,
                              compression_ratio=5.6, avg_logprob=-.02, no_speech_prob=.001, words=())
        self.assertTrue(_implausible_text(raw, 'ka'))
        model = Mock()
        model.transcribe.return_value = (iter([raw]), SimpleNamespace(language='ka'))
        provider = FasterWhisperProvider()
        with patch.object(provider, 'available', return_value=True), \
             patch.object(provider, '_get_model', return_value=model), \
             patch.object(provider, '_get_native_model', return_value=model), \
             patch.object(provider, '_detect_song_language', return_value=('ka', .6)):
            result = LyricsService(provider=provider).recognize('unused.mp3')
        self.assertTrue(result.text)
        self.assertEqual(result.transcription_alphabet, 'ru')
        self.assertFalse(result.text.isascii())
        self.assertEqual(result.review_reason, 'text')
        self.assertEqual(result.quality, 'low')
        self.assertFalse(LyricsService.is_usable(result))

    def test_normal_refrain_is_not_deleted_or_flagged_for_repeating(self):
        for text in ('გამარჯობა მეგობარო ' * 2, 'გამარჯობა მეგობარო ' * 6):
            self.assertFalse(_implausible_text(SimpleNamespace(start=1, end=29, text=text,
                                                               compression_ratio=5.6), 'ka'))

    def test_tiny_adjacent_duplicate_is_dropped_without_another_decode(self):
        text = 'A repeated test sentence with enough letters'
        original = SimpleNamespace(start=10, end=20, text=text, words=())
        duplicate = SimpleNamespace(start=20, end=20.1, text=text, words=())
        model = Mock()
        self.assertEqual(list(verified_segments(model, 'unused.wav', [original, duplicate], {})), [original])
        model.transcribe.assert_not_called()
        self.assertFalse(duplicate_boundary_segment(SimpleNamespace(start=20, end=24, text=text), original))
        self.assertFalse(duplicate_boundary_segment(SimpleNamespace(start=20, end=20.1, text='A different test sentence with different words'), original))

    def test_repeating_final_sliver_stops_before_an_infinite_decoder_tail(self):
        original = SimpleNamespace(start=1, end=9.2, text='A normally timed test sentence', words=())
        tail = SimpleNamespace(start=9.4, end=9.5, text='Many unexpected words crammed into this tail', words=())
        read = []
        def decoder():
            yield original
            read.append(True)
            yield tail
            self.fail('The decoder must not be advanced again after an impossible final sliver')
        model = Mock()
        progress = []
        result = list(verified_segments(model, 'unused.wav', decoder(), {}, audio_duration=9.6,
                                        progress=progress.append))
        self.assertEqual(result, [original])
        self.assertEqual(read, [True])
        self.assertIn('unreliable_tail', progress)
        model.transcribe.assert_not_called()

    def test_last_valid_line_near_audio_end_does_not_reenter_decoder(self):
        original = SimpleNamespace(start=1, end=9.9, text='A normally timed final test sentence', words=())
        def decoder():
            yield original
            self.fail('The last valid line covers the audio; do not decode padding again')
        self.assertEqual(list(verified_segments(Mock(), 'unused.wav', decoder(), {}, audio_duration=10)), [original])


if __name__ == '__main__':
    unittest.main()
