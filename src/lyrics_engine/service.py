import re
from dataclasses import replace
from pathlib import Path

from .formats import load_sidecar, parse_lrc, find_sidecar, timing_input
from .models import LyricsResult
from .isolated import IsolatedLyricsProvider


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")


class LyricsService:
    def __init__(self, provider=None, metadata_reader=None, separate_vocals=None):
        self.separate_vocals = (provider is None) if separate_vocals is None else bool(separate_vocals)
        self.provider = provider or IsolatedLyricsProvider()
        self.metadata_reader = metadata_reader
        self._vocal_cache = None
        self._timing_provider = None

    def close(self):
        if self._timing_provider is not None:
            self._timing_provider.close()
            self._timing_provider = None
        close = getattr(self.provider, 'close', None)
        if close is not None:
            close()
        if self._vocal_cache is not None:
            self._vocal_cache.close()
            self._vocal_cache = None

    def load_existing(self, audio_path):
        result = None if Path(audio_path).suffix.lower() == ".mp3" else load_sidecar(audio_path)
        if result is None and self.metadata_reader is not None:
            tags = self.metadata_reader(Path(audio_path))
            text = tags.get("lyrics") or tags.get("unsyncedlyrics") or ""
            if text.strip():
                segments = tuple(parse_lrc(text))
                plain = "\n".join(segment.text for segment in segments) if segments else text.strip()
                language = tags.get("lyrics_language", "unknown")
                if not re.fullmatch(r"[a-z]{2,3}|en/latin|mixed|unknown", language):
                    language = "unknown"
                alphabet = tags.get("lyrics_alphabet")
                result = LyricsResult(text=plain, segments=segments, source="metadata", language=language,
                                      transcription_alphabet=alphabet if alphabet in ("en", "ru") else None)
        if result is None:
            result = load_sidecar(audio_path)
        if result is None:
            return None
        return self._with_language(result)

    def load_for_timing(self, audio_path):
        previous = self.load_existing(audio_path)
        if previous is None:
            return None
        raw = None
        if Path(audio_path).suffix.lower() == '.mp3' and self.metadata_reader is not None:
            tags = self.metadata_reader(Path(audio_path))
            raw = tags.get('lyrics') or tags.get('unsyncedlyrics')
        if not raw:
            sidecar = find_sidecar(audio_path)
            raw = sidecar.read_text(encoding='utf-8-sig') if sidecar else previous.text
        return timing_input(raw, previous)

    def align(self, audio_path, original, cancel_event=None, progress=None, language=None):
        if not original.text.strip():
            raise ValueError('Timing correction requires existing lyrics')
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError('Timing correction was cancelled')
        if self._timing_provider is None:
            from .alignment import timing_provider
            self._timing_provider = timing_provider()
        prepared = audio_path
        if self.separate_vocals:
            from .vocals import VocalCache
            if self._vocal_cache is None:
                self._vocal_cache = VocalCache()
            prepared = self._vocal_cache.prepare(audio_path, cancel_event, progress)
        detected, _, _ = detect_text_languages(original.text)
        language = 'ru' if CYRILLIC_RE.search(original.text) else (
            language if language not in (None, 'auto', 'other_ru', 'other_en', 'unknown') else
            original.language if original.language not in ('unknown', 'mixed') else detected)
        language = 'en' if language in ('unknown', 'en/latin', 'mixed') else language
        corrected = self._timing_provider.align(prepared, original, cancel_event, progress, language)
        if corrected.text != original.text or [s.text for s in corrected.segments] != [line for line in original.text.splitlines() if line.strip()]:
            raise ValueError('Timing correction changed the supplied words; result was rejected')
        return corrected

    def recognize(self, audio_path, cancel_event=None, progress=None, language=None, on_segment=None):
        options = dict(cancel_event=cancel_event, progress=progress, language=language)
        if on_segment is not None:
            options["on_segment"] = lambda segment: on_segment(replace(segment, start=max(0, segment.start - .1)))
        prepared = audio_path
        if self.separate_vocals:
            from .vocals import VocalCache
            if self._vocal_cache is None:
                self._vocal_cache = VocalCache()
            prepared = self._vocal_cache.prepare(audio_path, cancel_event, progress)
        result = self.provider.transcribe(prepared, **options)
        result = self._with_language(result)
        result = replace(result, segments=tuple(replace(s, start=max(0, s.start - .1)) for s in result.segments))
        if not self.is_usable(result):
            return LyricsResult(
                text=result.text,
                segments=result.segments,
                language=result.language,
                language_confidence=result.language_confidence,
                mixed_languages=result.mixed_languages,
                quality="low",
                instrumental=result.instrumental and not bool(result.text.strip()),
                source=result.source,
                transcription_alphabet=result.transcription_alphabet,
                review_reason=result.review_reason or ('confidence' if result.text.strip() else 'no_text'),
            )
        return result

    def resolve_for_cover(self, audio_path, supplied_text=""):
        if supplied_text and supplied_text.strip():
            return supplied_text.strip()
        result = self.load_existing(audio_path)
        return result.text if result else ""

    @staticmethod
    def is_usable(result):
        words = re.findall(r"[\w'-]+", result.text or "", re.UNICODE)
        speech_duration = sum(max(0.0, segment.end - segment.start) for segment in result.segments)
        confidences = [segment.confidence for segment in result.segments if segment.confidence is not None]
        average = sum(confidences) / len(confidences) if confidences else 1.0
        if result.instrumental or result.review_reason or len(words) < 3 or average < 0.35:
            return False
        return not result.segments or speech_duration >= 1.0

    @staticmethod
    def _with_language(result):
        # Sound spelling is not English/Russian, and an uncertain acoustic
        # language must not become "English" just because ASR guessed Latin.
        if result.transcription_alphabet or (result.source == "faster-whisper" and result.language == "unknown"):
            return result
        language, confidence, mixed = detect_text_languages(result.text)
        provider_language = result.language if result.language != "unknown" else language
        if mixed:
            provider_language = "mixed"
        provider_confidence = result.language_confidence
        # A weak initial audio guess must not label clearly Cyrillic lyrics English.
        if (language == "ru" and provider_language == "en"
                and len(CYRILLIC_RE.findall(result.text)) >= 20):
            provider_language = "ru"
            provider_confidence = None
        if provider_confidence is None:
            provider_confidence = confidence if result.language == "unknown" else None
        return LyricsResult(
            text=result.text,
            segments=result.segments,
            language=provider_language,
            language_confidence=provider_confidence,
            mixed_languages=mixed,
            quality=result.quality if result.quality != "unknown" else _quality_from_text(result.text),
            instrumental=result.instrumental,
            source=result.source,
            transcription_alphabet=result.transcription_alphabet,
            review_reason=result.review_reason,
        )


def detect_text_languages(text):
    cyrillic = len(CYRILLIC_RE.findall(text or ""))
    latin = len(LATIN_RE.findall(text or ""))
    total = cyrillic + latin
    if total == 0:
        return "unknown", 0.0, ()
    cyrillic_share = cyrillic / total
    latin_share = latin / total
    if cyrillic_share >= 0.85:
        return "ru", cyrillic_share, ()
    if latin_share >= 0.85:
        return "en/latin", latin_share, ()
    mixed = tuple(code for code, share in (("ru", cyrillic_share), ("en/latin", latin_share)) if share >= 0.12)
    return "mixed", max(cyrillic_share, latin_share), mixed


def _quality_from_text(text):
    words = len((text or "").split())
    if words >= 80:
        return "high"
    if words >= 20:
        return "medium"
    return "low"
