from __future__ import annotations

import colorsys
import hashlib
from pathlib import Path

import numpy as np


EPSILON = 1e-9


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(min(high, max(low, value)))


def scale(value: float | np.ndarray, low: float, high: float):
    if high <= low:
        return np.zeros_like(value, dtype=np.float32) if isinstance(value, np.ndarray) else 0.0
    scaled = np.clip((np.asarray(value) - low) / (high - low), 0.0, 1.0)
    smoothed = scaled * scaled * (3.0 - 2.0 * scaled)
    if np.ndim(smoothed) == 0:
        return float(smoothed)
    return smoothed.astype(np.float32)


def robust_scale(values: np.ndarray, low_percentile: float = 10, high_percentile: float = 90) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return values
    low, high = np.percentile(values, (low_percentile, high_percentile))
    if high - low < EPSILON:
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0).astype(np.float32)


def resample_curve(values: np.ndarray, size: int = 64) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return np.zeros(size, dtype=np.float32)
    if values.size == size:
        return values.copy()
    return np.interp(
        np.linspace(0.0, 1.0, size),
        np.linspace(0.0, 1.0, values.size),
        values,
    ).astype(np.float32)


def smooth(values: np.ndarray, passes: int = 3) -> np.ndarray:
    result = np.asarray(values, dtype=np.float32).copy()
    if result.size < 3:
        return result
    for _ in range(max(0, passes)):
        result = (np.roll(result, 1) + result * 3.0 + np.roll(result, -1)) / 5.0
        result[0] = (result[0] * 3.0 + result[1]) / 4.0
        result[-1] = (result[-1] * 3.0 + result[-2]) / 4.0
    return result.astype(np.float32)


def audio_fingerprint(audio: np.ndarray, sample_rate: int) -> str:
    sample = resample_curve(np.asarray(audio, dtype=np.float32), 4096)
    quantized = np.clip(np.round(sample * 32767), -32768, 32767).astype("<i2")
    payload = sample_rate.to_bytes(4, "little", signed=False) + quantized.tobytes()
    return hashlib.sha256(payload).hexdigest()


def file_cache_key(path: Path, extra: str = "") -> str:
    stat = path.stat()
    payload = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{extra}"
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def hsv_hex(hue: float, saturation: float, luminance: float) -> str:
    red, green, blue = colorsys.hsv_to_rgb((hue % 360.0) / 360.0, clamp(saturation), clamp(luminance))
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"
