"""Bounded, cancellable sound recommendations; no artwork/tempo/key analysis."""
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

from audio_editor import Cancelled
from audio_tags import probe_audio

RATE = 22050
EXCERPT_SECONDS = 8


@dataclass(frozen=True)
class SoundAnalysis:
    duration: float
    analyzed_seconds: float
    rms_dbfs: float
    relative_dynamic_range: float
    bass_energy: float
    brightness: float


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def _decode(path, start, seconds, cancel):
    executable = shutil.which('ffmpeg')
    if not executable:
        raise RuntimeError('FFmpeg is required for sound analysis')
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [executable, '-hide_banner', '-nostdin', '-loglevel', 'error', '-ss', str(start),
             '-i', str(path), '-t', str(seconds), '-vn', '-ac', '1', '-ar', str(RATE),
             '-f', 'f32le', 'pipe:1'], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=errors,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while True:
                _check(cancel)
                try:
                    raw, _ = process.communicate(timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                errors.seek(0)
                raise RuntimeError(errors.read()[-3000:].decode('utf-8', 'replace'))
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
    if len(raw) > int((seconds + 1) * RATE * 4):
        raise ValueError('Decoded excerpt exceeds its analysis limit')
    audio = np.frombuffer(raw, dtype='<f4')
    if not audio.size:
        raise ValueError('No sound in analysis excerpt')
    return np.nan_to_num(audio, nan=0., posinf=1., neginf=-1.)


def analyze_sound(path, cancel=None, progress=None):
    def report(stage, **data):
        _check(cancel)
        if progress:
            progress(stage, data)
    path = Path(path).resolve(strict=True)
    report('opening')
    duration = probe_audio(path)['duration']
    if duration <= 0:
        raise ValueError('Audio duration could not be determined')
    seconds = min(EXCERPT_SECONDS, duration)
    # Short songs are measured in full. Longer songs use three spread excerpts,
    # not just a possibly silent opening; total decoding is capped at 24 seconds.
    starts = [0.] if duration <= EXCERPT_SECONDS * 3 else [
        min(duration - seconds, duration * fraction) for fraction in (.10, .45, .80)]
    if len(starts) == 1:
        seconds = min(duration, EXCERPT_SECONDS * 3)
    samples = []
    for index, start in enumerate(starts, 1):
        report('reading', index=index, total=len(starts))
        samples.append(_decode(path, start, seconds, cancel))
    report('levels')
    audio = np.concatenate(samples)
    frame_size, hop = 2048, 1024
    frames = np.concatenate([np.lib.stride_tricks.sliding_window_view(
        np.pad(sample, (0, max(0, frame_size - sample.size))), frame_size)[::hop]
        for sample in samples])
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    rms_db = 20 * np.log10(np.maximum(rms, 1e-6))
    rms_dbfs = float(20 * np.log10(max(float(np.sqrt(np.mean(audio * audio))), 1e-6)))
    dynamic = float(np.subtract(*np.percentile(rms_db, (90, 10))))
    report('spectrum')
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(frame_size), axis=1))
    power = spectrum * spectrum
    frequencies = np.fft.rfftfreq(frame_size, 1 / RATE)
    bands = np.array([np.median(power[:, (frequencies >= low) & (frequencies < high)].sum(axis=1)
                                / (power.sum(axis=1) + 1e-12))
                      for low, high in ((20, 220), (220, 2500), (2500, RATE / 2 + 1))])
    bands /= bands.sum() + 1e-12
    centroid = float(np.median((spectrum * frequencies).sum(axis=1) / (spectrum.sum(axis=1) + 1e-12)))
    report('noise')
    # Reuse the decoded audio; the previous implementation decoded again at 8 kHz.
    downsampled = np.interp(np.arange(0, audio.size, RATE / 8000), np.arange(audio.size), audio)
    size = 400
    noise = dict(apply=False, noise_floor_db=-120., flatness=0.)
    if downsampled.size >= size * 8:
        chunks = downsampled[:downsampled.size - downsampled.size % size].reshape(-1, size)
        levels = np.sqrt(np.mean(chunks * chunks, axis=1) + 1e-12)
        quiet_mask = levels <= np.percentile(levels, 20)
        quiet = chunks[quiet_mask][:120]
        magnitudes = np.abs(np.fft.rfft(quiet * np.hanning(size), axis=1)) + 1e-9
        flatness = float(np.median(np.exp(np.mean(np.log(magnitudes), axis=1)) / np.mean(magnitudes, axis=1)))
        floor = float(20 * np.log10(max(float(np.median(levels[quiet_mask])), 1e-6)))
        spread = float(20 * np.log10(max(float(np.percentile(levels, 75)), 1e-6))) - floor
        noise = dict(apply=floor > -52 and flatness > .22 and spread > 8,
                     noise_floor_db=floor, flatness=flatness)
    report('recommendation')
    result = SoundAnalysis(duration, audio.size / RATE, rms_dbfs,
                           min(1., max(0., dynamic / 28)), float(bands[0]),
                           min(1., max(0., centroid / 6500 * .7 + float(bands[2]) * .3)))
    return result, noise


class SoundAnalysisCache:
    def __init__(self):
        self.results = {}

    def analyze(self, path, cancel=None, progress=None):
        path = Path(path).resolve(strict=True)
        stamp = path.stat()
        key = (str(path), stamp.st_size, stamp.st_mtime_ns)
        _check(cancel)
        if key in self.results:
            if progress:
                progress('cached', {})
            return self.results[key]
        result = analyze_sound(path, cancel, progress)
        after = path.stat()
        if (after.st_size, after.st_mtime_ns) != key[1:]:
            raise ValueError('Audio changed during analysis; repeat the analysis')
        if len(self.results) >= 4:
            self.results.pop(next(iter(self.results)))
        self.results[key] = result
        return result
