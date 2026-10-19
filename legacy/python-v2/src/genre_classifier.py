"""Offline, bounded-memory music tagging with the original ISC MSD musicnn.

Scores are independent sigmoid activations, NOT calibrated probabilities.
Filename context never contributes to acoustic genre scores.
"""
from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

import numpy as np

SR = 16000
PATCH_SECONDS = 3.0
FRAMES = 187
SILENCE_RMS = 10 ** (-60 / 20)
# Conservative operating policy, frozen before evaluation; requires calibration
# on a larger artist-disjoint validation set before claiming probability quality.
SCORE_THRESHOLD = 0.20
GENRE_LABELS = {
    'rock': 'Rock', 'pop': 'Pop', 'alternative': 'Alternative', 'indie': 'Indie',
    'electronic': 'Electronic', 'dance': 'Dance', 'alternative rock': 'Alternative Rock',
    'jazz': 'Jazz', 'metal': 'Metal', 'chillout': 'Chillout', 'classic rock': 'Classic Rock',
    'soul': 'Soul', 'indie rock': 'Indie Rock', 'electronica': 'Electronica', 'folk': 'Folk',
    'punk': 'Punk', 'blues': 'Blues', 'hard rock': 'Hard Rock', 'ambient': 'Ambient',
    'acoustic': 'Acoustic', 'experimental': 'Experimental', 'hip-hop': 'Hip-Hop',
    'country': 'Country', 'easy listening': 'Easy Listening', 'funk': 'Funk',
    'electro': 'Electro', 'heavy metal': 'Heavy Metal', 'progressive rock': 'Progressive Rock',
    'rnb': 'R&B', 'indie pop': 'Indie Pop', 'house': 'House',
}
CONTEXT_PATTERNS = {
    'Anime': r'anime|аниме|amv', 'OST': r'ost|soundtrack|саундтрек',
    'Edit': r'edit|edits|эдит', 'Nightcore': r'nightcore', 'Slowed': r'slowed',
}
STARTUP = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
_SESSION_LOCK = threading.Lock()


def check_cancelled(event):
    if event is not None and event.is_set():
        raise InterruptedError('Processing was cancelled.')


def context_tags(path):
    name = Path(path).stem.casefold().replace('_', ' ')
    return tuple(tag for tag, pattern in CONTEXT_PATTERNS.items()
                 if re.search(r'(?<!\w)(?:' + pattern + r')(?!\w)', name))


def capture(command, event=None, timeout=30):
    """Drain both pipes and interrupt/kill the decoder even during communicate."""
    check_cancelled(event)
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **STARTUP) as process:
        deadline = time.monotonic() + timeout
        try:
            while True:
                check_cancelled(event)
                if time.monotonic() > deadline:
                    raise RuntimeError('Audio decoder timed out.')
                try:
                    out, err = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.kill()
            process.communicate()
            raise
        if process.returncode:
            raise RuntimeError('Audio decoding failed: ' + err.decode('utf-8', 'replace')[-1500:])
        return out


def duration_seconds(path, event=None):
    # ffmpeg is bundled already; use PyAV for probing so ffprobe isn't an extra
    # executable requirement in the Windows installer.
    check_cancelled(event)
    import av
    try:
        with av.open(str(path)) as container:
            stream = next(s for s in container.streams if s.type == 'audio')
            duration = (float(stream.duration * stream.time_base) if stream.duration is not None
                        else float(container.duration / av.time_base) if container.duration else 0)
    except (av.FFmpegError, StopIteration, ValueError) as exc:
        raise RuntimeError(f'Cannot probe audio: {path}: {exc}') from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError('Audio duration is unavailable; genre left undefined.')
    return duration


def decode_fragment(path, start=0, seconds=9, sample_rate=SR, event=None):
    if not 0 < seconds <= 30 or start < 0:
        raise ValueError('Decode a positive fragment of at most 30 seconds.')
    raw = capture(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                   '-ss', str(start), '-i', str(path), '-t', str(seconds),
                   '-vn', '-ac', '1', '-ar', str(sample_rate), '-f', 'f32le', 'pipe:1'], event)
    audio = np.frombuffer(raw, dtype='<f4')
    if not audio.size or not np.isfinite(audio).all():
        raise RuntimeError(f'No valid audio decoded from {path}')
    return audio


def sample_regions(duration):
    """Cover the whole song with nonoverlapping nine-second regions, at most 5.

    Short tracks are covered once, without duplicate votes. Long tracks sample
    the interior of five time strata, reducing intro/outro dominance.
    """
    count = min(5, max(1, int(math.ceil(duration / 9))))
    width = min(9.0, duration / count)
    return [(max(0, (i + .5) * duration / count - width / 2), width) for i in range(count)]


@lru_cache(maxsize=1)
def mel_filters():
    # librosa's Slaney scale and area normalization, using NumPy only.
    def hz_to_mel(hz):
        hz = np.asarray(hz, dtype=float)
        return np.where(hz < 1000, hz / (200 / 3), 15 + np.log(np.maximum(hz, 1) / 1000) / (np.log(6.4) / 27))
    def mel_to_hz(mel):
        return np.where(mel < 15, mel * (200 / 3), 1000 * np.exp((mel - 15) * (np.log(6.4) / 27)))
    hz = mel_to_hz(np.linspace(hz_to_mel(0), hz_to_mel(SR / 2), 98))
    ramps = hz[:, None] - np.fft.rfftfreq(512, 1 / SR)[None, :]
    diff = np.diff(hz)
    weights = np.maximum(0, np.minimum(-ramps[:-2] / diff[:-1, None], ramps[2:] / diff[1:, None]))
    return (weights * (2 / (hz[2:] - hz[:-2]))[:, None]).astype(np.float32)


def log_mel(audio):
    # Match original musicnn: centered STFT, periodic Hann, power mel, logC.
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size < SR * PATCH_SECONDS:
        audio = np.pad(audio, (0, int(SR * PATCH_SECONDS) - audio.size), mode='wrap')
    padded = np.pad(audio, (256, 256), mode='reflect')
    frames = np.lib.stride_tricks.sliding_window_view(padded, 512)[::256][:FRAMES]
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(512) / 512)).astype(np.float32)
    power = np.abs(np.fft.rfft(frames * window)).astype(np.float32) ** 2
    mel = power @ mel_filters().T
    return np.log10(1 + 10000 * mel).astype(np.float32)


def model_directory():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'assets/models/genre'


@lru_cache(maxsize=1)
def _load_session():
    import onnxruntime as ort
    folder = model_directory()
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    path = folder / 'msd_musicnn.onnx'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
        raise RuntimeError('Genre model checksum mismatch.')
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    session = ort.InferenceSession(str(path), sess_options=opts, providers=['CPUExecutionProvider'])
    return session, tuple(manifest['labels'])


def model_session():
    # lru_cache alone can run its factory twice under concurrent cache misses.
    with _SESSION_LOCK:
        try:
            return _load_session()
        except Exception as exc:
            raise RuntimeError(f'Cannot load local genre model: {exc}') from exc


@dataclass(frozen=True)
class Candidate:
    genre: str
    score: float
    support: float


@dataclass(frozen=True)
class GenreResult:
    genres: tuple = ()
    alternatives: tuple = ()
    context: tuple = ()
    segments: tuple = ()
    reason: str = ''
    model: str = 'MSD_musicnn'

    @property
    def tag(self):
        return '; '.join(self.genres)

    def to_dict(self):
        return asdict(self)


def aggregate(scores, labels, allowed=None):
    from music_metadata import choose_allowed_genre
    allowed = list(GENRE_LABELS.values()) if allowed is None else list(allowed)
    candidates = []
    for i, label in enumerate(labels):
        canonical = GENRE_LABELS.get(label.casefold())
        genre = choose_allowed_genre(canonical, allowed) if canonical else None
        if genre:
            values = scores[:, i]
            candidates.append(Candidate(genre, float(values.mean()), float((values >= SCORE_THRESHOLD).mean())))
    candidates.sort(key=lambda c: (-c.score, c.genre))
    # Retain consistent whole-song tags and strong recurrent minority styles.
    # A single unusually high patch cannot establish a second style.
    selected = [c.genre for c in candidates if c.score >= SCORE_THRESHOLD and c.support >= .4][:3]
    return tuple(selected), tuple(candidates[:5])


def classify_genre(path, allowed=None, cancel_event=None):
    context = context_tags(path)
    try:
        duration = duration_seconds(path, cancel_event)
        patches, times = [], []
        for start, width in sample_regions(duration):
            check_cancelled(cancel_event)
            audio = decode_fragment(path, start, width, event=cancel_event)
            for offset in range(0, len(audio), int(SR * PATCH_SECONDS)):
                part = audio[offset:offset + int(SR * PATCH_SECONDS)]
                if len(part) < SR * 1.5:
                    continue
                # Silence gate on the physical signal, before any repeat padding.
                if np.sqrt(np.mean(part.astype(np.float64) ** 2)) < SILENCE_RMS:
                    continue
                patches.append(log_mel(part))
                times.append(start + offset / SR)
        if not patches:
            return GenreResult(context=context, reason='silent_or_too_short')
        session, labels = model_session()
        outputs = []
        # Two patches per run keeps intermediate activation memory bounded.
        for offset in range(0, len(patches), 2):
            check_cancelled(cancel_event)
            try:
                outputs.extend(session.run(None, {session.get_inputs()[0].name:
                               np.stack(patches[offset:offset + 2])})[0])
            except Exception as exc:
                raise RuntimeError(f'Genre model inference failed: {exc}') from exc
        check_cancelled(cancel_event)
        scores = np.asarray(outputs)
        if scores.shape != (len(patches), len(labels)) or not np.isfinite(scores).all():
            raise RuntimeError('Invalid output from genre model.')
        genres, alternatives = aggregate(scores, labels, allowed)
        segments = tuple({'start': t, 'scores': {GENRE_LABELS[label.casefold()]: float(row[i])
                         for i, label in enumerate(labels) if label.casefold() in GENRE_LABELS}}
                         for t, row in zip(times, scores))
        return GenreResult(genres, alternatives, context, segments,
                           '' if genres else 'low_confidence_or_unsupported')
    except (RuntimeError, OSError, ValueError, ImportError) as exc:
        # Failure is explicit and cannot invoke a filename/BPM fallback.
        # InterruptedError is an OSError: propagate cancellation instead.
        if isinstance(exc, InterruptedError):
            raise
        return GenreResult(context=context, reason=f'unavailable: {exc}')


def classify_batch(paths, allowed=None, cancel_event=None):
    for path in paths:
        check_cancelled(cancel_event)
        yield path, classify_genre(path, allowed, cancel_event)
