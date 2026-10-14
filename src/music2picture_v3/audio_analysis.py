"""Bounded spectral timeline; x always runs from the opening to the ending."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from music2picture_v2.audio_analysis import (DEFAULT_SAMPLE_RATE, FFT_SIZE, _frame_audio,
                                            _tempo, _find_peaks, decode_audio)
from music2picture_v2.utils import smooth


@dataclass(frozen=True)
class SongStructure:
    spectrum: np.ndarray  # low to high frequency rows, chronological columns
    level_curve: np.ndarray
    attack_curve: np.ndarray
    speed_curve: tuple[float, ...] = ()


def analyze_structure(audio_path):
    path = Path(audio_path).resolve()
    stat = path.stat()
    return _cached_structure(str(path), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=4)
def _cached_structure(path, file_size, mtime_ns):
    return analyze_structure_array(decode_audio(path))


def analyze_structure_array(audio, sample_rate=DEFAULT_SAMPLE_RATE):
    audio = np.nan_to_num(np.asarray(audio, dtype=np.float32).reshape(-1))
    if not audio.size:
        audio = np.zeros(FFT_SIZE, dtype=np.float32)
    frames, hop = _frame_audio(audio)
    magnitude = np.abs(np.fft.rfft(frames * np.hanning(FFT_SIZE), axis=1)).T
    # Classic M2Pv1 frequency spacing, with the same ~5.5 kHz upper boundary.
    # Keep absolute amplitude: a quiet section must not become loud by rescaling.
    frequencies = np.fft.rfftfreq(FFT_SIZE, 1 / sample_rate)
    targets = np.linspace(0, 1, 128) ** 1.65 * min(5500, sample_rate / 2)
    indices = np.interp(targets, frequencies, np.arange(len(frequencies)))
    lower = np.floor(indices).astype(int)
    upper = np.minimum(lower + 1, len(frequencies) - 1)
    weight = (indices - lower)[:, None]
    spectrum = np.log1p(magnitude) / np.log1p(FFT_SIZE * .25)
    spectrum = spectrum[lower] * (1 - weight) + spectrum[upper] * weight
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    levels = 20 * np.log10(np.maximum(rms, 1e-6))
    level = np.clip((levels + 60) / 54, 0, 1)
    attacks = np.clip(np.maximum(0, np.diff(levels, prepend=levels[0])) / 12, 0, 1)
    normalized = magnitude / (np.linalg.norm(magnitude, axis=0, keepdims=True) + 1e-8)
    flux = np.sqrt(np.mean(np.maximum(0, np.diff(normalized, axis=1,
                          prepend=normalized[:, :1])) ** 2, axis=0))
    onset = smooth(flux * 3.2 + attacks * .9, 1)
    speed = rhythmic_speed_profile(onset, levels, sample_rate / hop)
    # Pool across the entire track rather than picking individual FFT frames.
    groups = np.array_split(np.arange(len(level)), min(256, len(level)))
    spectrum = np.stack([spectrum[:, group].mean(axis=1) for group in groups], axis=1)
    level = np.asarray([level[group].mean() for group in groups])
    attacks = np.asarray([attacks[group].max() for group in groups])
    arrays = [np.clip(value, 0, 1).astype(np.float32) for value in (spectrum, level, attacks)]
    for value in arrays:
        value.setflags(write=False)
    return SongStructure(*arrays, speed)


def rhythmic_speed_profile(onset, levels, frame_rate):
    """Confidence-weighted tempo and attack rate, without loudness as speed."""
    count = min(64, max(1, round(len(onset) / frame_rate / 2)))
    radius = max(1, round(frame_rate * 4))
    speeds = []
    for center in np.linspace(0, len(onset) - 1, count):
        left, right = max(0, round(center) - radius), min(len(onset), round(center) + radius + 1)
        local = onset[left:right]
        threshold = max(.012, float(np.median(local) + np.subtract(*np.percentile(local, (75, 25))) * .75))
        peaks = _find_peaks(local, threshold, max(1, round(frame_rate * .10)))
        if len(peaks) < 3 or np.percentile(levels[left:right], 75) < -55:
            speeds.append(0.)
            continue
        tempo, confidence = _tempo(local, frame_rate)
        pace = np.clip((tempo - 45) / 155, 0, 1)
        density = np.clip((len(peaks) / max(.1, len(local) / frame_rate) - .25) / 5, 0, 1)
        speeds.append(round(float(pace * confidence * .75 + density * .25), 5))
    return tuple(speeds)
