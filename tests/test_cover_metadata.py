import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from mutagen.id3 import ID3

from audio_tags import ID3Frame, _size_bytes, read_id3, text_frame
from easy_music_process import process_music
import music2picture


class CoverMetadataTests(unittest.TestCase):
    @staticmethod
    def tagged_song(path, version=3, audio=b'unchanged MPEG data'):
        # Preserve even tags that FFmpeg does not expose as ordinary metadata.
        frames = (
            text_frame('TIT2', 'Original title'),
            text_frame('TPE1', 'Original artist'),
            text_frame('TALB', 'Original album'),
            text_frame('TRCK', '4/12'),
            text_frame('USLT', 'Первая строка\nВторая строка', language='rus'),
            text_frame('USLT', 'First line\nSecond line', language='eng'),
            ID3Frame('SYLT', b'\x03eng\x02\x01\x00Timed line\x00\x00\x00\x00\xc8'),
            ID3Frame('COMM', b'\x03eng\x00Original comment'),
            text_frame('TXXX', 'ru', 'SONICFORGE_LYRICS_LANGUAGE'),
            text_frame('TXXX', 'keep this', 'CUSTOM_FIELD'),
            ID3Frame('PRIV', b'owner\x00private data', b'\x40\x00'),
            ID3Frame('XABC', b'unknown application metadata'),
            ID3Frame('APIC', b'\x00image/png\x00\x03\x00old cover'),
        )
        body = b''.join(
            frame.name.encode('ascii')
            + (_size_bytes(len(frame.payload)) if version == 4
               else len(frame.payload).to_bytes(4, 'big'))
            + frame.flags + frame.payload
            for frame in frames
        )
        path.write_bytes(b'ID3' + bytes((version, 0, 0)) + _size_bytes(len(body))
                         + body + audio)
        return frames

    def test_cover_replacement_keeps_all_other_frames_and_audio_bytes(self):
        for version in (3, 4):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                song, picture = root / 'song.mp3', root / 'cover.png'
                audio = bytes(range(256)) * 128 + b'TAG' + b'legacy tag'.ljust(125, b'\x00')
                original_frames = self.tagged_song(song, version, audio)
                Image.new('RGBA', (32, 32), '#673ab780').save(picture)
                with patch('music2picture.subprocess.run') as remux:
                    self.assertTrue(music2picture.embed_cover(song, picture))
                remux.assert_not_called()
                actual_version, offset, frames = read_id3(song)
                self.assertEqual(actual_version, version)
                self.assertEqual(tuple(f for f in frames if f.name != 'APIC'),
                                 tuple(f for f in original_frames if f.name != 'APIC'))
                self.assertEqual(song.read_bytes()[offset:], audio)
                covers = ID3(song).getall('APIC')
                self.assertEqual(len(covers), 1)
                self.assertEqual(covers[0].type, 3)
                self.assertEqual(covers[0].mime, 'image/png')
                self.assertEqual(covers[0].data, picture.read_bytes())
                self.assertFalse(list(root.glob('.sonicforge-tags-*')))

    def test_untagged_audio_and_repeated_cover_changes_do_not_duplicate_covers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            song, picture = root / 'song.mp3', root / 'cover.jpg'
            song.write_bytes(b'original audio without ID3')
            for color in ('red', 'blue'):
                Image.new('RGB', (32, 32), color).save(picture)
                music2picture.embed_cover(song, picture)
                _, offset, frames = read_id3(song)
                self.assertEqual(song.read_bytes()[offset:], b'original audio without ID3')
                self.assertEqual(len(frames), 1)
                cover = ID3(song).getall('APIC')[0]
                self.assertEqual(cover.mime, 'image/jpeg')
                self.assertEqual(cover.data, picture.read_bytes())

    def test_webp_is_converted_to_png_without_touching_other_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            song, picture = root / 'song.mp3', root / 'cover.webp'
            original_frames = self.tagged_song(song)
            Image.new('RGBA', (32, 32), '#673ab780').save(picture)
            music2picture.embed_cover(song, picture)
            _, _, frames = read_id3(song)
            self.assertEqual(tuple(f for f in frames if f.name != 'APIC'),
                             tuple(f for f in original_frames if f.name != 'APIC'))
            self.assertTrue(ID3(song).getall('APIC')[0].data.startswith(b'\x89PNG'))

    def test_invalid_images_or_unsupported_tag_headers_never_modify_song(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            song, picture = root / 'song.mp3', root / 'cover.png'
            self.tagged_song(song)
            picture.write_bytes(b'not an image')
            original = song.read_bytes()
            with self.assertRaises(ValueError):
                music2picture.embed_cover(song, picture)
            self.assertEqual(song.read_bytes(), original)
            Image.new('RGB', (32, 32), 'purple').save(picture)
            for header in (b'ID3\x02\x00\x00', b'ID3\x03\x00\x80', b'ID3\x04\x00\x40'):
                original = header + b'\x00' * 4 + b'original song'
                song.write_bytes(original)
                with self.assertRaises(ValueError):
                    music2picture.embed_cover(song, picture)
                self.assertEqual(song.read_bytes(), original)
            self.assertFalse(list(root.glob('.sonicforge-tags-*')))

    def test_failed_atomic_update_preserves_original_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            song, picture = root / 'song.mp3', root / 'cover.png'
            self.tagged_song(song)
            Image.new('RGB', (32, 32), 'purple').save(picture)
            original = song.read_bytes()
            with patch.object(Path, 'replace', side_effect=OSError('File is locked')):
                with self.assertRaises(OSError):
                    music2picture.embed_cover(song, picture)
            self.assertEqual(song.read_bytes(), original)
            self.assertFalse(list(root.glob('.sonicforge-tags-*')))

    def test_non_mp3_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            song = Path(directory) / 'song.flac'
            song.write_bytes(b'original data')
            self.assertFalse(music2picture.embed_cover(song, 'unused.png'))
            self.assertEqual(song.read_bytes(), b'original data')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg is required to create test audio')
    def test_cover_only_pipeline_preserves_lyrics_metadata_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, picture = root / 'song.mp3', root / 'cover.png'
            subprocess.run([
                'ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i',
                'sine=frequency=440:duration=1', '-c:a', 'libmp3lame', str(source),
            ], check=True, capture_output=True)
            _, offset, _ = read_id3(source)
            self.tagged_song(source, audio=source.read_bytes()[offset:])
            original_hash = hashlib.sha256(source.read_bytes()).digest()
            _, offset, original_frames = read_id3(source)
            original_audio = source.read_bytes()[offset:]
            Image.new('RGB', (32, 32), 'purple').save(picture)

            def generate(_source, target, **_kwargs):
                Path(target).mkdir(parents=True, exist_ok=True)
                shutil.copy2(picture, Path(target) / 'song_cover_128.png')

            for custom in (True, False):
                with self.subTest(custom=custom), patch('music2picture.make_covers', side_effect=generate), \
                     patch('lyrics_engine.recognize_batch') as recognize:
                    output = root / ('custom' if custom else 'generated')
                    process_music(source, output, process_steps={'cover'}, cover_size=128,
                                  custom_cover_path=picture if custom else None)
                    recognize.assert_not_called()
                    result = output / source.name
                    _, offset, frames = read_id3(result)
                    self.assertEqual(tuple(f for f in frames if f.name != 'APIC'),
                                     tuple(f for f in original_frames if f.name != 'APIC'))
                    self.assertEqual(result.read_bytes()[offset:], original_audio)
                    self.assertEqual(len(ID3(result).getall('USLT')), 2)
                    self.assertEqual(len(ID3(result).getall('SYLT')), 1)
                    self.assertEqual(len(ID3(result).getall('APIC')), 1)
                    self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), original_hash)


if __name__ == '__main__':
    unittest.main()
