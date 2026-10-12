import re
import math
from dataclasses import replace
from pathlib import Path

from .models import LyricsResult, TranscriptSegment


TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
TIMESTAMP_HINT_RE = re.compile(r'\[\d{1,3}:')
LRC_HEADER_RE = re.compile(r'^\[(?:ar|ti|al|by|re|ve|length):[^\]]*\]$', re.I)


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


def parse_lrc(text, strict=False):
    segments = []
    lines = text.splitlines()
    offset = 0.0
    for line in lines:
        match = re.fullmatch(r'\[offset:([+-]?\d+)\]', line.strip(), re.I)
        if match:
            offset = int(match[1]) / 1000
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or LRC_HEADER_RE.fullmatch(line) or re.fullmatch(r'\[offset:[+-]?\d+\]', line, re.I):
            continue
        stamps = list(TIMESTAMP_RE.finditer(line))
        if strict and len(TIMESTAMP_HINT_RE.findall(line)) != len(stamps):
            raise ValueError(f'Line {number}: invalid timestamp; use [mm:ss.xx].')
        if not stamps or (strict and stamps[0].start() != 0):
            if strict:
                raise ValueError(f'Line {number}: use [mm:ss.xx] before each lyric line.')
            continue
        lyric = TIMESTAMP_RE.sub("", line).strip()
        if not lyric:
            continue
        for stamp in stamps:
            minutes, seconds, fraction = stamp.groups()
            if int(seconds) >= 60:
                if strict:
                    raise ValueError(f'Line {number}: seconds must be between 00 and 59.')
                continue
            fraction_value = int(fraction) / 10 ** len(fraction) if fraction else 0.0
            start = int(minutes) * 60 + int(seconds) + fraction_value + offset
            if strict and start < 0:
                raise ValueError(f'Line {number}: offset produces negative time.')
            start = max(0, start)
            segments.append(TranscriptSegment(start=start, end=start, text=lyric))
    segments.sort(key=lambda segment: segment.start)
    if strict and not segments:
        raise ValueError('No timed lyric lines found.')
    return [replace(segment, end=segments[i + 1].start if i + 1 < len(segments) else segment.start)
            for i, segment in enumerate(segments)]


def result_from_text(text, previous=None, force_timed=False):
    """Parse explicit user timestamps; retain existing times for plain line edits."""
    if force_timed or TIMESTAMP_HINT_RE.search(text):
        segments = tuple(parse_lrc(text, strict=True))
        plain = '\n'.join(s.text for s in segments)
    else:
        plain = text.strip()
        lines = [line.strip() for line in plain.splitlines() if line.strip()]
        segments = previous.segments if previous else ()
        segments = tuple(replace(s, text=line) for s, line in zip(segments, lines)) if len(segments) == len(lines) else ()
    base = previous or LyricsResult(text='')
    return replace(base, text=plain, segments=segments, source='edited' if previous else 'manual',
                   instrumental=False, review_reason='')


def render_lrc(result):
    if result.segments:
        return "\n".join(f"[{_timestamp(segment.start)}]{segment.text.strip()}" for segment in result.segments if segment.text.strip()) + "\n"
    raise ValueError('LRC requires real line timestamps. Use TXT for untimed lyrics.')


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
    return format_timestamp(seconds)


def format_timestamp(seconds):
    total = float(seconds)
    if not math.isfinite(total) or total < 0:
        raise ValueError('Timestamp must be a nonnegative finite time.')
    ticks = round(total * 100)
    minutes, remainder = divmod(ticks, 6000)
    second, fraction = divmod(remainder, 100)
    return f'{minutes:02d}:{second:02d}.{fraction:02d}'
