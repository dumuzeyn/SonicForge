"""Organic folds with spectral and musical changes anchored to horizontal time."""
from dataclasses import dataclass, replace
import hashlib

import numpy as np
from PIL import Image

from music2picture_v2.renderer import (COMPOSITIONS, _artistic_texture, _finish,
                                      artistic_parameters, customize_parameters)

from .audio_analysis import SongStructure

GENERATOR_VERSION = 'chronological-organic-v2'


@dataclass(frozen=True)
class TimelineFields:
    spectrum: np.ndarray
    level: np.ndarray
    attack: np.ndarray
    drive: np.ndarray


def _curve(values, size, fallback=0):
    values = np.asarray(values, dtype=np.float32)
    if not values.size:
        return np.full((1, size), fallback, dtype=np.float32)
    return np.interp(np.linspace(0, 1, size), np.linspace(0, 1, len(values)), values)[None, :].astype(np.float32)


def timeline_fields(structure, dna, size):
    # No wrapping, shuffling or horizontal warp of the song's time coordinates.
    spectrum = np.asarray(structure.spectrum, dtype=np.float32)
    time = np.linspace(0, 1, size)
    rows = np.stack([np.interp(time, np.linspace(0, 1, spectrum.shape[1]), row)
                     for row in spectrum])
    frequency = np.linspace(0, spectrum.shape[0] - 1, size)
    low = frequency.astype(int)
    high = np.minimum(low + 1, spectrum.shape[0] - 1)
    weight = (frequency - low)[:, None]
    background = (rows[low] * (1 - weight) + rows[high] * weight)[::-1]
    level = _curve(structure.level_curve, size)
    attack = _curve(structure.attack_curve, size)
    activity = _curve(dna.activity_curve, size, fallback=dna.arousal)
    # Long activity windows cannot hide short pauses or sudden local attacks.
    audible = np.clip(level / .28, 0, 1)
    drive = np.clip((activity * .80 + attack * .12 + level * .08) * audible, 0, 1)
    return TimelineFields(background.astype(np.float32), level, attack, drive)


def smooth_field(field, radius, axis=1):
    radius = max(1, int(radius))
    kernel = np.exp(-.5 * (np.arange(-radius, radius + 1) / max(1, radius / 2)) ** 2)
    kernel /= kernel.sum()
    padding = [(0, 0)] * field.ndim
    padding[axis] = (radius, radius)
    return np.apply_along_axis(lambda row: np.convolve(row, kernel, mode='valid'),
                               axis, np.pad(field, padding, mode='edge')).astype(np.float32)


def flowing_time_coordinates(height, width, phase=0):
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    x /= max(1, width - 1)
    y /= max(1, height - 1)
    # Small, smoothly curved section boundaries. Each row remains strictly
    # chronological; opening/ending stay anchored and displacement is <4%.
    drift = .026 * np.sin(y * np.pi * 2 + phase) + .010 * np.sin(y * np.pi * 4 - phase)
    return np.clip(x + np.sin(x * np.pi) ** 2 * drift, 0, 1)


def flowing_timeline(fields, size, phase=0):
    time = flowing_time_coordinates(size, size, phase) * (size - 1)
    left = time.astype(int)
    right = np.minimum(left + 1, size - 1)
    fraction = time - left
    y = np.arange(size)[:, None]
    def flow(field, radius):
        field = smooth_field(field, radius)
        field = np.broadcast_to(field, (size, size))
        return (field[y, left] * (1 - fraction) + field[y, right] * fraction).astype(np.float32)
    spectrum = smooth_field(fields.spectrum, max(2, size * .025), axis=0)
    return TimelineFields(flow(spectrum, max(3, size * .022)),
                          flow(fields.level, max(3, size * .035)),
                          flow(fields.attack, max(3, size * .035)),
                          flow(fields.drive, max(3, size * .035)))


def render_cover(visual_dna, visual_plan, structure: SongStructure, size=1000,
                 seed=None, preview=False, detail=None, palette=None,
                 palette_stops=None, composition=None):
    requested = max(64, int(size))
    work_size = max(192, min(requested, 384 if preview else 640))
    payload = f'{GENERATOR_VERSION}|{visual_dna.fingerprint}|{0 if seed is None else int(seed)}'
    resolved = int.from_bytes(hashlib.sha256(payload.encode('utf-8')).digest()[:8], 'little') & 0x7FFFFFFF
    rng = np.random.default_rng(resolved)
    params = customize_parameters(artistic_parameters(visual_dna, visual_plan, resolved), detail)
    if composition is not None:
        if composition not in COMPOSITIONS:
            raise ValueError('Unknown M2Pv3 composition')
        params = replace(params, composition=composition)
    texture = _artistic_texture(visual_dna, visual_plan, params, work_size, rng,
                                palette=palette, palette_stops=palette_stops,
                                timeline=flowing_timeline(timeline_fields(structure, visual_dna, work_size),
                                                         work_size, params.direction_angle))
    image = _finish(texture, visual_dna, visual_plan, params, rng,
                    preserve_palette=True)
    if image.size != (requested, requested):
        image = image.resize((requested, requested), Image.Resampling.LANCZOS)
    return image.convert('RGB')
