import threading
import unittest
import numpy as np
from types import SimpleNamespace

from lyrics_engine import TranscriptSegment
from lyrics_engine.verification import (choose_verified_segment, repair_repeated_words, verified_segments,
                                        confirmed_opening, trim_covered_segment)


def segment(text, start=10.0, end=15.0, probabilities=None, logprob=-0.3):
    words = text.split()
    probabilities = probabilities or [0.95] * len(words)
    span = (end - start) / len(words)
    return SimpleNamespace(text=text, start=start, end=end, avg_logprob=logprob,
        words=[SimpleNamespace(word=word, start=start + i * span, end=start + (i + 1) * span,
                               probability=probabilities[i]) for i, word in enumerate(words)])


class LyricsVerificationTests(unittest.TestCase):
    def test_skipped_opening_is_recovered_without_duplicate_main_fragments(self):
        opening = segment("Первая полная строка звучит раньше", start=20.8, end=26.3)
        next_line = segment("Следующая полная строка песни", start=26.7, end=31.7)
        old_fragment = segment("Первая строка", start=27.2, end=29.98)
        old_next = segment("строка песни", start=30, end=31.72)
        following = segment("Дальше продолжается песня", start=34, end=39)
        calls = []
        class Model:
            def transcribe(self, _audio, **options):
                # The cropped model outputs local time; no expected text prompt.
                start = (15.2, 18.2)[len(calls)]
                calls.append(options)
                return iter([segment(opening.text, opening.start-start, opening.end-start),
                             segment(next_line.text, next_line.start-start, next_line.end-start)]), None
        result = list(verified_segments(Model(), np.ones(60*16000, dtype=np.float32),
                                        [old_fragment, old_next, following], {'language': 'ru'}, limit=4,
                                        audio_duration=60))
        self.assertEqual([r.text for r in result], [opening.text, next_line.text, following.text])
        self.assertAlmostEqual(result[0].start, 20.8)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all('initial_prompt' not in call and call['language'] == 'ru' for call in calls))

    def test_opening_requires_two_matching_acoustic_contexts(self):
        original = segment('Неполная строка', 27, 30)
        opening = segment('Полная первая строка звучит гораздо раньше', 21, 26)
        self.assertEqual(confirmed_opening(original, [opening], []), [])
        other = segment('Совсем другая фраза без общей части', 21, 26)
        self.assertEqual(confirmed_opening(original, [opening], [other]), [])
        short = segment('Лишние слова', 21, 26)
        self.assertEqual(confirmed_opening(original, [short], [short]), [])
        weak = segment(opening.text, 21, 26, [.3] * 7)
        self.assertEqual(confirmed_opening(original, [weak], [weak]), [])
        shifted = segment(opening.text, 16, 20)
        self.assertEqual(confirmed_opening(original, [opening], [shifted]), [])
        self.assertEqual(confirmed_opening(original, [opening], [opening], lambda _: True), [])

    def test_recovered_prefix_keeps_timed_main_suffix(self):
        raw = segment('Первая строка потом вторая строка', 20, 32)
        trimmed = trim_covered_segment(raw, 24)
        self.assertEqual(trimmed.text, 'потом вторая строка')
        self.assertEqual(trimmed.start, 24.8)
        self.assertEqual(raw.text, 'Первая строка потом вторая строка')
        self.assertIsNone(trim_covered_segment(raw, 32))
        tail = segment('Полная строка потом вторая строка', 20, 31.18)
        fragment = segment('вторая строка', 30, 31.72)
        self.assertIsNone(trim_covered_segment(fragment, tail.end, tail))
        raw.words = None
        self.assertIs(trim_covered_segment(raw, 24), raw)

    def test_verification_stops_after_nearby_evidence(self):
        consumed = []
        original = segment("Тихая строка песни", probabilities=[0.5, 0.9, 0.9])
        class Model:
            def transcribe(self, _audio, **_options):
                def candidates():
                    for start in (10, 20, 25, 30):
                        consumed.append(start)
                        yield segment("Тихая строка песни", start=start, end=start + 5)
                return candidates(), None
        self.assertEqual(list(verified_segments(Model(), "file.mp3", [original], {})), [original])
        self.assertEqual(consumed, [10, 20])

    def test_repeated_context_repairs_weak_word_without_changing_timestamps(self):
        raw = [segment("Снова вижу этот сон, и знаю причину", start=i * 40, end=i * 40 + 7,
                       probabilities=[0.95, 0.95, 0.95, 0.7, 0.95, 0.95, 0.95]) for i in range(2)]
        raw.append(segment("Снова вижу этот солнце, и знаю причину", start=80, end=87,
                           probabilities=[0.95, 0.95, 0.95, 0.8, 0.95, 0.95, 0.95]))
        originals = [TranscriptSegment(r.start, r.end, r.text, 0.9) for r in raw]
        result = repair_repeated_words(originals, [r.words for r in raw])
        self.assertEqual(result[2].text, originals[0].text)
        self.assertEqual([(r.start, r.end, r.confidence) for r in result], [(r.start, r.end, r.confidence) for r in originals])
        self.assertIn("солнце,", originals[2].text)

    def test_repeated_context_does_not_overwrite_confident_or_different_lines(self):
        raw = [segment("Снова вижу этот свет и знаю причину", start=i * 40, end=i * 40 + 7) for i in range(2)]
        raw.append(segment("Снова вижу этот след и знаю причину", start=80, end=87))
        raw.append(segment("Снова вижу этот след и другую картину", start=120, end=127,
                           probabilities=[0.95, 0.95, 0.95, 0.6, 0.95, 0.95, 0.95]))
        originals = [TranscriptSegment(r.start, r.end, r.text) for r in raw]
        self.assertEqual(repair_repeated_words(originals, [r.words for r in raw]), originals)

    def test_repeated_context_does_not_count_adjacent_duplicates_or_unknown_confidence(self):
        raw = [segment("Снова вижу этот свет и знаю причину", start=i, end=i + 7) for i in range(2)]
        raw.append(segment("Снова вижу этот след и знаю причину", start=80, end=87,
                           probabilities=[0.95, 0.95, 0.95, 0.6, 0.95, 0.95, 0.95]))
        originals = [TranscriptSegment(r.start, r.end, r.text) for r in raw]
        self.assertEqual(repair_repeated_words(originals, [r.words for r in raw]), originals)
        self.assertEqual(repair_repeated_words(originals, [(), (), ()]), originals)

    def test_unconfirmed_anomaly_is_removed_only_with_positive_following_voice(self):
        original = segment("Случайная фраза", start=28.2, end=29.7, probabilities=[0.45, 0.99])
        original.words[-1].start = 29.64
        actual = segment("Первая настоящая строка песни", start=30.3, end=35.0, logprob=-0.18)
        self.assertIsNone(choose_verified_segment(original, [actual], after_pause=True))
        self.assertIs(choose_verified_segment(original, [], after_pause=True), original)

    def test_real_opening_is_not_removed_when_shifted_context_confirms_it(self):
        original = segment("Тихая строка песни", start=28, end=30, probabilities=[0.45, 0.9, 0.95])
        confirmation = segment("Тихая строка песни", start=28.2, end=30.1)
        self.assertIs(choose_verified_segment(original, [confirmation], after_pause=True), original)

    def test_homophone_changes_only_with_better_acoustic_evidence(self):
        original = segment("Этот солнце сегодня кажется очень странным", probabilities=[0.9, 0.70, 0.9, 0.9, 0.9, 0.9], logprob=-0.33)
        corrected = segment("Этот сон сегодня кажется очень странным", probabilities=[0.9, 0.73, 0.9, 0.9, 0.9, 0.9], logprob=-0.23)
        self.assertIs(choose_verified_segment(original, [corrected]), corrected)
        corrected.words[1].probability = 0.60
        self.assertIs(choose_verified_segment(original, [corrected]), original)

    def test_high_confidence_word_and_unrelated_line_are_not_rewritten(self):
        original = segment("Этот свет сегодня кажется очень странным")
        other = segment("Этот след сегодня кажется очень странным", logprob=-0.1)
        self.assertIs(choose_verified_segment(original, [other]), original)
        unrelated = segment("Совсем другая строка без общего смысла", logprob=-0.01)
        self.assertIs(choose_verified_segment(original, [unrelated]), original)

    def test_shifted_time_range_is_preserved_and_false_line_never_streams(self):
        original = segment("Случайная фраза", start=28.2, end=29.7, probabilities=[0.45, 0.99])
        original.words[-1].start = 29.64
        actual = segment("Первая настоящая строка песни", start=30.3, end=35.0, logprob=-0.18)
        calls = []
        class Model:
            def transcribe(self, audio, **options):
                calls.append((audio, options))
                return iter([actual]), None
        result = list(verified_segments(Model(), "original.mp3", iter([original, actual]), {"language": "en", "vad_filter": False}))
        self.assertEqual(result, [actual])
        self.assertEqual(calls[0][0], "original.mp3")
        self.assertEqual(calls[0][1]["clip_timestamps"], [23.2, 53.2])
        self.assertEqual(calls[0][1]["language"], "en")
        self.assertFalse(calls[0][1]["vad_filter"])

    def test_verification_is_bounded(self):
        calls = []
        class Model:
            def transcribe(self, _audio, **_options):
                calls.append(True)
                return iter([]), None
        originals = [segment("Тихая строка песни", start=i * 5, end=i * 5 + 4, probabilities=[0.5, 0.9, 0.9]) for i in range(20)]
        result = list(verified_segments(Model(), "file.mp3", originals, {}, limit=3))
        self.assertEqual(result, originals)
        self.assertEqual(len(calls), 3)

    def test_confident_intro_invention_requires_two_acoustic_checks(self):
        invented = segment("Лишние слова", start=27.0, end=29.0)
        actual = segment("Настоящая первая строка песни", start=30.0, end=35.0, logprob=-.15)
        calls = []
        class Model:
            def transcribe(self, _audio, **options):
                calls.append(options)
                return iter([actual]), None
        result = list(verified_segments(Model(), "song.wav", [invented, actual], {}))
        self.assertEqual(result, [actual])
        self.assertGreaterEqual(len(calls), 2)
        self.assertLessEqual(len(calls), 3)
        self.assertNotEqual(calls[0]['clip_timestamps'], calls[1]['clip_timestamps'])
        self.assertTrue(all(call['temperature'] == 0.0 for call in calls))

    def test_second_context_preserves_real_confident_opening(self):
        opening = segment("Настоящие слова", start=27.0, end=29.0)
        following = segment("Настоящая следующая строка песни", start=30.0, end=35.0, logprob=-.15)
        answers = iter([[following], [opening, following]])
        class Model:
            def transcribe(self, _audio, **options):
                return iter(next(answers)), None
        self.assertEqual(list(verified_segments(Model(), "song.wav", [opening, following], {})),
                         [opening, following])

    def test_inserted_prefix_is_removed_without_losing_confirmed_words_or_timing(self):
        original = segment("Лишнее слово настоящая строка песни", start=20, end=25,
                           probabilities=[.4, .5, .95, .95, .95])
        confirmed = segment("Настоящая строка песни", start=22, end=25, logprob=-.2)
        cleaned = choose_verified_segment(original, [confirmed])
        self.assertEqual(cleaned.text, "настоящая строка песни")
        self.assertEqual((cleaned.start, cleaned.end), (22, 25))
        self.assertEqual(len(cleaned.words), 3)
        self.assertEqual(original.text, "Лишнее слово настоящая строка песни")

    def test_prefix_is_kept_when_confident_or_shifted_to_another_time(self):
        original = segment("Тихое слово настоящая строка песни", start=20, end=25)
        confirmed = segment("Настоящая строка песни", start=22, end=25, logprob=-.2)
        self.assertIs(choose_verified_segment(original, [confirmed]), original)
        original.words[0].probability = .3
        original.words[1].probability = .3
        confirmed.start = 23
        self.assertIs(choose_verified_segment(original, [confirmed]), original)

    def test_cancel_during_verification_prevents_output(self):
        cancelled = threading.Event()
        class Model:
            def transcribe(self, _audio, **_options):
                cancelled.set()
                return iter([segment("Тихая строка песни")]), None
        with self.assertRaises(InterruptedError):
            list(verified_segments(Model(), "file.mp3", [segment("Тихая строка песни", probabilities=[0.5, 0.9, 0.9])], {}, cancelled))


if __name__ == "__main__":
    unittest.main()
