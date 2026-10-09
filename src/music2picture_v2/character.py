"""Shared calm-to-drive mapping with small, sustained opposite-section accents."""
from dataclasses import dataclass

import numpy as np

from .utils import clamp


@dataclass(frozen=True)
class MusicalCharacter:
    drive: float
    opposite_drive: float
    accent_share: float = 0.0
    accent_time: float = .5


def musical_character(dna):
    tempo = clamp((dna.tempo - 55) / 130) * clamp(dna.tempo_confidence)
    overall = clamp(.35 * dna.rhythmic_density + .24 * tempo
                    + .20 * dna.attack_strength + .13 * dna.arousal
                    + .08 * dna.absolute_loudness)
    overall = clamp((overall - .10) / .68)
    curve = np.asarray(getattr(dna, 'activity_curve', ()), dtype=np.float32)
    active = np.isfinite(curve) & (curve > .01)
    if not np.any(active):
        return MusicalCharacter(overall, overall)
    local = np.clip(curve[active], 0, 1)
    dominant = float(np.median(local))
    drive = clamp(dominant * .85 + overall * .15)
    opposite = active & ((curve > dominant + .17) if dominant < .5 else (curve < dominant - .17))
    # A click or one transitional window is not a contrasting musical section.
    sustained = opposite & (np.roll(opposite, 1) | np.roll(opposite, -1))
    if len(sustained):
        sustained[0] = opposite[0] and len(opposite) > 1 and opposite[1]
        sustained[-1] = opposite[-1] and len(opposite) > 1 and opposite[-2]
    if np.count_nonzero(sustained) < 2:
        return MusicalCharacter(drive, drive)
    opposite_drive = float(np.median(curve[sustained]))
    fraction = np.count_nonzero(sustained) / np.count_nonzero(active)
    share = float(min(.12, .025 + .25 * fraction) * clamp(abs(opposite_drive - drive) / .30))
    accent_time = float(np.mean(np.flatnonzero(sustained)) / max(1, len(curve) - 1))
    return MusicalCharacter(drive, opposite_drive, share, accent_time)


def accent_mask(shape, character, texture=None):
    """Low-strength accents following existing contours, never a separate spot."""
    if character.accent_share <= 0:
        return np.zeros(shape, dtype=np.float32)
    if texture is None:
        y, x = np.mgrid[0:shape[0], 0:shape[1]].astype(np.float32)
        x /= max(1, shape[1] - 1)
        y /= max(1, shape[0] - 1)
        texture = .5 + .5 * np.sin(x * 5 + y * 3 + np.sin(y * 5) * .8)
    texture = np.asarray(texture, dtype=np.float32)
    # A pair of softly tinted contour bands belongs to the same material.
    level = .24 + character.accent_time * .30
    bands = np.exp(-((texture - level) / .065) ** 2)
    bands += .65 * np.exp(-((texture - (level + .22)) / .055) ** 2)
    strength = min(.34, character.accent_share / max(float(bands.mean()), 1e-6))
    return np.minimum(bands * strength, .34).astype(np.float32)


def palette_positions(texture, dna, minority=None):
    """Keep dominant colors near musical drive; never auto-fill the entire scale."""
    character = musical_character(dna)
    texture = np.asarray(texture, dtype=np.float32)
    # Enough neighboring colors for depth, without stretching every track
    # over the complete palette or clipping the field into flat end colors.
    width = .34 + clamp(dna.harmonic_complexity) * .10
    center = clamp(character.drive, width * .5, 1 - width * .5)
    lower, upper = center - width * .5, center + width * .5
    if character.drive < .45:
        upper = min(upper, .49)
    elif character.drive > .55:
        lower = max(lower, .51)
    positions = lower + texture * (upper - lower)
    if character.accent_share:
        mask = accent_mask(positions.shape, character, texture) if minority is None else minority
        opposite_center = clamp(character.opposite_drive, width * .5, 1 - width * .5)
        opposite = opposite_center + (texture - .5) * width
        positions = positions * (1 - mask) + opposite * mask
    return np.clip(positions, 0, 1).astype(np.float32)
