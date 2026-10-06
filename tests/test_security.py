import tempfile
import unittest
import wave
from pathlib import Path

from PIL import Image

from security import UnsafeMediaError, validate_audio_file, validate_image_file, validate_output_directory


class SecurityTests(unittest.TestCase):
    def test_audio_extension_must_match_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "attack.mp3"
            fake.write_bytes(b"MZ" + b"\0" * 100)
            with self.assertRaises(UnsafeMediaError):
                validate_audio_file(fake)
            real = root / "song.wav"
            with wave.open(str(real), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\0\0" * 100)
            self.assertEqual(validate_audio_file(real), real.resolve())

    def test_image_is_decoded_and_verified_not_trusted_by_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "cover.png"
            fake.write_bytes(b"not an image")
            with self.assertRaises(UnsafeMediaError):
                validate_image_file(fake)
            real = root / "cover.png"
            Image.new("RGB", (64, 64), "purple").save(real)
            self.assertEqual(validate_image_file(real), real.resolve())

    def test_output_cannot_replace_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve()
            with self.assertRaises(UnsafeMediaError):
                validate_output_directory(source, source)


if __name__ == "__main__":
    unittest.main()
