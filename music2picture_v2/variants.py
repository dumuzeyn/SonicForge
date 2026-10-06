"""Five cover styles combining the current renderer with Music2Picture 342013a.

The historical renderer is imported only when one of its styles is requested.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .renderer import render_cover


STYLE_CURRENT = "current"
STYLE_CURRENT_LEGACY_COLORS = "current_legacy_colors"
STYLE_BLEND = "blend"
STYLE_LEGACY_CURRENT_COLORS = "legacy_current_colors"
STYLE_LEGACY = "legacy"
STYLES = (
    STYLE_CURRENT,
    STYLE_CURRENT_LEGACY_COLORS,
    STYLE_BLEND,
    STYLE_LEGACY_CURRENT_COLORS,
    STYLE_LEGACY,
)
LEGACY_COLOR_MODES = ("ocean", "plasma", "fusion", "aurora")
LEGACY_COMMIT = "342013aaa8bdb4cb86c8c14fec0acb038e50b5ca"


def render_legacy(audio_path, size=1000, seed=None, color_mode="plasma"):
    """Render the original 342013a artwork before its optional title layer."""
    from . import legacy_music2picture as legacy

    color_mode = legacy.normalize_color_mode(color_mode)
    rng = np.random.default_rng(seed)
    audio = legacy.read_audio(audio_path)
    spectrum, rms, bass, mids, highs, centroid = legacy.stft_features(audio)
    bpm = legacy.estimate_bpm(rms)
    bpm_curve = legacy.estimate_bpm_curve_from_bass(bass, size)
    energy_curve, global_energy, _ = legacy.estimate_energy_profile(
        spectrum, rms, bass, highs, centroid, bpm, bpm_curve, size
    )
    motion_curve = (
        energy_curve if color_mode in {"plasma", "fusion", "aurora"}
        else legacy.estimate_motion_curve(spectrum, rms, centroid, bpm_curve, size)
    )
    rgb = legacy.render_random_cover(
        spectrum, rms, bass, mids, highs, size,
        patterns=2, bpm=bpm, bpm_curve=bpm_curve,
        color_mode=color_mode, motion_curve=motion_curve,
        energy_curve=energy_curve, global_energy=global_energy, rng=rng,
    )
    image = Image.fromarray(rgb, "RGB")
    image = legacy.ImageEnhance.Color(image).enhance(1.12 + 0.16 * global_energy)
    return legacy.ImageEnhance.Contrast(image).enhance(1.03 + 0.12 * global_energy)


def apply_palette(pattern: Image.Image, colors: Image.Image) -> Image.Image:
    """Map donor colors onto target luminance so the target geometry survives."""
    pattern = pattern.convert("RGB")
    colors = colors.convert("RGB").resize(pattern.size, Image.Resampling.LANCZOS)
    reduced = colors.resize((min(256, colors.width), min(256, colors.height)))
    palette_image = reduced.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    counts = palette_image.getcolors(maxcolors=256) or []
    palette = palette_image.getpalette()
    entries = sorted(counts, reverse=True)[:8]
    swatches = np.asarray(
        [palette[index * 3:index * 3 + 3] for _, index in entries], dtype=np.float32
    )
    if len(swatches) < 2:
        return pattern
    brightness = swatches @ np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    swatches = swatches[np.argsort(brightness)]
    pixels = np.asarray(pattern, dtype=np.float32)
    lightness = pixels @ np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    low, high = np.percentile(lightness, (2, 98))
    position = np.clip((lightness - low) / max(1.0, high - low), 0.0, 1.0)
    stops = np.linspace(0.0, 1.0, len(swatches))
    mapped = np.stack([np.interp(position, stops, swatches[:, channel]) for channel in range(3)], axis=-1)
    return Image.fromarray(np.uint8(np.clip(mapped, 0, 255)), "RGB")


def render_variant(audio_path, visual_dna, visual_plan, *, style=STYLE_CURRENT,
                   size=1000, seed=None, preview=False, legacy_color_mode="plasma"):
    if style not in STYLES:
        raise ValueError(f"Unknown cover style: {style}")
    if legacy_color_mode not in LEGACY_COLOR_MODES:
        raise ValueError(f"Unknown historical color mode: {legacy_color_mode}")
    current = None
    historical = None
    if style != STYLE_LEGACY:
        current = render_cover(visual_dna, visual_plan, size=size, seed=seed, preview=preview)
    if style != STYLE_CURRENT:
        historical = render_legacy(audio_path, size=size, seed=seed, color_mode=legacy_color_mode)
    if style == STYLE_CURRENT:
        return current
    if style == STYLE_CURRENT_LEGACY_COLORS:
        return apply_palette(current, historical)
    if style == STYLE_BLEND:
        return Image.blend(current, historical, 0.5)
    if style == STYLE_LEGACY_CURRENT_COLORS:
        return apply_palette(historical, current)
    return historical
