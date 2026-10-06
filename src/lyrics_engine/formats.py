import re
from pathlib import Path

from .models import LyricsResult, TranscriptSegment


TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def sidecar_path(audio_path, export_format="txt", output_dir=None):
    audio_path = Path(audio_path)
    parent = Path(output_dir) if output_dir else audio_path.parent
    suffix = ".lrc" if str(export_format).lower().lstrip(".") == "lrc" else ".txt"
    return parent / f"{audio_path.stem}{suffix}"


def find_sidecar(audio_path):
    audio_path = Path(audio_path)
    for suffix in (".lrc", ".txt"):
        candidate = audio_path.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def load_sidecar(audio_path):
    path = find_sidecar(audio_path)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8-sig")
    segments = tuple(parse_lrc(text)) if path.suffix.lower() == ".lrc" else ()
    plain = "\n".join(segment.text for segment in segments) if segments else text.strip()
    return LyricsResult(text=plain, segments=segments, source="sidecar")


def parse_lrc(text):
    segments = []
    for line in text.splitlines():
        stamps = list(TIMESTAMP_RE.finditer(line))
        if not stamps:
            continue
        lyric = TIMESTAMP_RE.sub("", line).strip()
        if not lyric:
            continue
        for stamp in stamps:
            minutes, seconds, fraction = stamp.groups()
            fraction_value = 0.0
            if fraction:
                fraction_value = int(fraction) / (1000 if len(fraction) == 3 else 100)
            start = int(minutes) * 60 + int(seconds) + fraction_value
            segments.append(TranscriptSegment(start=start, end=start, text=lyric))
    return sorted(segments, key=lambda segment: segment.start)


def render_lrc(result):
    if result.segments:
        return "\n".join(f"[{_timestamp(segment.start)}]{segment.text.strip()}" for segment in result.segments if segment.text.strip()) + "\n"
    lines = [line.strip() for line in result.text.splitlines() if line.strip()]
    return "\n".join(f"[00:00.00]{line}" for line in lines) + ("\n" if lines else "")


def embed_lyrics(audio_path, result):
    """Store timed lyric lines in an MP3 USLT frame without a sidecar file."""
    from audio_tags import text_frame, update_id3

    audio_path = Path(audio_path)
    if audio_path.suffix.lower() != ".mp3":
        raise ValueError("Embedded lyrics are supported only for MP3 files")
    # Manual/untimed lyrics remain plain USLT, never fake [00:00.00] lines.
    content = render_lrc(result) if result.segments else result.text.strip()
    if not content.strip():
        raise ValueError("There are no lyric lines to embed")
    language = {"ru": "rus", "en": "eng", "en/latin": "eng", "ka": "geo"}.get(result.language, "und")
    frames = [text_frame('USLT', content, language=language)]
    # Retain the acoustic language and the display alphabet separately. Latin
    # sound spelling must not be labelled an English song on reopening.
    for name, value in (("SONICFORGE_LYRICS_LANGUAGE", result.language),
                        ("SONICFORGE_LYRICS_ALPHABET", result.transcription_alphabet)):
        if value and value != "unknown":
            frames.append(text_frame('TXXX', value, description=name))
    update_id3(audio_path, frames, remove_names=('USLT',), remove_custom=(
        'SONICFORGE_LYRICS_LANGUAGE', 'SONICFORGE_LYRICS_ALPHABET'))
    return audio_path


def save_lyrics(audio_path, result, export_format="txt", output_dir=None):
    if Path(audio_path).suffix.lower() == ".mp3":
        return embed_lyrics(audio_path, result)
    destination = sidecar_path(audio_path, export_format, output_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = render_lrc(result) if destination.suffix == ".lrc" else result.text.strip() + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(destination)
    return destination


def _timestamp(seconds):
    total = max(0.0, float(seconds))
    minutes = int(total // 60)
    remaining = total - minutes * 60
    return f"{minutes:02d}:{remaining:05.2f}"
