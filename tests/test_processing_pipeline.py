import tempfile
import unittest
import wave
import json
import subprocess
import shutil
from pathlib import Path
from unittest import mock

import music_metadata
from easy_music_process import normalize_music_file, process_music
from lyrics_engine import LyricsResult, LyricsService, TranscriptSegment
from lyrics_engine.providers import MockLyricsProvider
from mutagen.id3 import ID3
from PIL import Image


class FailingLyricsProvider:
    def transcribe(self, *args, **kwargs):
        raise RuntimeError("forced lyrics failure")

class ProcessingPipelineTests(unittest.TestCase):
    def test_custom_image_is_used_for_cover_without_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "song.wav"
            custom = root / "my-cover.jpg"
            _write_silence(source)
            Image.new("RGB", (320, 180), "#6b4fc4").save(custom)
            with mock.patch("easy_music_process.music2picture.make_covers") as generated, \
                 mock.patch("easy_music_process.music2picture.require_ffmpeg"), \
                 mock.patch("easy_music_process.music2picture.embed_cover"):
                process_music(
                    source,
                    root / "out",
                    process_steps={"cover"},
                    custom_cover_path=custom,
                    cover_size=256,
                    embed_cover=False,
                )
            generated.assert_not_called()
            result = root / "out" / "covers" / "song_cover_256.png"
            self.assertTrue(result.is_file())
            with Image.open(result) as image:
                self.assertEqual(image.size, (256, 256))

    def test_lyrics_stage_reports_real_progress_and_saved_counts(self):
        result = LyricsResult(text="Synthetic test lyric line", source="mock",
                              segments=(TranscriptSegment(.1, 2, "Synthetic test lyric line", .95),))
        service = LyricsService(provider=MockLyricsProvider(result))
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "song.wav"
            _write_silence(source)
            process_music(source, root / "out", process_steps={"lyrics"}, lyrics_service=service,
                          lyrics_progress=lambda stage, data: events.append((stage, data)))
        stages = [stage for stage, _ in events]
        self.assertEqual(stages, ["started", "file_started", "transcribing", "saving", "saved", "completed"])
        self.assertEqual(events[2][1]["audio_end"], 2)
        self.assertEqual(events[2][1]["duration"], 3)
        self.assertEqual(events[-1][1], dict(total=1, saved=1, preserved=0, uncertain=0, failed=0))

    def test_lyrics_batch_counts_errors_uncertainty_and_preserved_text(self):
        from lyrics_engine import recognize_batch
        service = mock.Mock()
        service.load_existing.return_value = None
        service.recognize.side_effect = [RuntimeError("Test error"), LyricsResult(text="", instrumental=True)]
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one.wav", "two.wav"):
                _write_silence(root / name)
            recognize_batch(root, root, service=service, overwrite=True,
                            progress=lambda stage, data: events.append((stage, data)))
        self.assertEqual(events[-1], ("completed", dict(total=2, saved=0, preserved=0, uncertain=1, failed=1)))

    def test_existing_lyrics_are_counted_without_new_recognition(self):
        from lyrics_engine import recognize_batch
        result = LyricsResult(text="Existing synthetic test text", segments=(TranscriptSegment(0, 2, "Existing synthetic test text"),))
        service = mock.Mock()
        service.load_existing.return_value = result
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            staging = root / "staging"
            staging.mkdir()
            _write_silence(source)
            _write_silence(staging / source.name)
            recognize_batch(source, staging, service=service,
                            progress=lambda stage, data: events.append((stage, data)))
        service.recognize.assert_not_called()
        self.assertEqual(events[-1][1], dict(total=1, saved=0, preserved=1, uncertain=0, failed=0))

    def test_uncertain_text_is_preserved_for_review_without_embedding(self):
        result = LyricsResult(text='A synthetic practice line', review_reason='language')
        service = LyricsService(provider=MockLyricsProvider(result))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'song.wav'
            _write_silence(source)
            process_music(source, root / 'out', process_steps={'lyrics'}, lyrics_service=service)
            self.assertFalse((root / 'out/song.txt').exists())
            review = root / 'out/song.lyrics-review.txt'
            self.assertIn(result.text, review.read_text(encoding='utf-8'))

    def test_metadata_or_save_error_on_one_file_does_not_stop_165_file_batch(self):
        from lyrics_engine import recognize_batch
        result = LyricsResult(text='A synthetic practice line')
        service = mock.Mock()
        service.load_existing.side_effect = lambda path: (_ for _ in ()).throw(ValueError('Bad tags')) if path.name == 'song-000.wav' else None
        service.recognize.return_value = result
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(165):
                (root / f'song-{index:03d}.wav').touch()
            def save(path, *_args):
                if path.name == 'song-080.wav':
                    raise OSError('File locked')
            with mock.patch('lyrics_engine.batch.save_lyrics', side_effect=save):
                recognize_batch(root, root, service=service,
                                progress=lambda stage, data: events.append((stage, data)))
        self.assertEqual(events[-1][1], dict(total=165, saved=163, preserved=0, uncertain=0, failed=2))

    def test_owned_batch_service_is_closed_even_when_cancelled(self):
        from lyrics_engine import recognize_batch
        with mock.patch('lyrics_engine.batch.LyricsService') as factory, \
             mock.patch('lyrics_engine.batch._recognize_batch', side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                recognize_batch('source', 'staging')
        factory.return_value.close.assert_called_once()

    def test_disabled_cover_lyrics_skip_lookup_but_keep_recognition_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "song.wav"
            _write_silence(source)
            with mock.patch("lyrics_engine.LyricsService.load_existing") as load, \
                 mock.patch("easy_music_process.music2picture.require_ffmpeg"), \
                 mock.patch("easy_music_process.music2picture.make_covers", return_value=[]) as covers, \
                 mock.patch("easy_music_process.music2picture.apply_generated_covers"), \
                 mock.patch("lyrics_engine.recognize_batch", return_value={}) as recognize:
                process_music(source, root / "out", process_steps={"cover", "lyrics"},
                              cover_lyrics_text="Editor test text", use_lyrics_for_cover=False)
            load.assert_not_called()
            recognize.assert_called_once()
            self.assertIs(covers.call_args.kwargs["use_lyrics_for_cover"], False)
            self.assertEqual(covers.call_args.kwargs["lyrics_text"], "")
            self.assertEqual(covers.call_args.kwargs["lyrics_lookup"], {})

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_mp3_lyrics_are_embedded_after_cover_without_lrc_sidecar(self):
        result = LyricsResult(
            text="Первая строка песни\nВторая строка песни",
            segments=(
                TranscriptSegment(0.2, 1.5, "Первая строка песни", .95),
                TranscriptSegment(1.6, 2.9, "Вторая строка песни", .95),
            ),
            language="ru", source="mock",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "song.mp3"
            subprocess.run([
                "ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=3", "-c:a", "libmp3lame", str(source),
            ], check=True, capture_output=True)
            output = root / "out"
            process_music(
                source, output, process_steps={"cover", "lyrics"}, cover_size=128,
                cover_text_mode="none", lyrics_format="lrc", overwrite_lyrics=True,
                lyrics_service=LyricsService(provider=MockLyricsProvider(result)),
            )
            ready = output / source.name
            tags = ID3(ready)
            self.assertTrue(tags.getall("APIC"))
            self.assertIn("[00:01.60]Вторая строка песни", tags.getall("USLT")[0].text)
            self.assertFalse((output / "song.lrc").exists())
            loaded = LyricsService(metadata_reader=music_metadata.read_all_metadata).load_existing(ready)
            self.assertEqual(loaded.text, result.text)
            self.assertEqual(len(loaded.segments), 2)

    def test_metadata_and_duration_do_not_need_ffprobe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tags.mp3"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-metadata", "title=Проверка", "-metadata", "genre=Pop", str(path),
                ],
                check=True,
            )
            tags = music_metadata.read_all_metadata(path)
            self.assertEqual(tags["title"], "Проверка")
            self.assertEqual(tags["genre"], "Pop")
            self.assertAlmostEqual(normalize_music_file.probe_duration(path), 1.0, delta=0.1)

    def test_cover_analysis_and_generation_happen_before_remaining_outputs(self):
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "song.wav"
            _write_silence(source)

            def normalize(_source, staging, **_kwargs):
                events.append("audio")
                Path(staging).mkdir(parents=True, exist_ok=True)

            with (
                mock.patch("easy_music_process.music2picture.make_covers", side_effect=lambda *a, **k: events.append("cover")),
                mock.patch("easy_music_process.normalize_music_file.normalize_music", side_effect=normalize),
                mock.patch("easy_music_process.music_metadata.update_music_metadata", side_effect=lambda *a, **k: events.append("metadata")),
                mock.patch("easy_music_process.music_metadata.require_ffmpeg"),
                mock.patch("easy_music_process.music2picture.require_ffmpeg"),
                mock.patch("lyrics_engine.recognize_batch", side_effect=lambda *a, **k: events.append("lyrics") or {}),
                mock.patch("easy_music_process.music2picture.apply_generated_covers", side_effect=lambda *a, **k: events.append("attach")),
            ):
                process_music(source, root / "out", process_steps={"audio", "metadata", "lyrics", "cover"})
        self.assertEqual(events, ["cover", "audio", "metadata", "attach", "lyrics"])

    def test_lyrics_is_an_independent_batch_stage(self):
        result = LyricsResult(
            text="Это настоящий тестовый текст песни",
            segments=(TranscriptSegment(0, 3, "Это настоящий тестовый текст песни", .95),),
            source="mock",
        )
        service = LyricsService(provider=MockLyricsProvider(result))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            for name in ("one.wav", "two.wav"):
                with wave.open(str(source / name), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(8000)
                    audio.writeframes(b"\0\0" * 24000)
            process_music(
                source,
                output,
                process_steps={"lyrics"},
                lyrics_service=service,
                lyrics_format="txt",
            )
            self.assertTrue((output / "one.txt").is_file())
            self.assertTrue((output / "two.txt").is_file())
            self.assertTrue((output / "one.wav").is_file())

    def test_instrumental_does_not_create_garbage_sidecar(self):
        service = LyricsService(provider=MockLyricsProvider(LyricsResult(text="oh", instrumental=False, source="mock")))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "instrumental.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\0\0" * 8000)
            process_music(source, root / "out", process_steps={"lyrics"}, lyrics_service=service)
            self.assertFalse((root / "out" / "instrumental.txt").exists())

    def test_existing_lyrics_reach_cover_semantics_before_generation(self):
        result = LyricsResult(
            text="ночной поезд уходит сквозь дождь по дороге домой",
            segments=(TranscriptSegment(0, 3, "ночной поезд уходит сквозь дождь по дороге домой", .95),),
            source="mock",
        )
        service = LyricsService(provider=MockLyricsProvider(result))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "song.wav"
            _write_silence(source)
            source.with_suffix(".txt").write_text(result.text, encoding="utf-8")
            output = root / "out"
            process_music(
                source,
                output,
                process_steps={"lyrics", "cover"},
                lyrics_service=service,
                cover_size=128,
            )
            profile_path = output / "covers" / ".sonicforge" / "song_cover_128.profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertIn("analysis_bundle", profile)
            self.assertTrue((output / "song.txt").is_file())

    def test_lyrics_failure_does_not_block_cover(self):
        service = LyricsService(provider=FailingLyricsProvider())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "song.wav"
            _write_silence(source)
            output = root / "out"
            process_music(
                source,
                output,
                process_steps={"lyrics", "cover"},
                lyrics_service=service,
                cover_size=128,
            )
            self.assertTrue((output / "covers" / "song_cover_128.png").is_file())


def _write_silence(path):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 24000)

if __name__ == "__main__":
    unittest.main()
