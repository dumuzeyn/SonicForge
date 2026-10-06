import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


STARTUP_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
COLOR_MODES = {"ocean", "plasma", "fusion", "aurora"}
COLOR_MODE_ALIASES = {
    "o": "ocean",
    "ocean": "ocean",
    "d": "plasma",
    "plasma": "plasma",
    "f": "fusion",
    "fusion": "fusion",
    "a": "aurora",
    "aurora": "aurora",
}
COLOR_MODE_LABELS = {
    "ocean": "Ocean",
    "plasma": "Plasma",
    "fusion": "Fusion",
    "aurora": "Aurora",
}

# PyCharm / direct Python run settings.
# Set RUN_FROM_CODE = True, edit the paths below, then press Run in PyCharm.
RUN_FROM_CODE = False
CODE_MODE = "covers"  # "covers" or "process"
CODE_SOURCE = r"C:\Path\To\MusicOrSong.mp3"
CODE_OUTPUT = r"C:\Path\To\OutputFolder"

# Cover settings.
CODE_SIZE = 1000
CODE_PATTERNS = 2  # 1 = simpler pattern, 2 = richer pattern
CODE_COLOR_MODE = "plasma"  # Ocean, Plasma, Fusion, Aurora; short aliases: O, D, F, A
CODE_CENTER_TITLE = True  # True = draw file name in the middle, False = only artwork
CODE_EMBED_COVER = False  # True = attach generated PNG as MP3 cover art
CODE_SEED = None  # Use an integer for repeatable covers.

# Music processing settings.
CODE_INTEGRATED_LUFS = -14.0
CODE_TRUE_PEAK = -1.5
CODE_LRA = 11.0
CODE_FINAL_GAIN = 1.30



def require_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg was not found in PATH.")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe was not found in PATH.")


def run(command):
    subprocess.run(command, check=True, text=True, encoding="utf-8", errors="replace", **STARTUP_KWARGS)


def audio_files(source):
    from audio_paths import find_audio_files
    return find_audio_files(source, AUDIO_EXTENSIONS)


def clean_stem(path):
    return Path(path).stem.rstrip(". ")


def normalize_color_mode(color_mode):
    key = str(color_mode).strip().lower()
    if key not in COLOR_MODE_ALIASES:
        raise ValueError(f'color_mode must be one of: {", ".join(sorted(COLOR_MODES))} or aliases O/D/F/A')
    return COLOR_MODE_ALIASES[key]



def output_mp3_path(source_root, output_root, audio_path):
    relative = audio_path.relative_to(source_root)
    return output_root / relative.with_suffix(".mp3")


def loudnorm_stats(audio_path, integrated_lufs, true_peak, lra):
    loudnorm = f"loudnorm=I={integrated_lufs}:TP={true_peak}:LRA={lra}:print_format=json"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-vn",
        "-i",
        str(audio_path),
        "-af",
        loudnorm,
        "-f",
        "null",
        "NUL",
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **STARTUP_KWARGS)
    text = result.stderr
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Could not read loudnorm stats for {audio_path}")
    return json.loads(text[start : end + 1])


def normalize_music(source, output, integrated_lufs=-14.0, true_peak=-1.5, lra=11.0, final_gain=1.30):
    source_root = Path(source).resolve()
    output_root = Path(output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    files = audio_files(source_root)

    if source_root.is_file():
        source_root = source_root.parent

    if not files:
        print(f"No supported audio files found in {source_root}")
        return

    for index, audio_path in enumerate(files, start=1):
        target = output_mp3_path(source_root, output_root, audio_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            print(f"[{index}/{len(files)}] Skip existing: {audio_path.name}")
            continue

        print(f"[{index}/{len(files)}] Analyze: {audio_path.name}")
        stats = loudnorm_stats(audio_path, integrated_lufs, true_peak, lra)
        loudnorm = (
            f"loudnorm=I={integrated_lufs}:TP={true_peak}:LRA={lra}:"
            f"measured_I={stats['input_i']}:"
            f"measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:"
            f"measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']}:"
            f"linear=true:print_format=summary,"
            f"volume={final_gain}"
        )

        print(f"[{index}/{len(files)}] Normalize: {audio_path.name}")
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(audio_path),
                "-map",
                "0:a:0",
                "-vn",
                "-af",
                loudnorm,
                "-c:a",
                "libmp3lame",
                "-b:a",
                "320k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-map_metadata",
                "0",
                "-id3v2_version",
                "3",
                str(target),
            ]
        )

    print(f"Done. Processed music is in: {output_root}")


def read_audio(audio_path, sample_rate=22050):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    raw = subprocess.check_output(command, **STARTUP_KWARGS)
    data = np.frombuffer(raw, dtype=np.float32)
    if data.size == 0:
        raise RuntimeError(f"No audio data decoded from {audio_path}")
    peak = np.max(np.abs(data))
    return data / peak if peak > 0 else data


def stft_features(audio, n_fft=2048, hop=512):
    if audio.size < n_fft:
        audio = np.pad(audio, (0, n_fft - audio.size))
    frame_count = max(1, 1 + (audio.size - n_fft) // hop)
    usable = audio[: n_fft + hop * (frame_count - 1)]
    frames = np.lib.stride_tricks.sliding_window_view(usable, n_fft)[::hop]
    window = np.hanning(n_fft).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1)).T
    spectrum = np.log1p(spectrum)[:512]
    spectrum -= spectrum.min()
    if spectrum.max() > 0:
        spectrum /= spectrum.max()

    rms = np.sqrt(np.mean(frames * frames, axis=1))
    if rms.max() > 0:
        rms /= rms.max()

    bass = spectrum[:24].mean(axis=0)
    mids = spectrum[24:160].mean(axis=0)
    highs = spectrum[160:].mean(axis=0)
    centroid = (spectrum * np.arange(spectrum.shape[0])[:, None]).sum(axis=0) / (spectrum.sum(axis=0) + 1e-6)
    centroid /= max(1, spectrum.shape[0] - 1)
    return spectrum, rms, bass, mids, highs, centroid


def resample_axis(values, size):
    if values.size == size:
        return values
    source = np.linspace(0, 1, values.size)
    target = np.linspace(0, 1, size)
    return np.interp(target, source, values)


def sample_curve(values, positions):
    values = np.asarray(values, dtype=np.float32)
    positions = np.clip(np.asarray(positions, dtype=np.float32), 0, values.size - 1)
    low = np.floor(positions).astype(np.int32)
    high = np.clip(low + 1, 0, values.size - 1)
    amount = positions - low
    return (values[low] * (1.0 - amount) + values[high] * amount).astype(np.float32)


def sample_map_bilinear(values, x_positions, y_positions):
    values = np.asarray(values, dtype=np.float32)
    height, width = values.shape
    x = np.clip(np.asarray(x_positions, dtype=np.float32), 0, width - 1)
    y = np.clip(np.asarray(y_positions, dtype=np.float32), 0, height - 1)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    tx = x - x0
    ty = y - y0
    top = values[y0, x0] * (1.0 - tx) + values[y0, x1] * tx
    bottom = values[y1, x0] * (1.0 - tx) + values[y1, x1] * tx
    return (top * (1.0 - ty) + bottom * ty).astype(np.float32)


def normalize_feature(values):
    values = values.astype(np.float32)
    low = np.percentile(values, 5)
    high = np.percentile(values, 95)
    if high <= low:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0, 1).astype(np.float32)


def fixed_scale(values, low, high):
    values = np.asarray(values, dtype=np.float32)
    if high <= low:
        return np.zeros_like(values, dtype=np.float32)
    scaled = np.clip((values - low) / (high - low), 0, 1)
    return (scaled * scaled * (3.0 - 2.0 * scaled)).astype(np.float32)


def smooth_curve(values, passes=3, center_weight=3.0):
    curve = np.asarray(values, dtype=np.float32).copy()
    for _ in range(passes):
        curve = (curve * center_weight + np.roll(curve, 1) + np.roll(curve, -1)) / (center_weight + 2.0)
    return curve.astype(np.float32)


def classify_energy(score):
    if score < 0.25:
        return "CALM"
    if score < 0.45:
        return "SMOOTH"
    if score < 0.60:
        return "BALANCED"
    if score < 0.78:
        return "ENERGETIC"
    return "AGGRESSIVE"


def palette_category(score):
    if score < 0.30:
        return "violet"
    if score < 0.43:
        return "rose-violet"
    if score < 0.54:
        return "magenta"
    if score < 0.66:
        return "coral"
    if score < 0.80:
        return "amber-orange"
    if score < 0.91:
        return "orange-red"
    return "red-orange"


def resize_spectrum(spectrum, freq_bins, time_bins):
    freq_source = np.linspace(0, 1, spectrum.shape[0])
    freq_target = np.linspace(0, 1, freq_bins) ** 1.65
    temp = np.empty((freq_bins, spectrum.shape[1]), dtype=np.float32)
    for t in range(spectrum.shape[1]):
        temp[:, t] = np.interp(freq_target, freq_source, spectrum[:, t])

    time_source = np.linspace(0, 1, temp.shape[1])
    time_target = np.linspace(0, 1, time_bins)
    resized = np.empty((freq_bins, time_bins), dtype=np.float32)
    for f in range(freq_bins):
        resized[f] = np.interp(time_target, time_source, temp[f])
    return resized


def estimate_bpm(rms, sample_rate=22050, hop=512):
    if rms.size < 16:
        return 120.0

    envelope = np.maximum(0, np.diff(rms, prepend=rms[0]))
    envelope -= envelope.mean()
    if np.max(np.abs(envelope)) > 0:
        envelope /= np.max(np.abs(envelope))

    frame_rate = sample_rate / hop
    min_lag = max(1, int(frame_rate * 60 / 200))
    max_lag = min(len(envelope) - 1, int(frame_rate * 60 / 30))
    if max_lag <= min_lag:
        return 120.0

    scores = [float(np.dot(envelope[:-lag], envelope[lag:])) for lag in range(min_lag, max_lag + 1)]
    best_lag = min_lag + int(np.argmax(scores))
    bpm = 60 * frame_rate / best_lag
    while bpm < 30:
        bpm *= 2
    while bpm > 200:
        bpm /= 2
    return float(np.clip(bpm, 30, 200))


def estimate_bpm_curve_from_bass(bass, output_size, sample_rate=22050, hop=512, window_seconds=15):
    bass = bass.astype(np.float32)
    if bass.size < 8:
        return np.full(output_size, 120.0, dtype=np.float32)

    smooth = bass.copy()
    for _ in range(4):
        smooth = (smooth * 2 + np.roll(smooth, 1) + np.roll(smooth, -1)) / 4

    onset = np.maximum(0, np.diff(smooth, prepend=smooth[0]))
    threshold = np.percentile(onset, 78)
    peak_mask = (onset > threshold) & (onset >= np.roll(onset, 1)) & (onset > np.roll(onset, -1))

    frames_per_window = max(1, int(window_seconds * sample_rate / hop))
    global_bpm = estimate_bpm(bass, sample_rate=sample_rate, hop=hop)
    centers = []
    bpm_values = []

    for start in range(0, bass.size, frames_per_window):
        end = min(bass.size, start + frames_per_window)
        bpm = int(np.count_nonzero(peak_mask[start:end])) * (60.0 / window_seconds)
        if bpm < 30 or bpm > 200:
            bpm = global_bpm
        centers.append((start + end - 1) / 2)
        bpm_values.append(float(np.clip(bpm, 30, 200)))

    if len(centers) == 1:
        return np.full(output_size, bpm_values[0], dtype=np.float32)

    source = np.asarray(centers, dtype=np.float32) / max(1, bass.size - 1)
    target = np.linspace(0, 1, output_size, dtype=np.float32)
    curve = np.interp(target, source, np.asarray(bpm_values, dtype=np.float32))
    for _ in range(3):
        curve = (curve * 3 + np.roll(curve, 1) + np.roll(curve, -1)) / 5
    return np.clip(curve, 30, 200).astype(np.float32)


def estimate_motion_curve(spectrum, rms, centroid, bpm_curve, output_size, sample_rate=22050, hop=512, window_seconds=3):
    frame_count = rms.size
    if frame_count < 4:
        return np.full(output_size, 0.5, dtype=np.float32)

    rms_norm = np.clip(rms.astype(np.float32), 0, 1)
    rms_attack = np.maximum(0, np.diff(rms_norm, prepend=rms_norm[0]))
    spectral_change = np.sqrt(np.mean(np.diff(spectrum, axis=1, prepend=spectrum[:, :1]) ** 2, axis=0))
    attack_signal = rms_attack * 1.2 + spectral_change * 2.4
    attack_threshold = max(0.030, float(np.percentile(attack_signal, 72)))
    attack_peaks = (
        (attack_signal > attack_threshold)
        & (attack_signal >= np.roll(attack_signal, 1))
        & (attack_signal > np.roll(attack_signal, -1))
    )

    flux_norm = fixed_scale(spectral_change, 0.010, 0.095)
    centroid_norm = fixed_scale(centroid, 0.18, 0.70)
    frames_per_window = max(1, int(window_seconds * sample_rate / hop))
    expected_attacks = max(1.0, window_seconds * 7.0)
    centers = []
    motion_values = []

    for start in range(0, frame_count, frames_per_window):
        end = min(frame_count, start + frames_per_window)
        onset_density = min(1.0, float(np.count_nonzero(attack_peaks[start:end])) / expected_attacks)
        loudness = float(np.mean(fixed_scale(rms_norm[start:end], 0.12, 0.68)))
        flux = float(np.mean(flux_norm[start:end]))
        brightness = float(np.mean(centroid_norm[start:end]))
        rms_contrast = float(fixed_scale(np.std(rms_norm[start:end]), 0.025, 0.22))
        local_bpm = float(np.mean(bpm_curve[start * output_size // frame_count : max(start * output_size // frame_count + 1, end * output_size // frame_count)]))
        bpm_motion = float(fixed_scale(local_bpm, 85.0, 178.0))
        audio_motion = (
            0.25 * onset_density
            + 0.18 * loudness
            + 0.21 * flux
            + 0.11 * brightness
            + 0.15 * rms_contrast
            + 0.10 * bpm_motion
        )
        motion = float(np.clip(audio_motion, 0, 1))
        centers.append((start + end - 1) / 2)
        motion_values.append(motion)

    if len(centers) == 1:
        return np.full(output_size, motion_values[0], dtype=np.float32)

    source = np.asarray(centers, dtype=np.float32) / max(1, frame_count - 1)
    target = np.linspace(0, 1, output_size, dtype=np.float32)
    curve = np.interp(target, source, np.asarray(motion_values, dtype=np.float32))
    return np.clip(smooth_curve(curve, passes=2, center_weight=4.0), 0, 1).astype(np.float32)


def estimate_energy_profile(spectrum, rms, bass, highs, centroid, bpm, bpm_curve, output_size, sample_rate=22050, hop=512):
    frame_count = rms.size
    if frame_count < 4:
        curve = np.full(output_size, 0.5, dtype=np.float32)
        diagnostics = {
            "attack_density": 0.0,
            "spectral_flux": 0.0,
            "rms_contrast": 0.0,
            "peak_density": 0.0,
            "bass_hits": 0.0,
            "high_energy": 0.0,
            "spectral_smoothness": 1.0,
        }
        return curve, 0.5, diagnostics

    duration = max(frame_count * hop / sample_rate, 1e-6)
    rms_norm = np.clip(rms.astype(np.float32), 0, 1)
    bass_norm = np.clip(bass.astype(np.float32), 0, 1)
    highs_norm = np.clip(highs.astype(np.float32), 0, 1)
    spectral_change = np.sqrt(np.mean(np.diff(spectrum, axis=1, prepend=spectrum[:, :1]) ** 2, axis=0))
    rms_jump = np.maximum(0, np.diff(rms_norm, prepend=rms_norm[0]))
    bass_jump = np.maximum(0, np.diff(bass_norm, prepend=bass_norm[0]))
    attack_signal = rms_jump * 1.25 + spectral_change * 2.35 + bass_jump * 0.35
    attack_threshold = max(0.032, float(np.percentile(attack_signal, 74)))
    attack_peaks = (
        (attack_signal > attack_threshold)
        & (attack_signal >= np.roll(attack_signal, 1))
        & (attack_signal > np.roll(attack_signal, -1))
    )
    strong_peak_mask = (
        (rms_norm > max(0.55, float(np.percentile(rms_norm, 88))))
        & (rms_norm >= np.roll(rms_norm, 1))
        & (rms_norm > np.roll(rms_norm, -1))
    )
    bass_hit_mask = (
        (bass_jump > max(0.025, float(np.percentile(bass_jump, 82))))
        & (bass_jump >= np.roll(bass_jump, 1))
        & (bass_jump > np.roll(bass_jump, -1))
    )

    local_bpm = resample_axis(bpm_curve, frame_count)
    attack_density_curve = smooth_curve(attack_peaks.astype(np.float32), passes=5, center_weight=5.0)
    peak_density_curve = smooth_curve(strong_peak_mask.astype(np.float32), passes=6, center_weight=5.0)
    bass_hit_curve = smooth_curve(bass_hit_mask.astype(np.float32), passes=5, center_weight=5.0)
    local_energy = (
        0.16 * fixed_scale(local_bpm, 90.0, 178.0)
        + 0.19 * fixed_scale(attack_density_curve, 0.015, 0.18)
        + 0.20 * fixed_scale(spectral_change, 0.010, 0.095)
        + 0.13 * fixed_scale(rms_jump, 0.010, 0.085)
        + 0.12 * fixed_scale(peak_density_curve, 0.010, 0.120)
        + 0.08 * fixed_scale(np.abs(rms_norm - smooth_curve(rms_norm, passes=8, center_weight=3.0)), 0.015, 0.18)
        + 0.07 * fixed_scale(highs_norm, 0.18, 0.66)
        + 0.05 * fixed_scale(bass_hit_curve, 0.010, 0.120)
    )
    local_energy = np.clip(smooth_curve(local_energy, passes=2, center_weight=4.0), 0, 1)

    diagnostics = {
        "attack_density": float(np.count_nonzero(attack_peaks) / duration),
        "spectral_flux": float(np.mean(spectral_change)),
        "rms_contrast": float(np.std(rms_norm)),
        "peak_density": float(np.count_nonzero(strong_peak_mask) / duration),
        "bass_hits": float(np.count_nonzero(bass_hit_mask) / duration),
        "high_energy": float(np.mean(highs_norm)),
        "spectral_smoothness": float(1.0 - np.clip(np.mean(spectral_change) / 0.11, 0, 1)),
    }
    global_energy = (
        0.16 * float(fixed_scale(bpm, 88.0, 178.0))
        + 0.17 * float(fixed_scale(diagnostics["attack_density"], 0.7, 8.5))
        + 0.18 * float(fixed_scale(diagnostics["spectral_flux"], 0.010, 0.090))
        + 0.14 * float(fixed_scale(diagnostics["rms_contrast"], 0.035, 0.240))
        + 0.13 * float(fixed_scale(diagnostics["peak_density"], 0.10, 2.8))
        + 0.10 * float(fixed_scale(diagnostics["high_energy"], 0.18, 0.62))
        + 0.07 * float(fixed_scale(diagnostics["bass_hits"], 0.15, 4.0))
        + 0.05 * (1.0 - diagnostics["spectral_smoothness"])
    )
    global_energy = float(np.clip(global_energy, 0, 1))
    curve = resample_axis(local_energy, output_size)
    curve = np.clip(0.72 * curve + 0.28 * global_energy, 0, 1).astype(np.float32)
    return curve, global_energy, diagnostics


def peak_emphasis(values):
    values = values.astype(np.float32)
    smooth = values.copy()
    for _ in range(6):
        smooth = (smooth * 2 + np.roll(smooth, 1) + np.roll(smooth, -1)) / 4
    peaks = np.maximum(0, values - smooth)
    if peaks.max() > 0:
        peaks /= peaks.max()
    peaks = np.power(peaks, 0.55)
    for _ in range(4):
        peaks = (peaks * 3 + np.roll(peaks, 1) + np.roll(peaks, -1)) / 5
    return np.clip(peaks, 0, 1)


def bpm_to_hue(bpm):
    position = np.clip((bpm - 40.0) / 160.0, 0, 1)
    return 0.78 * position


def motion_to_hue(motion):
    motion = np.clip(motion, 0, 1)
    stops = np.asarray([0.00, 0.15, 0.30, 0.45, 0.58, 0.70, 0.82, 0.92, 1.00], dtype=np.float32)
    hues = np.asarray([0.76, 0.77, 0.79, 0.72, 0.88, 0.91, 0.96, 0.00, 0.04], dtype=np.float32)
    return np.interp(motion.reshape(-1), stops, hues).reshape(motion.shape).astype(np.float32)


def energy_to_rgb(energy):
    energy = np.clip(np.asarray(energy, dtype=np.float32), 0, 1)
    stops = np.asarray([0.00, 0.16, 0.29, 0.42, 0.54, 0.66, 0.78, 0.90, 1.00], dtype=np.float32)
    colors = np.asarray(
        [
            (22, 6, 42),
            (68, 18, 126),
            (86, 54, 168),
            (168, 54, 152),
            (222, 82, 126),
            (224, 104, 84),
            (224, 134, 48),
            (218, 62, 80),
            (246, 88, 40),
        ],
        dtype=np.float32,
    ) / 255.0
    flat = energy.reshape(-1)
    channels = [np.interp(flat, stops, colors[:, channel]) for channel in range(3)]
    return np.stack(channels, axis=-1).reshape(energy.shape + (3,)).astype(np.float32)


def local_contrast_edge_rgb(base_rgb, edge_strength):
    base_rgb = np.clip(np.asarray(base_rgb, dtype=np.float32), 0, 1)
    edge_strength = np.clip(np.asarray(edge_strength, dtype=np.float32), 0, 1)
    luminance = base_rgb[..., 0] * 0.2126 + base_rgb[..., 1] * 0.7152 + base_rgb[..., 2] * 0.0722
    gray = luminance[..., None]
    saturated = np.clip(gray + (base_rgb - gray) * (1.30 + edge_strength[..., None] * 0.55), 0, 1)
    darker = np.clip(saturated * (0.30 - edge_strength[..., None] * 0.08), 0, 1)
    lighter = np.clip(1.0 - (1.0 - saturated) * (0.42 - edge_strength[..., None] * 0.10), 0, 1)
    return np.where((luminance > 0.42)[..., None], darker, lighter).astype(np.float32)


def apply_local_pattern_edges(rgb, pattern_edge, high_map, spectrum_value, sharp_mix):
    neighbor_rgb = (
        np.roll(rgb, 3, axis=0)
        + np.roll(rgb, -3, axis=0)
        + np.roll(rgb, 3, axis=1)
        + np.roll(rgb, -3, axis=1)
    ) * 0.25
    rim_edge = np.clip(pattern_edge * (0.38 + high_map * 0.30 + spectrum_value * 0.12), 0, 0.62)
    rim_color = local_contrast_edge_rgb(neighbor_rgb, pattern_edge)
    shadow_edge = np.clip(pattern_edge * (0.38 + sharp_mix * 0.34), 0, 0.58)
    rgb = rgb * (1.0 - shadow_edge[..., None] * (1.0 - rim_edge[..., None] * 0.35))
    return rgb * (1.0 - rim_edge[..., None]) + rim_color * rim_edge[..., None]


def hsv_to_rgb_array(h, s, v):
    h = np.mod(h, 1.0)
    i = np.floor(h * 6).astype(np.int32)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i = np.mod(i, 6)

    rgb = np.zeros(h.shape + (3,), dtype=np.float32)
    masks = [i == n for n in range(6)]
    rgb[masks[0]] = np.stack([v, t, p], axis=-1)[masks[0]]
    rgb[masks[1]] = np.stack([q, v, p], axis=-1)[masks[1]]
    rgb[masks[2]] = np.stack([p, v, t], axis=-1)[masks[2]]
    rgb[masks[3]] = np.stack([p, q, v], axis=-1)[masks[3]]
    rgb[masks[4]] = np.stack([t, p, v], axis=-1)[masks[4]]
    rgb[masks[5]] = np.stack([v, p, q], axis=-1)[masks[5]]
    return rgb


def smooth_random_field(size, cells, rng, detail=0.0):
    small = rng.random((cells, cells), dtype=np.float32)
    image = Image.fromarray(np.uint8(small * 255), "L")
    image = image.resize((size, size), Image.Resampling.BICUBIC)
    field = np.asarray(image).astype(np.float32) / 255
    if detail > 0:
        detail_cells = max(cells * 4, cells + 8)
        small_detail = rng.random((detail_cells, detail_cells), dtype=np.float32)
        detail_image = Image.fromarray(np.uint8(small_detail * 255), "L")
        detail_image = detail_image.resize((size, size), Image.Resampling.BILINEAR)
        detail_field = np.asarray(detail_image).astype(np.float32) / 255
        field = field * (1.0 - detail) + detail_field * detail
    field -= field.min()
    if field.max() > 0:
        field /= field.max()
    return field.astype(np.float32)


def render_random_cover(
    spec,
    rms,
    bass,
    mids,
    highs,
    size,
    patterns=2,
    bpm=120.0,
    bpm_curve=None,
    color_mode="ocean",
    motion_curve=None,
    energy_curve=None,
    global_energy=0.5,
    rng=None,
):
    if rng is None:
        rng = np.random.default_rng()
    song_map = resize_spectrum(spec, freq_bins=size, time_bins=size)
    song_map = np.flipud(song_map)
    if bpm_curve is None:
        bpm_curve = np.full(size, bpm, dtype=np.float32)
    if motion_curve is None:
        motion_curve = np.full(size, 0.5, dtype=np.float32)
    if energy_curve is None:
        energy_curve = motion_curve

    volume = resample_axis(rms, size)
    bass_line = resample_axis(bass, size)
    mids_line = resample_axis(mids, size)
    highs_line = resample_axis(highs, size)
    peaks = peak_emphasis(volume)

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    base_part = size - 1 - yy
    base_freq = xx

    calm_cells = int(round(8 + 8 * global_energy))
    sharp_cells = int(round(18 + 18 * global_energy))
    detail_amount = 0.12 + 0.20 * global_energy
    field_a = smooth_random_field(size, cells=calm_cells, rng=rng, detail=detail_amount * 0.55)
    field_b = smooth_random_field(size, cells=sharp_cells, rng=rng, detail=detail_amount)
    field_c = smooth_random_field(size, cells=max(7, calm_cells - 2), rng=rng, detail=detail_amount * 0.70)
    field_d = smooth_random_field(size, cells=max(24, sharp_cells + 8), rng=rng, detail=min(0.42, detail_amount + 0.10))
    micro_field = smooth_random_field(size, cells=max(36, sharp_cells * 2), rng=rng, detail=0.36)

    initial_part = np.clip(base_part + (field_a - 0.5) * 46 + (field_d - 0.5) * 28, 0, size - 1)
    peak_rows = sample_curve(peaks, initial_part)
    energy_rows = sample_curve(energy_curve, initial_part)
    calm = 1.0 - energy_rows
    sharp_mix = np.clip(energy_rows * 0.92 + peak_rows * 0.55, 0, 1)
    smooth_part = (field_a - 0.5) * (42 + 62 * calm)
    smooth_freq = (field_c - 0.5) * (55 + 78 * calm)
    angular = (np.abs(field_d - 0.5) * 2.0 - 0.5) * np.sign(field_b - 0.5)
    sharp_part = angular * (42 + 168 * sharp_mix)
    sharp_freq = (field_b - 0.5) * (58 + 205 * sharp_mix)
    part_warp = smooth_part * (1.0 - sharp_mix) + sharp_part * sharp_mix
    freq_warp = smooth_freq * (1.0 - sharp_mix) + sharp_freq * sharp_mix
    pattern_signal = np.zeros_like(field_a, dtype=np.float32)
    pattern_edge = np.zeros_like(field_a, dtype=np.float32)
    if patterns >= 2:
        wave_soft = np.sin((xx * 0.010 + field_c * 5.5) * math.pi) * (20 + 45 * calm)
        triangle = 2.0 * np.abs(((xx * (0.010 + 0.012 * sharp_mix) + field_d * 4.0) % 1.0) - 0.5) - 0.5
        part_warp += wave_soft * (1.0 - sharp_mix) + triangle * (42 + 118 * sharp_mix)
        freq_warp += np.sin((yy * 0.012 + field_a * 7) * math.pi) * (24 + 102 * sharp_mix)
        curve_angle = (xx * (0.016 + 0.010 * global_energy) + yy * (0.006 + 0.008 * global_energy))
        curve_angle += field_a * 4.2 + field_b * 2.4 - field_c * 3.0
        stripe = np.sin(curve_angle * math.pi)
        ridge = np.power(np.clip(np.abs(stripe), 0, 1), 0.34)
        broken_ridge = ridge * np.clip(0.46 + field_d * 0.58 + np.abs(field_a - field_b) * 0.46, 0, 1)
        pattern_signal = (broken_ridge - 0.5).astype(np.float32)
        edge_core = 1.0 - np.clip(np.abs(stripe) * 4.2, 0, 1)
        edge_breakup = np.clip(0.46 + field_b * 0.76 + np.abs(field_c - field_d) * 0.62, 0, 1)
        pattern_edge = np.power(edge_core, 0.34).astype(np.float32) * edge_breakup
        part_warp += (broken_ridge - 0.5) * (20 + 74 * sharp_mix)
        freq_warp += stripe * (18 + 62 * sharp_mix)

    part_pos = np.clip(base_part + part_warp, 0, size - 1)
    freq_pos = np.clip(base_freq + freq_warp, 0, size - 1)

    spectrum_value = sample_map_bilinear(song_map, part_pos, freq_pos)
    spectrum_detail = np.clip(
        (micro_field - 0.5) * 0.050 + (field_d - 0.5) * 0.030 + pattern_signal * 0.070 + pattern_edge * 0.125,
        -0.13,
        0.16,
    )
    spectrum_value = np.clip(spectrum_value + spectrum_detail, 0, 1)
    local_bpm = sample_curve(bpm_curve, part_pos)
    local_energy = sample_curve(energy_curve, part_pos)
    peak_rows = sample_curve(peaks, part_pos)
    energy_rows = local_energy
    sharp_mix = np.clip(energy_rows * 0.92 + peak_rows * 0.55, 0, 1)

    bass_map = sample_curve(bass_line, part_pos)
    mid_map = sample_curve(mids_line, part_pos)
    high_map = sample_curve(highs_line, part_pos)
    volume_map = sample_curve(volume, part_pos)
    if color_mode == "ocean":
        bpm_texture = (field_a - 0.5) * (1.6 + 1.2 * peak_rows) + pattern_signal * 1.1
        pixel_bpm = (local_bpm + bpm_texture).astype(np.float32)
        pixel_bpm = np.clip(pixel_bpm, 30, 200)

        hue_shift = (field_a - 0.5) * 0.014 + pattern_signal * 0.010 + spectrum_value * 0.006
        red_lock = np.clip((40.0 - pixel_bpm) / 10.0, 0, 1)
        hue_shift = np.where(red_lock > 0, np.minimum(hue_shift, 0), hue_shift)
        hue = np.mod(bpm_to_hue(pixel_bpm) + hue_shift, 1.0)
        saturation = np.clip(0.52 + spectrum_value * 0.18 + high_map * 0.08 + peak_rows * 0.12, 0, 1)
        value = np.clip(0.14 + spectrum_value * 0.48 + volume_map * 0.28 + bass_map * 0.10 + peak_rows * 0.30, 0, 1)
    elif color_mode in {"plasma", "fusion", "aurora"}:
        brightness_bias = np.clip((float(np.mean(highs_line)) - float(np.mean(bass_line))) * 0.18, -0.08, 0.08)
        bass_bias = np.clip((float(np.mean(bass_line)) - 0.38) * 0.10, -0.04, 0.05)
        color_energy = np.clip(global_energy + brightness_bias + bass_bias, 0, 1)
        base_energy = np.clip(0.56 * color_energy + 0.44 * local_energy, 0, 1)
        energy_sigma = 0.012 + 0.026 * sharp_mix
        pixel_energy = rng.normal(base_energy, energy_sigma).astype(np.float32)
        pixel_energy = np.clip(
            pixel_energy
            + (spectrum_value - 0.50) * 0.050
            + (micro_field - 0.5) * 0.025
            + pattern_signal * 0.055
            + pattern_edge * 0.085
            + peak_rows * 0.025,
            0,
            1,
        )
        rgb = energy_to_rgb(pixel_energy)
        saturation_boost = np.clip(0.82 + spectrum_value * 0.22 + sharp_mix * 0.18, 0.78, 1.22)
        value = np.clip(0.13 + spectrum_value * 0.54 + volume_map * 0.24 + bass_map * 0.10 + peak_rows * (0.18 + 0.20 * global_energy), 0, 1)
        rgb *= saturation_boost[..., None] * value[..., None] / np.maximum(rgb.max(axis=-1, keepdims=True), 0.08)
        if color_mode == "plasma":
            plasma_wave = np.sin((xx * 0.016 - yy * 0.010 + field_d * 5.0 + field_a * 1.6) * math.pi)
            plasma_lane = np.power(np.clip(plasma_wave * 0.5 + 0.5, 0, 1), 3.2)
            plasma_lane *= np.clip(0.42 + sharp_mix * 0.48 + peak_rows * 0.28, 0, 1)
            cool = np.asarray((0.08, 0.42, 1.00), dtype=np.float32)
            hot = np.asarray((1.00, 0.18, 0.54), dtype=np.float32)
            lane_color = cool * (1.0 - local_energy[..., None]) + hot * local_energy[..., None]
            rgb = rgb * (1.0 - plasma_lane[..., None] * 0.30) + lane_color * (plasma_lane[..., None] * 0.30)
            rgb = np.clip((rgb - 0.5) * 1.10 + 0.5, 0, 1)
        elif color_mode == "aurora":
            aurora_phase = yy * (0.008 + 0.004 * global_energy) - xx * 0.004 + field_a * 4.4 + field_c * 2.1
            aurora_wave = np.sin(aurora_phase * math.pi) * 0.5 + 0.5
            aurora_band = np.power(np.clip(aurora_wave, 0, 1), 2.8)
            aurora_band *= np.clip(0.34 + volume_map * 0.34 + high_map * 0.22 + (1.0 - sharp_mix) * 0.16, 0, 1)
            teal = np.asarray((0.06, 0.92, 0.72), dtype=np.float32)
            violet = np.asarray((0.54, 0.18, 1.00), dtype=np.float32)
            rose = np.asarray((1.00, 0.18, 0.72), dtype=np.float32)
            aurora_color = teal * (1.0 - local_energy[..., None]) + violet * local_energy[..., None]
            rose_mix = np.clip(high_map * 0.45 + spectrum_value * 0.24, 0, 0.55)[..., None]
            aurora_color = aurora_color * (1.0 - rose_mix) + rose * rose_mix
            rgb = rgb * (1.0 - aurora_band[..., None] * 0.34) + aurora_color * (aurora_band[..., None] * 0.34)
            rgb = np.clip(rgb * (0.94 + aurora_band[..., None] * 0.26), 0, 1)
    else:
        raise ValueError(f"Unknown color mode: {color_mode}")

    edge_pattern = (
        np.abs(np.gradient(field_a, axis=0))
        + np.abs(np.gradient(field_b, axis=1))
        + np.abs(np.gradient(micro_field, axis=0)) * 0.72
        + np.abs(np.gradient(micro_field, axis=1)) * 0.72
        + np.abs(np.gradient(pattern_signal, axis=0)) * 1.25
        + np.abs(np.gradient(pattern_signal, axis=1)) * 1.25
        + pattern_edge * 2.15
    )
    edge_pattern = np.clip(edge_pattern * (11 + 28 * sharp_mix), 0, 1)
    if color_mode == "ocean":
        rgb = hsv_to_rgb_array(hue, saturation, value)
        rgb = apply_local_pattern_edges(rgb, pattern_edge, high_map, spectrum_value, sharp_mix)
    elif color_mode in {"plasma", "fusion", "aurora"}:
        accent_mask = np.clip((high_map - 0.82) * 1.65 + edge_pattern * 0.045, 0, 1)
        accent_mask *= np.clip(pixel_energy - 0.58, 0, 0.42) / 0.42
        accent = np.asarray((1.00, 0.48, 0.10), dtype=np.float32)
        warm_strength = 0.040 if color_mode == "plasma" else (0.035 if color_mode == "aurora" else 0.055)
        rgb = rgb * (1.0 - accent_mask[..., None] * warm_strength) + accent * (accent_mask[..., None] * warm_strength)
        blue_mask = np.clip((field_b - 0.48) * 2.65 + (high_map - bass_map) * 1.75 + spectrum_value * 0.30 + edge_pattern * 0.15, 0, 1)
        blue_mask *= np.clip(0.92 - pixel_energy, 0, 0.92) / 0.92
        blue = np.asarray((0.06, 0.26, 1.00), dtype=np.float32)
        blue_strength = 0.38 if color_mode == "plasma" else (0.42 if color_mode == "aurora" else 0.50)
        rgb = rgb * (1.0 - blue_mask[..., None] * blue_strength) + blue * (blue_mask[..., None] * blue_strength)
        green_mask = np.clip((field_c - 0.40) * 2.65 + (mid_map + bass_map - high_map * 0.35) * 0.95 + (1.0 - sharp_mix) * 0.24, 0, 1)
        green_mask *= np.clip(0.86 - pixel_energy, 0, 0.86) / 0.86
        green = np.asarray((0.04, 0.78, 0.34), dtype=np.float32)
        green_strength = 0.28 if color_mode == "plasma" else (0.34 if color_mode == "aurora" else 0.52)
        rgb = rgb * (1.0 - green_mask[..., None] * green_strength) + green * (green_mask[..., None] * green_strength)
        rgb = apply_local_pattern_edges(rgb, pattern_edge, high_map, spectrum_value, sharp_mix)
    rgb *= np.clip(0.90 + edge_pattern[..., None] * (0.14 + sharp_mix[..., None] * 0.78), 0.70, 1.30)
    return np.clip(rgb * 255, 0, 255).astype(np.uint8)


def title_font(size):
    for candidate in (
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def music_edge_color(image, rng):
    arr = np.asarray(image.convert("RGB")).astype(np.float32)
    pixels = arr.reshape(-1, 3)
    scores = pixels.max(axis=1) - pixels.min(axis=1) + pixels.mean(axis=1) * 0.2
    top_count = max(32, len(scores) // 80)
    palette = pixels[np.argpartition(scores, -top_count)[-top_count:]]
    color = palette[int(rng.integers(0, len(palette)))]
    return tuple(int(x) for x in np.clip(color * 1.18, 0, 255))


def wrap_text(text, font, draw, max_width):
    words = text.split()
    if not words:
        return [text]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def balanced_text_layouts(text, font, draw, max_width):
    words = text.split()
    if len(words) <= 1:
        return [[text]]

    layouts = []

    def build(start, current):
        if start >= len(words):
            layouts.append(current)
            return
        line = ""
        for end in range(start, len(words)):
            line = words[end] if not line else f"{line} {words[end]}"
            bbox = draw.textbbox((0, 0), line, font=font)
            if bbox[2] - bbox[0] > max_width:
                break
            build(end + 1, current + [line])

    if len(words) <= 7:
        build(0, [])
    else:
        layouts.append(wrap_text(text, font, draw, max_width))

    single_word_layout = [[word] for word in words]
    if all((draw.textbbox((0, 0), word, font=font)[2] - draw.textbbox((0, 0), word, font=font)[0]) <= max_width for word in words):
        layouts.append(words)

    unique = []
    seen = set()
    for lines in layouts:
        key = tuple(lines)
        if key not in seen:
            seen.add(key)
            unique.append(lines)
    return unique


def text_block_size(lines, font, draw, line_gap, stroke_width=0, shadow_offset=(0, 0)):
    sizes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    shadow_x, shadow_y = shadow_offset
    extra_width = stroke_width * 2 + max(0, shadow_x)
    extra_height = stroke_width * 2 + max(0, shadow_y)
    widths = [box[2] - box[0] + extra_width for box in sizes]
    heights = [box[3] - box[1] + extra_height for box in sizes]
    return max(widths or [0]), sum(heights) + max(0, len(lines) - 1) * line_gap


def fit_text_to_square(text, square_size):
    probe = Image.new("RGB", (square_size, square_size))
    draw = ImageDraw.Draw(probe)
    best = None
    words = text.split()
    for font_size in range(12, square_size + 1):
        font = title_font(font_size)
        line_gap = max(2, font_size // 12)
        stroke_width = 0
        shadow_offset = (max(2, font_size // 28), max(2, font_size // 24))
        candidates = []
        for lines in balanced_text_layouts(text, font, draw, square_size):
            width, height = text_block_size(lines, font, draw, line_gap, stroke_width, shadow_offset)
            if width <= square_size and height <= square_size:
                fill = min(width / square_size, 1.0) * min(height / square_size, 1.0)
                line_bonus = min(len(lines), max(2, len(words))) * 0.08 if len(words) > 1 else 0
                balance = 1.0 - (max([draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0] for line in lines] or [0]) - min([draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0] for line in lines] or [0])) / max(square_size, 1)
                candidates.append((fill + line_bonus + balance * 0.05, lines, width, height))
        if candidates:
            _, lines, width, height = max(candidates, key=lambda item: item[0])
            best = (font, lines, line_gap, stroke_width, shadow_offset, width, height)
        elif best is not None:
            break
    return best


def patterned_text_fill(background, base_color, rng):
    width, height = background.size
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    angle = float(rng.uniform(-0.65, 0.65))
    phase = float(rng.uniform(0, math.tau))
    scale = float(rng.uniform(0.012, 0.020))
    wave = np.sin((xx * math.cos(angle) + yy * math.sin(angle)) * scale + phase)
    wave2 = np.sin((xx * math.cos(angle + 1.55) + yy * math.sin(angle + 1.55)) * scale * 0.92 + phase * 0.7)
    wave3 = np.sin((xx * math.cos(angle - 0.90) + yy * math.sin(angle - 0.90)) * scale * 1.80 + phase * 1.4)
    pattern = np.clip((wave * 0.46 + wave2 * 0.34 + wave3 * 0.20) * 0.5 + 0.5, 0, 1)
    tear_cells = max(12, min(width, height) // 56)
    tear_small = rng.random((tear_cells, tear_cells), dtype=np.float32)
    tear_img = Image.fromarray(np.uint8(tear_small * 255), "L").resize((width, height), Image.Resampling.BICUBIC)
    tear = np.asarray(tear_img).astype(np.float32) / 255.0
    sparse = (pattern > np.quantile(pattern, 0.84)) & (tear > 0.34)
    sparse_img = Image.fromarray(np.uint8(sparse * 255), "L")
    sparse_img = sparse_img.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.75))
    sparse = np.asarray(sparse_img).astype(np.float32) / 255.0
    sparse = np.clip((sparse - 0.12) / 0.88, 0, 1) * 0.62

    base_arr = np.full((height, width, 3), np.asarray(base_color[:3], dtype=np.float32), dtype=np.float32)
    bg_arr = np.asarray(background.convert("RGB").filter(ImageFilter.GaussianBlur(1.0))).astype(np.float32)
    bg_luma = bg_arr[..., 0] * 0.2126 + bg_arr[..., 1] * 0.7152 + bg_arr[..., 2] * 0.0722
    darker_bg = bg_arr * 0.58
    lighter_bg = np.clip(bg_arr * 1.35 + 28, 0, 255)
    bg_pattern = np.where((bg_luma > 132)[..., None], darker_bg, lighter_bg)
    rgb = base_arr * (1.0 - sparse[..., None]) + bg_pattern * sparse[..., None]
    alpha = np.full((height, width, 1), base_color[3] if len(base_color) > 3 else 255, dtype=np.float32)
    return Image.fromarray(np.uint8(np.clip(np.dstack([rgb, alpha]), 0, 255)), "RGBA")


def add_center_title(image, title, square_ratio=0.76, rng=None):
    if not title:
        return image
    if rng is None:
        rng = np.random.default_rng()

    base = image.convert("RGBA")
    width, height = base.size
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    text = title.upper()
    square_size = int(min(width, height) * square_ratio)
    square_left = (width - square_size) / 2
    square_top = (height - square_size) / 2
    padding = max(10, square_size // 42)
    inner_size = square_size - padding * 2

    fit = fit_text_to_square(text, inner_size)
    if fit is None:
        return image

    font, lines, line_gap, stroke_width, shadow_offset, _, text_height = fit
    accent_color = music_edge_color(image, rng)
    shadow_fill = tuple(int(x) for x in np.clip(np.asarray(accent_color) * 0.58, 0, 255)) + (230,)
    dark_shadow_fill = tuple(int(x) for x in np.clip(np.asarray(accent_color) * 0.22, 0, 255)) + (175,)
    text_fill = (255, 255, 255, 252)
    fill_texture = patterned_text_fill(image, text_fill, rng)
    sx, sy = shadow_offset
    line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_widths = [box[2] - box[0] for box in line_boxes]
    line_heights = [box[3] - box[1] for box in line_boxes]
    text_height = sum(line_heights) + max(0, len(lines) - 1) * line_gap
    y = (height - (text_height + sy)) / 2
    for line in lines:
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_width = line_bbox[2] - line_bbox[0]
        line_height = line_bbox[3] - line_bbox[1]
        x = (width - (line_width + sx)) / 2 - line_bbox[0]
        baseline_y = y - line_bbox[1]
        draw.text(
            (x + sx + 1, baseline_y + sy + 1),
            line,
            font=font,
            fill=dark_shadow_fill,
            stroke_width=stroke_width,
            stroke_fill=dark_shadow_fill,
        )
        draw.text(
            (x + sx, baseline_y + sy),
            line,
            font=font,
            fill=shadow_fill,
            stroke_width=stroke_width,
            stroke_fill=shadow_fill,
        )
        text_mask = Image.new("L", base.size, 0)
        mask_draw = ImageDraw.Draw(text_mask)
        mask_draw.text((x, baseline_y), line, font=font, fill=255)
        overlay.alpha_composite(Image.composite(fill_texture, Image.new("RGBA", base.size, (0, 0, 0, 0)), text_mask))

        y += line_height + line_gap

    return Image.alpha_composite(base, overlay).convert("RGB")


def make_cover(audio_path, output_path, size=1000, patterns=2, center_title=True, color_mode="plasma", seed=None):
    color_mode = normalize_color_mode(color_mode)

    rng = np.random.default_rng(seed)
    audio = read_audio(audio_path)
    spectrum, rms, bass, mids, highs, centroid = stft_features(audio)
    bpm = estimate_bpm(rms)
    bpm_curve = estimate_bpm_curve_from_bass(bass, size)
    energy_curve, global_energy, diagnostics = estimate_energy_profile(spectrum, rms, bass, highs, centroid, bpm, bpm_curve, size)
    motion_curve = energy_curve if color_mode in {"plasma", "fusion", "aurora"} else estimate_motion_curve(spectrum, rms, centroid, bpm_curve, size)
    rgb = render_random_cover(
        spectrum,
        rms,
        bass,
        mids,
        highs,
        size,
        patterns=patterns,
        bpm=bpm,
        bpm_curve=bpm_curve,
        color_mode=color_mode,
        motion_curve=motion_curve,
        energy_curve=energy_curve,
        global_energy=global_energy,
        rng=rng,
    )

    image = Image.fromarray(rgb, "RGB")
    image = ImageEnhance.Color(image).enhance(1.12 + 0.16 * global_energy)
    image = ImageEnhance.Contrast(image).enhance(1.03 + 0.12 * global_energy)
    if center_title:
        image = add_center_title(image, clean_stem(audio_path), rng=rng)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    if color_mode in {"plasma", "fusion", "aurora"}:
        detail = f"energy: {float(global_energy):.2f} ({classify_energy(global_energy)}), local: {float(np.min(energy_curve)):.2f}-{float(np.max(energy_curve)):.2f}"
    else:
        detail = f"local BPM: {float(np.min(bpm_curve)):.1f}-{float(np.max(bpm_curve)):.1f}"
    print(f"Cover saved: {output_path} (mode: {COLOR_MODE_LABELS[color_mode]}, BPM: {bpm:.1f}, {detail})")
    print(
        "Diagnostics: "
        f"BPM={bpm:.1f}, "
        f"global energy score={global_energy:.3f}, "
        f"classification={classify_energy(global_energy)}, "
        f"attack density={diagnostics['attack_density']:.2f}/s, "
        f"spectral flux={diagnostics['spectral_flux']:.4f}, "
        f"RMS contrast={diagnostics['rms_contrast']:.4f}, "
        f"peak density={diagnostics['peak_density']:.2f}/s, "
        f"dominant palette category={palette_category(global_energy)}"
    )
    return output_path


def embed_cover(mp3_path, image_path):
    mp3_path = Path(mp3_path)
    image_path = Path(image_path)
    if mp3_path.suffix.lower() != ".mp3":
        print(f"Skip embed, not an MP3: {mp3_path}")
        return

    temp_path = mp3_path.with_name(f"{mp3_path.stem}.cover_tmp.mp3")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(mp3_path),
            "-i",
            str(image_path),
            "-map",
            "0:a:0",
            "-map",
            "1:v:0",
            "-c:a",
            "copy",
            "-c:v",
            "mjpeg",
            "-disposition:v:0",
            "attached_pic",
            "-map_metadata",
            "0",
            "-id3v2_version",
            "3",
            str(temp_path),
        ]
    )
    temp_path.replace(mp3_path)
    print(f"Embedded cover into: {mp3_path}")


def make_covers(source, output, size=1000, patterns=2, center_title=True, embed=False, color_mode="plasma", seed=None):
    color_mode = normalize_color_mode(color_mode)
    source_path = Path(source).resolve()
    output_root = Path(output).resolve()
    files = audio_files(source_path)
    if not files:
        print(f"No supported audio files found in {source_path}")
        return

    for index, audio_path in enumerate(files, start=1):
        target = output_root / f"{clean_stem(audio_path)}_cover_{size}.png"
        print(f"[{index}/{len(files)}] Cover: {audio_path.name}")
        file_seed = None if seed is None else int(seed) + index - 1
        cover_path = make_cover(audio_path, target, size=size, patterns=patterns, center_title=center_title, color_mode=color_mode, seed=file_seed)
        if embed:
            embed_cover(audio_path, cover_path)


def main():
    parser = argparse.ArgumentParser(description="Normalize music and generate MP3 cover art.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process = subparsers.add_parser("process", help="Normalize music and export MP3 files.")
    process.add_argument("--source", required=True)
    process.add_argument("--output", required=True)
    process.add_argument("--integrated-lufs", type=float, default=-14.0)
    process.add_argument("--true-peak", type=float, default=-1.5)
    process.add_argument("--lra", type=float, default=11.0)
    process.add_argument("--final-gain", type=float, default=1.30)

    covers = subparsers.add_parser("covers", help="Generate cover images for one song or a folder.")
    covers.add_argument("--source", required=True, help="Audio file or folder with audio files.")
    covers.add_argument("--output", required=True, help="Folder for generated PNG covers.")
    covers.add_argument("--size", type=int, default=1000)
    covers.add_argument("--patterns", type=int, choices=[1, 2], default=2)
    covers.add_argument(
        "--color-mode",
        choices=sorted(COLOR_MODE_ALIASES),
        default="plasma",
        help="Cover mode: Ocean/O, Plasma/D, Fusion/F, Aurora/A.",
    )
    covers.add_argument("--seed", type=int, default=None, help="Integer seed for repeatable cover generation.")
    covers.add_argument("--center-title", dest="center_title", action="store_true", default=True, help="Draw the file name in the center (default).")
    covers.add_argument("--no-center-title", dest="center_title", action="store_false", help="Generate artwork without center text.")
    covers.add_argument("--embed-cover", action="store_true", help="Attach the generated image as MP3 cover art.")

    args = parser.parse_args()
    require_ffmpeg()

    if args.command == "process":
        normalize_music(args.source, args.output, args.integrated_lufs, args.true_peak, args.lra, args.final_gain)
    elif args.command == "covers":
        make_covers(args.source, args.output, args.size, args.patterns, args.center_title, args.embed_cover, args.color_mode, args.seed)


def run_from_code_settings():
    require_ffmpeg()
    if CODE_MODE == "process":
        normalize_music(
            CODE_SOURCE,
            CODE_OUTPUT,
            integrated_lufs=CODE_INTEGRATED_LUFS,
            true_peak=CODE_TRUE_PEAK,
            lra=CODE_LRA,
            final_gain=CODE_FINAL_GAIN,
        )
    elif CODE_MODE == "covers":
        make_covers(
            CODE_SOURCE,
            CODE_OUTPUT,
            size=CODE_SIZE,
            patterns=CODE_PATTERNS,
            center_title=CODE_CENTER_TITLE,
            embed=CODE_EMBED_COVER,
            color_mode=CODE_COLOR_MODE,
            seed=CODE_SEED,
        )
    else:
        raise ValueError('CODE_MODE must be "covers" or "process".')


if __name__ == "__main__":
    try:
        if RUN_FROM_CODE:
            run_from_code_settings()
        else:
            main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
