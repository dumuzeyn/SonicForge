import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audio_tags import ID3Frame, read_id3, read_metadata, text_frame, update_id3, _size_bytes


class AudioTagTests(unittest.TestCase):
    def test_temporary_windows_lock_is_retried_without_losing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'song.mp3'
            path.write_bytes(b'original MPEG audio')
            original_replace = Path.replace
            attempts = []
            def replace(temporary, target):
                attempts.append(True)
                if len(attempts) == 1:
                    error = PermissionError('Temporary sharing violation')
                    error.winerror = 32
                    raise error
                return original_replace(temporary, target)
            with patch.object(Path, 'replace', replace), patch('audio_tags.time.sleep'):
                update_id3(path, [text_frame('USLT', 'A synthetic practice line')])
            self.assertEqual(len(attempts), 2)
            self.assertTrue(path.read_bytes().endswith(b'original MPEG audio'))

    def test_retry_never_overwrites_a_file_changed_while_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'song.mp3'
            path.write_bytes(b'original MPEG audio')
            def replace(temporary, target):
                path.write_bytes(b'changed outside SonicForge')
                error = PermissionError('Temporary sharing violation')
                error.winerror = 32
                raise error
            with patch.object(Path, 'replace', replace), patch('audio_tags.time.sleep'):
                with self.assertRaises(OSError):
                    update_id3(path, [text_frame('USLT', 'A synthetic practice line')])
            self.assertEqual(path.read_bytes(), b'changed outside SonicForge')

    def test_both_versions_keep_unknown_frames_and_audio_bytes(self):
        for version in (3, 4):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'song.mp3'
                payload = bytes(range(256)) * 80
                frame = b'PRIV' + (_size_bytes(6) if version == 4 else (6).to_bytes(4, 'big')) + b'\0\0abcdef'
                path.write_bytes(b'ID3' + bytes((version, 0, 0)) + _size_bytes(len(frame)) + frame + payload)
                update_id3(path, [text_frame('TIT2', 'Учебный пример'), text_frame('USLT', 'Hello\nПривет', language='rus')])
                new_version, offset, frames = read_id3(path)
                self.assertEqual(new_version, version)
                self.assertEqual(frames[0], ID3Frame('PRIV', b'abcdef'))
                self.assertEqual(frames[1].text, 'Учебный пример')
                self.assertEqual(frames[2].text, 'Hello\nПривет')
                self.assertEqual(frames[2].language, 'rus')
                self.assertEqual(hashlib.sha256(path.read_bytes()[offset:]).digest(), hashlib.sha256(payload).digest())

    def test_custom_metadata_replacement_preserves_unrelated_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'song.mp3'
            path.touch()
            update_id3(path, [text_frame('TXXX', 'en', 'SONICFORGE_LYRICS_ALPHABET'),
                              text_frame('TXXX', 'keep', 'OTHER'), text_frame('USLT', 'Old')])
            update_id3(path, [text_frame('USLT', 'Новый текст')], remove_names=('USLT',),
                       remove_custom=('SONICFORGE_LYRICS_ALPHABET',))
            _, _, frames = read_id3(path)
            self.assertEqual([(frame.name, frame.text) for frame in frames], [('TXXX', 'keep'), ('USLT', 'Новый текст')])
            self.assertEqual(read_metadata(path)['lyrics'], 'Новый текст')
            self.assertFalse(list(Path(directory).glob('.sonicforge-tags-*')))

    def test_malformed_or_complex_tags_are_never_modified(self):
        malformed = [b'ID3\x03\0\0\x80\0\0\0', b'ID3\x03\0\x80\0\0\0\0',
                     b'ID3\x03\0\0\x7f\x7f\x7f\x7f', b'ID3\x03\0\0\0\0\0\x05abc',
                     b'ID3\x02\0\0\0\0\0\0']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'song.mp3'
            for original in malformed:
                with self.subTest(original=original):
                    path.write_bytes(original)
                    with self.assertRaises(ValueError):
                        update_id3(path, [text_frame('USLT', 'Test')])
                    self.assertEqual(path.read_bytes(), original)

    def test_utf8_and_utf16be_frames_read_correctly(self):
        for encoding, codec in ((0, 'latin-1'), (1, 'utf-16'), (2, 'utf-16-be'), (3, 'utf-8')):
            text = 'Hello' if encoding == 0 else 'Привет'
            self.assertEqual(ID3Frame('TIT2', bytes((encoding,)) + text.encode(codec)).text, text)


if __name__ == '__main__':
    unittest.main()
