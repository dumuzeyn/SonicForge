from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from audio_tags import ID3Frame, read_id3, read_metadata, probe_audio, text_frame, update_id3
from music_metadata import write_metadata, clear_metadata, lyrics_snapshot


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class PreserveLyricsTests(unittest.TestCase):
    def make_song(self, root, extension='.mp3'):
        path = Path(root)/('song'+extension)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=220:duration=1', '-metadata', 'title=Old title',
                        '-metadata', 'lyrics=  Original\nLyrics  ', str(path)], check=True)
        return path

    def test_replace_and_clear_keep_exact_plain_timed_and_language_frames(self):
        for version in (3, 4):
            for action in ('replace', 'clear'):
                with self.subTest(version=version, action=action), tempfile.TemporaryDirectory() as root:
                    path = self.make_song(root)
                    frames = [text_frame('USLT', '[00:01.25]Original lyrics', language='rus'),
                              text_frame('USLT', 'Second language', language='eng'),
                              ID3Frame('SYLT', b'\0eng\x02\x01\0timed line\0\0\0\x03\xe8'),
                              text_frame('TXXX', 'ru', 'SONICFORGE_LYRICS_LANGUAGE'),
                              text_frame('TXXX', 'latin', 'SONICFORGE_LYRICS_ALPHABET')]
                    update_id3(path, frames, remove_names=('USLT',), target_version=version)
                    expected = lyrics_snapshot(path)
                    if action == 'replace':
                        write_metadata(path, 'New title', 'Rock', overwrite_all_metadata=True,
                                       extra_metadata={'lyrics': 'Do not write this'}, preserve_lyrics=True)
                        self.assertEqual(read_metadata(path)['title'], 'New title')
                    else:
                        clear_metadata(path, preserve_lyrics=True)
                        self.assertNotIn('title', read_metadata(path))
                    self.assertEqual(lyrics_snapshot(path), expected)

    def test_disabled_setting_can_replace_or_remove_lyrics(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.make_song(root)
            write_metadata(path, 'Title', 'Rock', extra_metadata={'lyrics': 'New text'}, preserve_lyrics=False)
            self.assertEqual(read_metadata(path)['lyrics'], 'New text')
            clear_metadata(path, preserve_lyrics=False)
            self.assertFalse(lyrics_snapshot(path)[1])

    def test_empty_original_lyrics_do_not_receive_additional_lyrics(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.make_song(root)
            clear_metadata(path)
            write_metadata(path, 'Title', 'Rock', extra_metadata={'lyrics': 'Ignored'}, preserve_lyrics=True)
            self.assertNotIn('lyrics', read_metadata(path))

    def test_other_containers_keep_exact_lyric_text(self):
        for extension in ('.flac', '.ogg', '.m4a'):
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as root:
                path = self.make_song(root, extension)
                before = lyrics_snapshot(path)[2]
                self.assertTrue(before)
                write_metadata(path, 'Title', 'Rock', overwrite_all_metadata=True,
                               preserve_lyrics=True, extra_metadata={'lyrics': 'Ignored'})
                self.assertEqual(lyrics_snapshot(path)[2], before)
                clear_metadata(path, preserve_lyrics=True)
                self.assertEqual(lyrics_snapshot(path)[2], before)

    def test_wav_without_lyric_tags_is_updated_without_injecting_text(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.make_song(root, '.wav')
            self.assertFalse(lyrics_snapshot(path)[2])
            write_metadata(path, 'Title', 'Rock', preserve_lyrics=True,
                           extra_metadata={'lyrics': 'Ignored'})
            self.assertFalse(lyrics_snapshot(path)[2])


if __name__ == '__main__':
    unittest.main()
