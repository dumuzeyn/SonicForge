import unittest

from scripts.compare_song_reference import edit_distance, normalize


class SoundReferenceComparisonTests(unittest.TestCase):
    def test_russian_sound_spelling_and_latin_use_same_comparison_alphabet(self):
        self.assertEqual(normalize("Привет, test!"), "privettest")
        self.assertEqual(normalize("Ха ца ча ша"), "khatsachasha")
        self.assertEqual(normalize("k' q"), "kk")

    def test_missing_and_extra_sounds_are_counted_not_corrected(self):
        self.assertEqual(edit_distance("abc", "axc"), 1)
        self.assertEqual(edit_distance("abc", "abcabc"), 3)
        self.assertEqual(edit_distance("abc", ""), 3)

    def test_line_matching_ignores_arrangement_but_not_wrong_sounds(self):
        self.assertEqual(edit_distance("abc", "xyzabcxyz", substring=True), 0)
        self.assertGreater(edit_distance("abc", "xyzxyz", substring=True), 0)
