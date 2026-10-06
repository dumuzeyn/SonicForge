import tempfile
import os
from contextlib import nullcontext
import shutil
import subprocess
import unittest
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lyrics_engine import LyricsResult, LyricsService, TranscriptSegment, load_sidecar, save_lyrics
from lyrics_engine.providers import FasterWhisperProvider, MockLyricsProvider
from lyrics_engine.service import detect_text_languages


class LyricsEngineTests(unittest.TestCase):
    def test_accuracy_model_is_lazy_cached_and_can_be_overridden(self):
        with patch.dict(os.environ, {}, clear=True), patch("faster_whisper.WhisperModel") as factory:
            provider = FasterWhisperProvider()
            self.assertEqual(provider.model_name, "large-v3-turbo")
            factory.assert_not_called()
            first = provider._get_model()
            self.assertIs(first, provider._get_model())
            factory.assert_called_once_with("large-v3-turbo", device="cpu", compute_type="int8")
        with patch.dict(os.environ, {"SONIC_FORGE_WHISPER_MODEL": "small"}):
            self.assertEqual(FasterWhisperProvider().model_name, "small")
            self.assertEqual(FasterWhisperProvider(model_name="base").model_name, "base")

    def test_recognition_does_not_filter_or_modify_original_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "original.mp3"
            audio.write_bytes(b"test audio untouched")
            with patch("subprocess.run") as process:
                with FasterWhisperProvider()._vocal_audio(audio) as prepared:
                    self.assertEqual(prepared, str(audio))
                process.assert_not_called()
            self.assertEqual(audio.read_bytes(), b"test audio untouched")
            self.assertEqual(list(Path(directory).iterdir()), [audio])

    def test_singing_options_allow_late_opening_without_vad_or_prompted_words(self):
        provider = FasterWhisperProvider()
        calls = []
        def transcribe(_audio, **options):
            calls.append(options)
            return iter([SimpleNamespace(start=28.2, end=30.0, text="Тестовая строка", no_speech_prob=0.05)]), SimpleNamespace(language="ru")
        with patch.object(provider, "available", return_value=True), \
             patch.object(provider, "_get_model", return_value=SimpleNamespace(transcribe=transcribe)):
            result = provider.transcribe("unused.mp3", language="ru")
        self.assertEqual(result.segments[0].start, 28.2)
        self.assertEqual(calls[0]["language"], "ru")
        self.assertEqual(calls[0]["max_initial_timestamp"], 30.0)
        self.assertFalse(calls[0]["vad_filter"])
        self.assertFalse(calls[0]["condition_on_previous_text"])
        self.assertTrue(calls[0]["word_timestamps"])
        self.assertEqual(calls[0]["temperature"], (0.0, 0.2, 0.4))
        self.assertNotIn("initial_prompt", calls[0])
        self.assertNotIn("hotwords", calls[0])

    def test_clear_russian_text_corrects_weak_english_label_without_fake_certainty(self):
        service = LyricsService(provider=MockLyricsProvider(LyricsResult(
            text="Это русская строка песни\nИ ещё одна русская строка",
            language="en", language_confidence=0.55,
        )))
        result = service.recognize("unused.mp3")
        self.assertEqual(result.language, "ru")
        self.assertIsNone(result.language_confidence)

    def test_uncertain_recognition_keeps_the_text_for_review(self):
        result = LyricsService(provider=MockLyricsProvider(LyricsResult(text="Привет"))).recognize("unused.mp3")
        self.assertEqual(result.text, "Привет")
        self.assertEqual(result.quality, "low")
        self.assertTrue(result.instrumental)

    def test_acoustic_language_votes_do_not_trust_one_intro_outlier(self):
        from lyrics_engine.language_detection import combine_language_predictions
        language, probability = combine_language_predictions([
            ("en", 0.99, [("en", 0.99), ("ru", 0.01)]),
            ("ru", 0.93, [("ru", 0.93), ("en", 0.07)]),
            ("ru", 0.89, [("ru", 0.89), ("en", 0.11)]),
        ])
        self.assertEqual(language, "ru")
        self.assertAlmostEqual(probability, (0.01 + 0.93 + 0.89) / 3)

    def test_language_checks_separated_windows_and_honors_cancellation(self):
        import numpy as np
        from lyrics_engine.language_detection import detect_song_language, language_windows
        calls = []
        class Model:
            def detect_language(self, audio, **options):
                calls.append((float(audio[0]), options))
                return "ru", 0.90, [("ru", 0.90), ("en", 0.10)]
        windows = language_windows(np.arange(200, dtype=np.float32), sampling_rate=1)
        self.assertEqual([start for start, _ in windows], [30.0, 90.0, 140.0])
        audio = np.linspace(0.1, 1.0, 200 * 16000, dtype=np.float32)
        self.assertEqual(detect_song_language(Model(), audio)[0], "ru")
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call[1]["language_detection_threshold"] == 1.0 for call in calls))
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            detect_song_language(Model(), audio, cancelled)

    def test_provider_streams_lines_and_uses_multi_sample_language(self):
        provider = FasterWhisperProvider()
        seen = []
        model = SimpleNamespace(transcribe=lambda *args, **kwargs: (
            iter([SimpleNamespace(start=1.0, end=3.0, text="Русская строка песни", no_speech_prob=0.01)]),
            SimpleNamespace(language=kwargs["language"], language_probability=1.0),
        ), detect_language=lambda **kwargs: None)
        with patch.object(provider, "available", return_value=True), \
             patch.object(provider, "_get_model", return_value=model), \
             patch.object(provider, "_vocal_audio", return_value=nullcontext("unused.wav")), \
             patch.object(provider, "_detect_song_language", return_value=("ru", 0.89)):
            result = provider.transcribe("unused.mp3", on_segment=seen.append)
        self.assertEqual(result.language, "ru")
        self.assertEqual(result.language_confidence, 0.89)
        self.assertEqual(tuple(seen), result.segments)

    def test_plain_manual_mp3_lyrics_do_not_get_fake_timestamps(self):
        from mutagen.id3 import ID3
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "manual.mp3"
            audio.touch()
            result = LyricsResult(text="Ручная строка без времени", language="ru")
            save_lyrics(audio, result, "uslt")
            self.assertEqual(ID3(audio).getall("USLT")[0].text, result.text)
            self.assertFalse(audio.with_suffix(".lrc").exists())

    def test_txt_and_lrc_use_same_base_name(self):
        result = LyricsResult(
            text="Первая строка\nSecond line",
            segments=(
                TranscriptSegment(1.25, 3.0, "Первая строка"),
                TranscriptSegment(65.5, 68.0, "Second line"),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "Song.wav"
            audio.touch()
            txt = save_lyrics(audio, result, "txt")
            self.assertEqual(txt.name, "Song.txt")
            txt.unlink()
            lrc = save_lyrics(audio, result, "lrc")
            self.assertEqual(lrc.name, "Song.lrc")
            self.assertIn("[01:05.50]Second line", lrc.read_text(encoding="utf-8"))
            loaded = load_sidecar(audio)
            self.assertEqual(len(loaded.segments), 2)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required to create a test MP3")
    def test_mp3_embeds_timed_lines_in_uslt_without_sidecar(self):
        from mutagen.id3 import ID3, TIT2
        from lyrics_engine import embed_lyrics

        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "Song.mp3"
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                 "-t", "2", "-c:a", "libmp3lame", str(audio)],
                check=True, capture_output=True,
            )
            tags = ID3(audio)
            tags.add(TIT2(encoding=1, text="Song"))
            tags.save(audio)
            result = LyricsResult(
                text="Первая строка\nSecond line",
                language="ru",
                segments=(TranscriptSegment(1.25, 1.8, "Первая строка"),
                          TranscriptSegment(65.5, 68.0, "Second line")),
            )
            self.assertEqual(embed_lyrics(audio, result), audio)
            self.assertEqual(save_lyrics(audio, result, "lrc"), audio)
            written = ID3(audio)
            self.assertEqual(written.getall("TIT2")[0].text[0], "Song")
            self.assertEqual(len(written.getall("USLT")), 1)
            self.assertIn("[01:05.50]Second line", written.getall("USLT")[0].text)
            self.assertFalse(audio.with_suffix(".lrc").exists())
            loaded = LyricsService(metadata_reader=lambda _: {"lyrics": written.getall("USLT")[0].text}).load_existing(audio)
            self.assertEqual(loaded.text, result.text)
            self.assertEqual(len(loaded.segments), 2)

    def test_language_detection_reports_mixed_script(self):
        language, confidence, mixed = detect_text_languages("Привет my love, это наша night")
        self.assertEqual(language, "mixed")
        self.assertGreater(confidence, 0.4)
        self.assertEqual(set(mixed), {"ru", "en/latin"})

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required to create a test MP3")
    def test_foreign_sound_spelling_reopens_with_language_and_alphabet_preserved(self):
        import music_metadata
        from mutagen.id3 import ID3
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "foreign.mp3"
            subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=22050:cl=mono',
                            '-t', '2', '-c:a', 'libmp3lame', str(audio)], check=True, capture_output=True)
            result = LyricsResult(text="gamarjoba megobaro megobaro", language="ka", transcription_alphabet="en",
                                  segments=(TranscriptSegment(1.25, 1.8, "gamarjoba megobaro megobaro"),))
            save_lyrics(audio, result, 'uslt')
            self.assertEqual(ID3(audio).getall('USLT')[0].lang, 'geo')
            loaded = LyricsService(metadata_reader=music_metadata.read_all_metadata).load_existing(audio)
            self.assertEqual(loaded.text, result.text)
            self.assertEqual(loaded.language, 'ka')
            self.assertEqual(loaded.transcription_alphabet, 'en')
            self.assertEqual(loaded.segments[0].start, 1.25)
            self.assertFalse(audio.with_suffix('.lrc').exists())
            save_lyrics(audio, LyricsResult(text='A manual English line', language='en'))
            self.assertFalse(ID3(audio).getall('TXXX:SONICFORGE_LYRICS_ALPHABET'))

    def test_service_provider_route_and_error_are_testable(self):
        expected = LyricsResult(text="Hello world again", source="mock")
        service = LyricsService(provider=MockLyricsProvider(expected))
        actual = service.recognize("unused.mp3")
        self.assertEqual(actual.text, expected.text)
        self.assertEqual(actual.language, "en/latin")

    def test_other_language_sound_modes_transliterate_without_english_decoding(self):
        provider = FasterWhisperProvider(model_name="small")
        calls = []

        class FakeModel:
            def __init__(self, *_args, **_kwargs):
                pass

            def transcribe(self, _audio, **kwargs):
                calls.append(kwargs)
                detected = "es" if kwargs["language"] is None else kwargs["language"]
                text = "hola mundo"
                segment = SimpleNamespace(start=1.0, end=2.0, text=text, no_speech_prob=0.05)
                return iter((segment,)), SimpleNamespace(language=detected, language_probability=0.93)

        with patch.object(provider, "available", return_value=True), patch.object(
            provider, "_vocal_audio", return_value=nullcontext("song.wav")
        ), patch("faster_whisper.WhisperModel", FakeModel):
            russian = provider.transcribe("song.wav", language="other_ru")
            english = provider.transcribe("song.wav", language="other_en")
        self.assertEqual([call["language"] for call in calls], [None, None])
        self.assertEqual(russian.text, "ола мундо")
        self.assertEqual(english.text, "hola mundo")
        self.assertEqual(russian.segments[0].start, 1.0)
        self.assertEqual(russian.language, "es")
        self.assertEqual(russian.transcription_alphabet, "ru")
        self.assertEqual(english.transcription_alphabet, "en")
        self.assertEqual(provider.model_name, "small")

    def test_sound_mode_keeps_original_russian_or_english(self):
        provider = FasterWhisperProvider(model_name="small")
        calls = []

        class FakeModel:
            def __init__(self, *_args, **_kwargs):
                pass

            def transcribe(self, _audio, **kwargs):
                calls.append(kwargs["language"])
                raw = SimpleNamespace(start=0.0, end=2.0, text="Русская строка песни", no_speech_prob=0.01)
                return iter((raw,)), SimpleNamespace(language="ru", language_probability=0.99)

        with patch.object(provider, "available", return_value=True), patch.object(
            provider, "_vocal_audio", return_value=nullcontext("song.wav")
        ), patch("faster_whisper.WhisperModel", FakeModel):
            result = provider.transcribe("song.wav", language="other_en")
        self.assertEqual(calls, [None])
        self.assertEqual(result.text, "Русская строка песни")


if __name__ == "__main__":
    unittest.main()
