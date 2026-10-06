from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class LyricsResult:
    text: str
    segments: tuple[TranscriptSegment, ...] = ()
    language: str = "unknown"
    language_confidence: float | None = None
    mixed_languages: tuple[str, ...] = ()
    quality: str = "unknown"
    instrumental: bool = False
    source: str = "unknown"
    transcription_alphabet: str | None = None
    review_reason: str = ""

    @property
    def has_timestamps(self):
        return bool(self.segments)
