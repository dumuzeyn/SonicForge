import importlib.util
import os
import math
from dataclasses import replace
from abc import ABC, abstractmethod
from contextlib import nullcontext

from .models import LyricsResult, TranscriptSegment
from .verification import repair_repeated_words, verified_segments


class LyricsProvider(ABC):
    name = "provider"

    @abstractmethod
    def transcribe(self, audio_path, cancel_event=None, progress=None, language=None, on_segment=None):
        raise NotImplementedError


class FasterWhisperProvider(LyricsProvider):
    name = "faster-whisper"

    def __init__(self, model_name=None, device=None, compute_type=None):
        self.model_name = model_name or os.environ.get("SONIC_FORGE_WHISPER_MODEL", "large-v3-turbo")
        self.device = device or os.environ.get("SONIC_FORGE_WHISPER_DEVICE", "cpu")
        self.compute_type = compute_type or os.environ.get("SONIC_FORGE_WHISPER_COMPUTE", "int8")
        self._model = None
        self._loaded_model_name = None
        self._language_identifier = None
        self._audio_duration = None

    @classmethod
    def available(cls):
        return importlib.util.find_spec("faster_whisper") is not None

    def transcribe(self, audio_path, cancel_event=None, progress=None, language=None, on_segment=None):
        if not self.available():
            raise RuntimeError(
                "Локальный модуль распознавания не установлен. Установите faster-whisper "
                "или загрузите уже готовый TXT/LRC рядом с песней."
            )
        if progress:
            progress("loading_model")
        model = self._get_model()
        self._audio_duration = None
        segments = []
        word_groups = []
        transcription_alphabet = None
        unreliable_text = False
        phonetic_language = {"other_en": "en", "other_ru": "ru"}.get(language)
        requested_language = None if phonetic_language or language in (None, "", "auto") else language
        with self._vocal_audio(audio_path) as prepared_audio:
            options = dict(
                beam_size=8,
                best_of=5,
                task="transcribe",
                vad_filter=False,
                word_timestamps=True,
                condition_on_previous_text=False,
                # Singing may begin near the end of a 30-second window. Do not
                # restrict the first timestamp to Whisper's default one second.
                max_initial_timestamp=30.0,
                temperature=(0.0, 0.2, 0.4),
                language_detection_segments=3,
                language_detection_threshold=0.85,
            )
            detected_language, probability = (requested_language, None)
            if requested_language is None and hasattr(model, "detect_language"):
                detected_language, probability = self._detect_song_language(
                    model, prepared_audio, cancel_event, progress,
                )
                if detected_language is None:
                    return LyricsResult(text="", language="unknown", quality="low", source=self.name,
                                        review_reason="language")
                from faster_whisper.tokenizer import _LANGUAGE_CODES
                if detected_language not in _LANGUAGE_CODES:
                    return LyricsResult(text="", language=detected_language, language_confidence=probability,
                                        quality="low", source=self.name, review_reason="language")
            if detected_language == "ka" and self.model_name == "large-v3-turbo":
                if progress:
                    progress("loading_model")
                # Only an internal acoustic pass: the native alphabet is never
                # sent to the editor. Drop the base reference before swapping
                # models, so both large models are not retained in memory.
                model = None
                model = self._get_native_model(detected_language)
            raw_segments, info = model.transcribe(
                str(prepared_audio), language=detected_language, **options,
            )
            detected_language = detected_language or getattr(info, "language", "unknown") or "unknown"
            if probability is None:
                probability = getattr(info, "language_probability", None) if requested_language is None else None
            if detected_language not in ("ru", "en", "unknown"):
                # Foreign songs default to sound spelling with Russian letters.
                # Forcing Whisper's English decoder invents semantic sentences.
                transcription_alphabet = phonetic_language or "ru"
            verification_options = dict(options, language=detected_language)
            def verification_progress(stage):
                nonlocal unreliable_text
                if stage == "unreliable_tail":
                    unreliable_text = True
                    stage = "verifying"
                if progress:
                    progress(stage)
            raw_segments = verified_segments(model, str(prepared_audio), raw_segments,
                                             verification_options, cancel_event, verification_progress,
                                             limit=4 if transcription_alphabet else 12,
                                             audio_duration=self._audio_duration)
            for raw in raw_segments:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Lyrics recognition was cancelled.")
                text = raw.text.strip()
                if text:
                    speech_probability = 1.0 - float(getattr(raw, "no_speech_prob", 0.0))
                    words = tuple(getattr(raw, "words", None) or ())
                    lexical_probability = (sum(float(word.probability) for word in words) / len(words)
                                           if words else math.exp(float(getattr(raw, "avg_logprob", 0.0))))
                    confidence = max(0.0, min(1.0, speech_probability, lexical_probability))
                    # no_speech_prob can be almost zero even for repetitive
                    # hallucinations. Do not treat that as perfect word accuracy.
                    if _implausible_text(raw, detected_language):
                        confidence = min(confidence, 0.2)
                        unreliable_text = True
                    segment = TranscriptSegment(float(raw.start), float(raw.end), text, confidence)
                    segments.append(segment)
                    word_groups.append(words)
                    if on_segment:
                        if transcription_alphabet:
                            from .transliteration import sound_spelling
                            segment = replace(segment, text=sound_spelling(segment.text, transcription_alphabet, detected_language))
                        on_segment(segment)
                    if progress:
                        progress("transcribing")
        segments = repair_repeated_words(segments, word_groups)
        if transcription_alphabet:
            from .transliteration import sound_spelling
            segments = [replace(segment, text=sound_spelling(segment.text, transcription_alphabet, detected_language))
                        for segment in segments]
        text = "\n".join(segment.text for segment in segments)
        average = sum(segment.confidence or 0 for segment in segments) / max(1, len(segments))
        return LyricsResult(
            text=text,
            segments=tuple(segments),
            language=detected_language,
            language_confidence=float(probability) if probability is not None else None,
            quality="low" if unreliable_text else _quality(average),
            instrumental=not bool(segments),
            source=self.name,
            transcription_alphabet=transcription_alphabet,
            review_reason="text" if unreliable_text else "",
        )

    def _detect_song_language(self, model, audio_path, cancel_event=None, progress=None):
        from faster_whisper.audio import decode_audio
        from .language_detection import detect_song_language

        if progress:
            progress("detecting_language")
        audio = decode_audio(str(audio_path), sampling_rate=16000)
        self._audio_duration = len(audio) / 16000
        from .language_identifier import LocalLanguageIdentifier
        if self._language_identifier is None:
            self._language_identifier = LocalLanguageIdentifier()
        return detect_song_language(model, audio, cancel_event=cancel_event,
                                    identifier=self._language_identifier)

    def _vocal_audio(self, audio_path):
        # PyAV already decodes/downmixes/resamples inside faster-whisper. Avoid
        # dynamic normalization and frequency filtering of sung consonants.
        return nullcontext(str(audio_path))

    def _get_model(self):
        return self._load_model(self.model_name)

    def _get_native_model(self, language):
        if language != "ka" or self.model_name != "large-v3-turbo":
            return self._get_model()
        from huggingface_hub import snapshot_download
        from faster_whisper.utils import disabled_tqdm
        path = snapshot_download(
            "LukeJacob2023/whisper-large-v3-turbo-ka-ct2-gguf",
            revision="a99c5dfd889a2ffca19908d99e8b4ffec7de433a",
            allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.json", "preprocessor_config.json"],
            tqdm_class=disabled_tqdm,
        )
        return self._load_model(path)

    def _load_model(self, model_name):
        if self._model is None or self._loaded_model_name != model_name:
            from faster_whisper import WhisperModel
            self._model = None
            self._model = WhisperModel(
                model_name, device=self.device, compute_type=self.compute_type
            )
            self._loaded_model_name = model_name
        return self._model


class MockLyricsProvider(LyricsProvider):
    name = "mock"

    def __init__(self, result):
        self.result = result

    def transcribe(self, audio_path, cancel_event=None, progress=None, language=None, on_segment=None):
        if on_segment:
            for segment in self.result.segments:
                on_segment(segment)
        return self.result


def _quality(confidence):
    if confidence >= 0.82:
        return "high"
    if confidence >= 0.58:
        return "medium"
    return "low"


def _implausible_text(raw, language):
    text = raw.text.strip()
    letters = [c for c in text if c.isalpha()]
    # A folk refrain can legitimately repeat. Compression alone is not evidence
    # of hallucination unless the text is also crammed into implausible timing.
    rate = len(letters) / max(0.1, float(raw.end) - float(raw.start))
    if float(getattr(raw, "compression_ratio", 0.0)) > 2.4 and rate > 18:
        return True
    if rate > 30:
        return True
    if language == "ka" and letters:
        compression = float(getattr(raw, "compression_ratio", 0.0))
        syllables = ["".join(c for c in word.casefold() if c.isalpha()) for word in text.split()]
        syllables = [word for word in syllables if word]
        # Speech fine-tuning can give near-perfect probabilities to a loop of
        # short sung syllables. Flag it for review even at a normal reading rate;
        # keep the displayed text and do not remove genuine musical repetitions.
        if compression > 7.0 and len(letters) >= 40:
            return True
        # The same loop may be emitted as one fused token with no spaces.
        if compression > 3.5 and len(letters) >= 40 and len({c.casefold() for c in letters}) <= 6:
            return True
        if (compression > 3.5 and len(syllables) >= 12
                and len(letters) / len(syllables) <= 5.0
                and len(set(syllables)) / len(syllables) < .4):
            return True
        native_share = sum('\u10a0' <= c <= '\u10ff' or '\u1c90' <= c <= '\u1cbf' for c in letters) / len(letters)
        return native_share < 0.8
    return False
