import threading
import unittest
from types import SimpleNamespace

import numpy as np

from lyrics_engine.overlap import stitch, transcribe_overlapping, windows
from test_lyrics_verification import segment


class OverlappingLyricsTests(unittest.TestCase):
    def test_short_windows_overlap_and_do_not_add_a_redundant_tail(self):
        self.assertEqual(list(windows(48, sample_rate=1)), [(0, 20), (14, 34), (28, 48)])
        self.assertEqual(list(windows(5, sample_rate=1)), [(0, 5)])
        self.assertEqual(list(windows(20, sample_rate=1)), [(0, 20)])
        self.assertEqual(list(windows(0, sample_rate=1)), [])

    def test_matching_boundary_words_are_kept_once_with_absolute_times(self):
        left = segment('one two three four', 14, 18)
        right = segment('two three four five', 15.05, 19.05)
        before, pending = stitch([left], [right], 14, 20)
        words = [w for s in before + pending for w in s.words]
        self.assertEqual([w.word for w in words], ['one', 'two', 'three', 'four', 'five'])
        self.assertEqual(len(words), 5)
        self.assertAlmostEqual(pending[-1].end, 19.05)
        self.assertEqual(left.text, 'one two three four')

    def test_edge_fragment_is_replaced_by_a_complete_word(self):
        left = segment('разде', 19.6, 20)
        right = segment('разделились', 19.6, 20.5)
        before, pending = stitch([left], [right], 14, 20)
        self.assertEqual([s.text for s in before + pending], ['разделились'])
        self.assertEqual(pending[0].start, 19.6)

    def test_repeated_words_at_different_times_are_not_text_deduplicated(self):
        left = segment('да да', 15, 17)
        right = segment('да да', 18, 20)
        before, pending = stitch([left], [right], 14, 20)
        self.assertEqual(sum(len(s.words) for s in before + pending), 4)

    def test_unmatched_overlap_keeps_whole_words_from_each_side(self):
        left = segment('first wrong', 14, 18)
        right = segment('correct next', 16, 20)
        before, pending = stitch([left], [right], 14, 20)
        self.assertEqual(' '.join(s.text for s in before + pending), 'first correct next')

    def test_a_phrase_only_heard_in_older_window_is_preserved(self):
        left = segment('late opening words', 18, 20)
        before, pending = stitch([left], [], 14, 20)
        self.assertEqual(before, [left])
        self.assertEqual(pending, [])

    def test_full_song_is_scanned_when_first_phrase_starts_after_a_minute(self):
        audio = np.zeros(90 * 16000, dtype=np.float32)
        audio[65 * 16000:70 * 16000] = .1
        calls = []
        class Model:
            def transcribe(self, clip, **options):
                calls.append(len(clip) / 16000)
                first = np.flatnonzero(clip)[0] / 16000
                return iter([segment('first sung phrase', first, first + 3)]), SimpleNamespace(language='ru')
        rows, _ = transcribe_overlapping(Model(), audio, 'ru', {})
        result = list(rows)
        self.assertEqual(result[0].start, 65)
        self.assertEqual(result[0].text, 'first sung phrase')
        self.assertTrue(all(length <= 20 for length in calls))
        self.assertEqual(calls, [20])

    def test_rebases_words_does_not_mutate_decoder_objects_or_repeat_chorus(self):
        raw = segment('repeated chorus line', 1, 4)
        clips = []
        class Model:
            def transcribe(self, clip, **options):
                clips.append(clip)
                return iter([raw]), SimpleNamespace(language='en')
        audio = np.ones(48 * 16000, dtype=np.float32)
        rows, info = transcribe_overlapping(Model(), audio, 'en', {})
        result = list(rows)
        self.assertEqual([s.start for s in result], [1, 15, 29])
        self.assertEqual(len(result), 3)
        self.assertEqual(raw.start, 1)
        self.assertEqual(raw.words[0].start, 1)
        self.assertTrue(all(np.shares_memory(audio, clip) for clip in clips))
        self.assertEqual(info.language, 'en')

    def test_cancel_stops_before_the_next_window(self):
        event = threading.Event()
        calls = []
        class Model:
            def transcribe(self, clip, **options):
                calls.append(1)
                event.set()
                return iter([]), SimpleNamespace(language='en')
        rows, _ = transcribe_overlapping(Model(), np.ones(90 * 16000), 'en', {}, event)
        with self.assertRaises(InterruptedError):
            list(rows)
        self.assertEqual(len(calls), 1)

    def test_empty_or_digital_silence_does_not_call_asr(self):
        class Model:
            def transcribe(self, *args, **options):
                raise AssertionError('No ASR on digital silence')
        for audio in (np.array([]), np.zeros(90 * 16000)):
            rows, _ = transcribe_overlapping(Model(), audio, 'ru', {})
            self.assertEqual(list(rows), [])

    def test_padded_decoder_tail_is_clamped_to_real_duration(self):
        class Model:
            def transcribe(self, clip, **options):
                return iter([segment('real words', 1, 10), segment('fake tail', 10, 15)]), SimpleNamespace(language='en')
        rows, _ = transcribe_overlapping(Model(), np.ones(5 * 16000), 'en', {})
        result = list(rows)
        self.assertTrue(all(0 <= s.start < s.end <= 5 for s in result))
        self.assertEqual(len(result), 1)

    def test_infinite_padded_tail_is_not_collected(self):
        consumed = []
        class Model:
            def transcribe(self, clip, **options):
                def rows():
                    yield segment('real first words', 1, 3)
                    while True:
                        consumed.append(1)
                        yield segment('An invented sentence on the padded tail', 4.8, 4.9)
                return rows(), SimpleNamespace(language='en')
        rows, _ = transcribe_overlapping(Model(), np.ones(5 * 16000), 'en', {})
        self.assertEqual([s.text for s in rows], ['real first words'])
        self.assertEqual(len(consumed), 1)

    def test_hallucinated_words_inside_digital_silence_are_rejected(self):
        class Model:
            def transcribe(self, clip, **options):
                return iter([segment('invented silence words', 1, 4), segment('real quiet words', 12, 16)]), SimpleNamespace(language='ru')
        audio = np.zeros(20 * 16000)
        audio[12 * 16000:] = 1e-8  # Do not impose a speech/energy threshold on quiet singing.
        rows, _ = transcribe_overlapping(Model(), audio, 'ru', {})
        self.assertEqual([s.text for s in rows], ['real quiet words'])

    def test_empty_intro_is_retried_even_when_later_windows_have_words(self):
        calls = []
        class Model:
            def transcribe(self, clip, **options):
                calls.append(options)
                if len(calls) == 1:
                    return iter([]), SimpleNamespace(language='ru')
                return iter([segment('early sung words', 1, 4)]), SimpleNamespace(language='ru')
        rows, _ = transcribe_overlapping(Model(), np.ones(34 * 16000), 'ru',
                                        {'no_speech_threshold': .85}, retry_empty=True)
        result = list(rows)
        self.assertEqual(result[0].start, 1)
        self.assertEqual(result[0].text, 'early sung words')
        self.assertEqual(len(calls), 3)
        self.assertIsNone(calls[1]['no_speech_threshold'])
        self.assertEqual(calls[2]['no_speech_threshold'], .85)


if __name__ == '__main__':
    unittest.main()
