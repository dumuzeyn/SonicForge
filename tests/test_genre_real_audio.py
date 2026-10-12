"""Real-model smoke checks; prepare the pinned public corpus first.

These known fixtures verify execution and integration, not generalization.
Quality is measured independently by tools/benchmark_genres.py.
"""
from pathlib import Path
import shutil
import tempfile
import unittest

from audio_tags import read_metadata
from genre_classifier import classify_genre, classify_batch
from music_metadata import update_music_metadata, write_metadata

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / '.sonicforge/genre-eval'


@unittest.skipUnless((CORPUS / 'clip_47127.mp3').exists(), 'Run tools/prepare_genre_evaluation.py')
class RealMusicGenreTests(unittest.TestCase):
    def test_real_neural_inference_rock_is_independent_of_filename(self):
        original = CORPUS / 'clip_47127.mp3'
        result = classify_genre(original, ['Rock', 'Classic Rock', 'Pop'])
        self.assertIn('Rock', result.genres)
        self.assertGreater(len(result.segments), 1)
        with tempfile.TemporaryDirectory() as folder:
            renamed = Path(folder) / 'Classical Nightcore.mp3'
            shutil.copyfile(original, renamed)
            other = classify_genre(renamed, ['Rock', 'Classic Rock', 'Pop'])
        self.assertEqual(result.genres, other.genres)
        self.assertEqual(result.alternatives, other.alternatives)
        self.assertEqual(other.context, ('Nightcore',))

    def test_real_house_and_electronic_batch(self):
        paths = [CORPUS/'clip_20286.mp3', CORPUS/'clip_26272.mp3']
        results = list(classify_batch(paths, ['House', 'Electronic', 'Ambient']))
        self.assertIn('House', results[0][1].genres)
        self.assertIn('Electronic', results[1][1].genres)
        self.assertTrue(all(result.model == 'MSD_musicnn' for _, result in results))

    def test_real_audio_user_tags_survive_metadata_update(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'song.mp3'
            shutil.copyfile(CORPUS/'clip_47127.mp3', path)
            write_metadata(path, 'User title', 'Anime; Classic Rock; Personal tag',
                           extra_metadata={'artist': 'User artist', 'comment': 'User comment'})
            update_music_metadata(path)
            tags = read_metadata(path)
        self.assertEqual(tags['genre'], 'Anime; Classic Rock; Personal tag')
        self.assertEqual(tags['title'], 'User title')
        self.assertEqual(tags['artist'], 'User artist')
        self.assertEqual(tags['comment'], 'User comment')


if __name__ == '__main__':
    unittest.main()
