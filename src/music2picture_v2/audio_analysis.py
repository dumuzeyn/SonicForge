from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from .models import AudioAnalysis
from .utils import EPSILON, audio_fingerprint, clamp, resample_curve, robust_scale, scale, smooth


DEFAULT_SAMPLE_RATE = 22_050
FFT_SIZE = 2_048
BASE_HOP = 512
MAX_ANALYSIS_FRAMES = 7_500
STARTUP_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = np.asarray((6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88))
MINOR_PROFILE = np.asarray((6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17))


def decode_audio(path: str | Path, sample_rate: int = DEFAULT_SAMPLE_RATE) -> np.ndarray:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to analyse audio")
    command = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    raw = subprocess.check_output(command, **STARTUP_KWARGS)
    audio = np.frombuffer(raw, dtype="<f4").astype(np.float32, copy=True)
    if audio.size == 0:
        raise RuntimeError(f"No audio samples decoded from {path}")
    return np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)


def analyze_audio_file(path: str | Path, sample_rate: int = DEFAULT_SAMPLE_RATE) -> AudioAnalysis:
    audio = decode_audio(path, sample_rate=sample_rate)
    return analyze_audio_array(audio, sample_rate=sample_rate)


def analyze_audio_array(audio: np.ndarray, sample_rate: int = DEFAULT_SAMPLE_RATE) -> AudioAnalysis:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        audio = np.zeros(FFT_SIZE, dtype=np.float32)
    duration = audio.size / max(1, sample_rate)
    frames, hop = _frame_audio(audio)
    window = np.hanning(FFT_SIZE).astype(np.float32)
    magnitude = np.abs(np.fft.rfft(frames * window, axis=1)).T.astype(np.float32)
    power = np.square(magnitude, dtype=np.float32)
    frequencies = np.fft.rfftfreq(FFT_SIZE, 1.0 / sample_rate).astype(np.float32)

    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float32), axis=1) + EPSILON)
    rms_db = 20.0 * np.log10(np.maximum(rms, 1e-6))
    absolute_peak = float(np.max(np.abs(audio)))
    overall_rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float32)) + EPSILON))
    crest_factor_db = float(20.0 * np.log10(max(absolute_peak, 1e-6) / max(overall_rms, 1e-6)))
    p10, p50, p90 = (float(value) for value in np.percentile(rms_db, (10, 50, 90)))
    dynamic_range_db = max(0.0, p90 - p10)
    relative_rms = robust_scale(rms_db, 8, 92)

    spectral_sum = magnitude.sum(axis=0) + EPSILON
    centroid_curve = (magnitude * frequencies[:, None]).sum(axis=0) / spectral_sum
    rolloff_curve = _rolloff(power, frequencies)
    flatness_curve = np.exp(np.mean(np.log(power + EPSILON), axis=0)) / (np.mean(power, axis=0) + EPSILON)
    contrast_curve = _spectral_contrast(power, frequencies)
    zcr_curve = np.mean(np.abs(np.diff(np.signbit(frames), axis=1)), axis=1)

    normalized_spectrum = magnitude / (np.linalg.norm(magnitude, axis=0, keepdims=True) + EPSILON)
    spectral_flux_curve = np.sqrt(
        np.mean(np.square(np.maximum(0.0, np.diff(normalized_spectrum, axis=1, prepend=normalized_spectrum[:, :1]))), axis=0)
    )
    rms_attack = np.clip(np.maximum(0.0, np.diff(rms_db, prepend=rms_db[0])) / 12.0, 0.0, 1.0)
    onset_curve = smooth(spectral_flux_curve * 3.2 + rms_attack * 0.9, passes=1)
    onset_threshold = float(np.median(onset_curve) + np.subtract(*np.percentile(onset_curve, (75, 25))) * 0.75)
    minimum_distance = max(1, round((sample_rate / hop) * 0.10))
    onset_peaks = _find_peaks(onset_curve, height=max(onset_threshold, 0.012), distance=minimum_distance)
    onset_density = len(onset_peaks) / max(duration, 1e-6)
    tempo, tempo_confidence = _tempo(onset_curve, sample_rate / hop)
    if len(onset_peaks) < 3:
        tempo, tempo_confidence = 0.0, 0.0
    beat_regularity = _beat_regularity(onset_peaks)

    band_energy = _band_energies(power, frequencies)
    chroma = _chroma(magnitude, frequencies)
    key, mode, key_strength = _estimate_key(chroma)
    harmonic_complexity = _entropy(np.mean(chroma, axis=1))
    chord_change_rate = _chord_change(chroma)
    harmonic_ratio, percussive_ratio = _harmonic_percussive_ratio(magnitude)

    energy_curve, sections = _structure(
        relative_rms,
        spectral_flux_curve,
        band_energy[0],
        onset_curve,
    )
    section_count, section_contrast, peak_position, largest_transition, climax_position, intro_energy, ending_energy = sections
    attack_strength = clamp(float(np.percentile(onset_curve, 90)) / 0.18)

    return AudioAnalysis(
        duration=float(duration),
        sample_rate=int(sample_rate),
        fingerprint=audio_fingerprint(audio, sample_rate),
        absolute_peak=absolute_peak,
        rms_dbfs=float(20.0 * np.log10(max(overall_rms, 1e-6))),
        loudness_p10_dbfs=p10,
        loudness_p50_dbfs=p50,
        loudness_p90_dbfs=p90,
        crest_factor_db=crest_factor_db,
        dynamic_range_db=float(dynamic_range_db),
        relative_dynamic_range=clamp(dynamic_range_db / 28.0),
        spectral_centroid_hz=float(np.median(centroid_curve)),
        spectral_rolloff_hz=float(np.median(rolloff_curve)),
        spectral_flatness=clamp(float(np.median(flatness_curve))),
        spectral_contrast=clamp(float(np.median(contrast_curve)) / 42.0),
        zero_crossing_rate=clamp(float(np.median(zcr_curve)) / 0.35),
        spectral_flux=clamp(float(np.median(spectral_flux_curve)) / 0.075),
        onset_strength=clamp(float(np.percentile(onset_curve, 85)) / 0.16),
        onset_density=float(onset_density),
        tempo=float(tempo),
        tempo_confidence=float(tempo_confidence),
        beat_regularity=float(beat_regularity),
        rhythmic_density=clamp(float(scale(onset_density, 0.35, 7.5))),
        bass_energy=float(band_energy[3][0]),
        mid_energy=float(band_energy[3][1]),
        high_energy=float(band_energy[3][2]),
        harmonic_ratio=float(harmonic_ratio),
        percussive_ratio=float(percussive_ratio),
        harmonic_complexity=float(harmonic_complexity),
        chord_change_rate=float(chord_change_rate),
        attack_strength=float(attack_strength),
        key=key,
        mode=mode,
        key_strength=float(key_strength),
        section_count=int(section_count),
        section_contrast=float(section_contrast),
        energy_curve=tuple(round(float(value), 5) for value in energy_curve),
        peak_position=float(peak_position),
        largest_transition=float(largest_transition),
        climax_position=float(climax_position),
        intro_energy=float(intro_energy),
        ending_energy=float(ending_energy),
    )


def _frame_audio(audio: np.ndarray) -> tuple[np.ndarray, int]:
    if audio.size < FFT_SIZE:
        audio = np.pad(audio, (0, FFT_SIZE - audio.size))
    available = max(1, audio.size - FFT_SIZE)
    hop = max(BASE_HOP, int(np.ceil(available / MAX_ANALYSIS_FRAMES)))
    frame_count = max(1, 1 + (audio.size - FFT_SIZE) // hop)
    usable = audio[:FFT_SIZE + hop * (frame_count - 1)]
    return np.lib.stride_tricks.sliding_window_view(usable, FFT_SIZE)[::hop], hop


def _rolloff(power: np.ndarray, frequencies: np.ndarray) -> np.ndarray:
    cumulative = np.cumsum(power, axis=0)
    threshold = cumulative[-1] * 0.85
    indices = np.argmax(cumulative >= threshold[None, :], axis=0)
    return frequencies[indices]


def _spectral_contrast(power: np.ndarray, frequencies: np.ndarray) -> np.ndarray:
    boundaries = (40, 120, 300, 700, 1_600, 3_500, 7_000, frequencies[-1] + 1)
    contrasts = []
    db = 10.0 * np.log10(power + EPSILON)
    for low, high in zip(boundaries, boundaries[1:]):
        mask = (frequencies >= low) & (frequencies < high)
        if np.count_nonzero(mask) < 2:
            continue
        band = db[mask]
        contrasts.append(np.percentile(band, 90, axis=0) - np.percentile(band, 10, axis=0))
    return np.mean(contrasts, axis=0) if contrasts else np.zeros(power.shape[1], dtype=np.float32)


def _tempo(onset: np.ndarray, frame_rate: float) -> tuple[float, float]:
    centered = onset - np.mean(onset)
    if centered.size < 8 or np.max(np.abs(centered)) < 1e-7:
        return 0.0, 0.0
    fft_size = 1 << (centered.size * 2 - 1).bit_length()
    spectrum = np.fft.rfft(centered, fft_size)
    correlation = np.fft.irfft(spectrum * np.conj(spectrum), fft_size)[:centered.size]
    min_lag = max(1, int(frame_rate * 60.0 / 210.0))
    max_lag = min(centered.size - 1, int(frame_rate * 60.0 / 35.0))
    if max_lag <= min_lag:
        return 0.0, 0.0
    region = correlation[min_lag:max_lag + 1]
    best = int(np.argmax(region)) + min_lag
    tempo = 60.0 * frame_rate / best
    confidence = clamp((float(correlation[best]) - float(np.median(region))) / (abs(float(correlation[0])) + EPSILON) * 4.0)
    return float(np.clip(tempo, 35.0, 210.0)), confidence


def _beat_regularity(peaks: np.ndarray) -> float:
    if peaks.size < 4:
        return 0.0
    intervals = np.diff(peaks).astype(np.float32)
    variation = float(np.std(intervals) / (np.mean(intervals) + EPSILON))
    return clamp(1.0 - variation / 0.9)


def _band_energies(power: np.ndarray, frequencies: np.ndarray):
    total_curve = power.sum(axis=0) + EPSILON
    curves = []
    for low, high in ((20, 220), (220, 2_500), (2_500, frequencies[-1] + 1)):
        mask = (frequencies >= low) & (frequencies < high)
        curves.append(power[mask].sum(axis=0) / total_curve)
    medians = np.asarray([np.median(curve) for curve in curves], dtype=np.float32)
    medians /= medians.sum() + EPSILON
    return curves[0], curves[1], curves[2], medians


def _chroma(magnitude: np.ndarray, frequencies: np.ndarray) -> np.ndarray:
    chroma = np.zeros((12, magnitude.shape[1]), dtype=np.float32)
    valid = frequencies >= 40.0
    midi = np.round(69.0 + 12.0 * np.log2(np.maximum(frequencies[valid], 1.0) / 440.0)).astype(int)
    for pitch_class in range(12):
        mask = valid.copy()
        mask[valid] = np.mod(midi, 12) == pitch_class
        chroma[pitch_class] = magnitude[mask].sum(axis=0)
    chroma /= chroma.sum(axis=0, keepdims=True) + EPSILON
    return chroma


def _estimate_key(chroma: np.ndarray) -> tuple[str, str, float]:
    profile = np.mean(chroma, axis=1)
    if np.sum(profile) < EPSILON:
        return "C", "unknown", 0.0
    scores = []
    for mode, template in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
        normalized = (template - template.mean()) / (template.std() + EPSILON)
        for root in range(12):
            scores.append((float(np.dot(profile, np.roll(normalized, root))), root, mode))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    strength = clamp((best[0] - second[0]) / (abs(best[0]) + EPSILON) * 2.5)
    return KEY_NAMES[best[1]], best[2], strength


def _entropy(values: np.ndarray) -> float:
    probability = np.asarray(values, dtype=np.float64)
    probability /= probability.sum() + EPSILON
    entropy = -np.sum(probability * np.log2(probability + EPSILON))
    return clamp(float(entropy / np.log2(max(2, probability.size))))


def _chord_change(chroma: np.ndarray) -> float:
    if chroma.shape[1] < 2:
        return 0.0
    left, right = chroma[:, :-1], chroma[:, 1:]
    similarity = np.sum(left * right, axis=0) / (
        np.linalg.norm(left, axis=0) * np.linalg.norm(right, axis=0) + EPSILON
    )
    return clamp(float(np.median(1.0 - similarity)) / 0.22)


def _harmonic_percussive_ratio(magnitude: np.ndarray) -> tuple[float, float]:
    reduced = magnitude[::4]
    harmonic = _median_filter_axis(reduced, window=9, axis=1)
    percussive = _median_filter_axis(reduced, window=9, axis=0)
    harmonic_energy = float(np.sum(harmonic))
    percussive_energy = float(np.sum(percussive))
    total = harmonic_energy + percussive_energy + EPSILON
    return harmonic_energy / total, percussive_energy / total


def _structure(relative_rms, flux, bass, onset):
    local = smooth(relative_rms * 0.52 + robust_scale(flux) * 0.20 + robust_scale(bass) * 0.16 + robust_scale(onset) * 0.12, 4)
    curve = np.clip(resample_curve(local, 64), 0.0, 1.0)
    transitions = np.abs(np.diff(curve, prepend=curve[0]))
    threshold = float(np.median(transitions) + np.subtract(*np.percentile(transitions, (75, 25))) * 1.4)
    peaks = _find_peaks(transitions, height=max(threshold, 0.045), distance=6)
    section_count = int(np.clip(peaks.size + 1, 1, 9))
    boundaries = np.concatenate(([0], peaks, [len(curve)]))
    section_means = [float(np.mean(curve[left:right])) for left, right in zip(boundaries, boundaries[1:]) if right > left]
    section_contrast = clamp((max(section_means) - min(section_means)) if section_means else 0.0)
    peak_position = float(np.argmax(curve) / max(1, len(curve) - 1))
    largest_transition = clamp(float(np.max(transitions)) / 0.35)
    weighted = smooth(curve, 2) * np.linspace(0.85, 1.12, len(curve))
    climax_position = float(np.argmax(weighted) / max(1, len(curve) - 1))
    span = max(2, len(curve) // 8)
    return curve, (
        section_count,
        section_contrast,
        peak_position,
        largest_transition,
        climax_position,
        float(np.mean(curve[:span])),
        float(np.mean(curve[-span:])),
    )


def _find_peaks(values: np.ndarray, height: float, distance: int) -> np.ndarray:
    values = np.asarray(values)
    if values.size < 3:
        return np.empty(0, dtype=np.int64)

    candidates = np.flatnonzero(
        (values[1:-1] > values[:-2])
        & (values[1:-1] >= values[2:])
        & (values[1:-1] >= height)
    ) + 1
    if candidates.size < 2 or distance <= 1:
        return candidates.astype(np.int64, copy=False)

    selected: list[int] = []
    for candidate in candidates[np.argsort(values[candidates])[::-1]]:
        index = int(candidate)
        if all(abs(index - existing) >= distance for existing in selected):
            selected.append(index)
    return np.asarray(sorted(selected), dtype=np.int64)


def _median_filter_axis(values: np.ndarray, window: int, axis: int) -> np.ndarray:
    if window <= 1 or values.shape[axis] <= 1:
        return values.copy()
    window = min(window, values.shape[axis] * 2 - 1)
    if window % 2 == 0:
        window -= 1
    padding = [(0, 0)] * values.ndim
    padding[axis] = (window // 2, window // 2)
    padded = np.pad(values, padding, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, window, axis=axis)
    return np.median(windows, axis=-1).astype(values.dtype, copy=False)
