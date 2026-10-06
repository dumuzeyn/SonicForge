from __future__ import annotations

import hashlib
import random

from .models import VisualDNA, VisualPlan
from .utils import clamp, hsv_hex


KEY_HUES = {
    "C": 42.0,
    "C#": 318.0,
    "D": 24.0,
    "D#": 278.0,
    "E": 55.0,
    "F": 188.0,
    "F#": 210.0,
    "G": 132.0,
    "G#": 338.0,
    "A": 12.0,
    "A#": 258.0,
    "B": 82.0,
}


def build_visual_plan(dna: VisualDNA, variation: int = 0) -> VisualPlan:
    anchor = KEY_HUES.get(dna.key, 210.0)
    fingerprint_digest = hashlib.sha256(dna.fingerprint.encode("utf-8", errors="replace")).digest()
    fingerprint_shift = (int.from_bytes(fingerprint_digest[:2], "little") % 111) - 55
    emotional_shift = (dna.warmth - 0.5) * 48.0 + (dna.valence - 0.5) * 34.0
    variation_shift = ((variation * 47) % 71) - 35 if variation else 0
    primary_hue = (anchor + emotional_shift + variation_shift + fingerprint_shift) % 360.0
    palette_width = clamp(0.20 + dna.harmonic_complexity * 0.42 + dna.dissonance * 0.38)
    separation = 28.0 + palette_width * 112.0
    secondary_hue = (primary_hue + separation * (1.0 if variation % 2 == 0 else -1.0)) % 360.0
    accent_hue = (primary_hue + 145.0 + dna.tension * 75.0) % 360.0
    saturation = clamp(0.28 + dna.arousal * 0.34 + dna.spectral_contrast * 0.18 - dna.acousticness * 0.08)
    luminance = clamp(0.28 + dna.brightness * 0.34 + dna.valence * 0.16 - dna.darkness * 0.11)
    contrast = clamp(0.28 + dna.tension * 0.28 + dna.original_dynamic_range * 0.24 + dna.attack_strength * 0.20)
    temperature = clamp(dna.warmth * 0.65 + dna.valence * 0.35)
    curvature = clamp(0.72 - dna.roughness * 0.36 - dna.attack_strength * 0.22 + dna.relaxation * 0.18)
    angularity = clamp(dna.roughness * 0.42 + dna.attack_strength * 0.35 + dna.dissonance * 0.23)
    symmetry = clamp(dna.rhythmic_regularity * 0.56 + dna.key_strength * 0.18 + (1.0 - dna.section_contrast) * 0.26)
    density = clamp(0.16 + dna.rhythmic_density * 0.42 + dna.arousal * 0.20 + dna.harmonic_complexity * 0.22)
    texture_roughness = clamp(dna.roughness * 0.62 + dna.spectral_flatness * 0.24 + dna.dissonance * 0.14)
    edge_sharpness = clamp(dna.attack_strength * 0.54 + dna.spectral_contrast * 0.25 + dna.aggressiveness * 0.21)
    granularity = clamp(dna.spectral_flatness * 0.52 + dna.zero_crossing_rate * 0.24 + dna.roughness * 0.24)
    focal_size = clamp(0.22 + dna.bass_mass * 0.36 + dna.absolute_loudness * 0.18 - density * 0.10)
    focal_x = clamp(0.18 + dna.climax_position * 0.64)
    focal_y = clamp(0.70 - dna.brightness * 0.32 + dna.bass_mass * 0.15)
    repetition = clamp(dna.rhythmic_regularity * 0.62 + dna.rhythmic_density * 0.24 + dna.electronicness * 0.14)
    fragmentation = clamp(dna.dissonance * 0.43 + dna.section_contrast * 0.32 + dna.chord_change_rate * 0.25)
    flow = clamp(0.22 + dna.relaxation * 0.30 + dna.spectral_flux * 0.24 + (1.0 - dna.rhythmic_regularity) * 0.24)
    dispersion = clamp(dna.dynamic_complexity * 0.34 + dna.spectral_flatness * 0.24 + dna.arousal * 0.22 + dna.dissonance * 0.20)
    background_complexity = clamp(dna.harmonic_complexity * 0.28 + dna.section_count / 9.0 * 0.26 + density * 0.28 + fragmentation * 0.18)
    visual_weight = clamp(dna.bass_mass * 0.42 + dna.absolute_loudness * 0.25 + dna.tension * 0.19 + dna.darkness * 0.14)
    spatial_balance = clamp(symmetry * 0.52 + (1.0 - fragmentation) * 0.28 + dna.rhythmic_regularity * 0.20)
    directionality = clamp(dna.spectral_flux * 0.34 + dna.attack_strength * 0.27 + dna.largest_transition * 0.24 + dna.arousal * 0.15)
    geometry = (
        "continuous parametric field: "
        f"curvature {curvature:.2f}, angularity {angularity:.2f}, symmetry {symmetry:.2f}, "
        f"density {density:.2f}, flow {flow:.2f}, fragmentation {fragmentation:.2f}"
    )

    palette_scheme, palette = _build_palette(
        dna, primary_hue, saturation, luminance, contrast, variation
    )
    lighting = _lighting(dna, contrast)
    return VisualPlan(
        primary_hue=primary_hue,
        secondary_hue=secondary_hue,
        accent_hue=accent_hue,
        palette_width=palette_width,
        palette_temperature=temperature,
        saturation=saturation,
        luminance=luminance,
        contrast=contrast,
        geometry=geometry,
        curvature=curvature,
        angularity=angularity,
        symmetry=symmetry,
        density=density,
        texture_roughness=texture_roughness,
        edge_sharpness=edge_sharpness,
        granularity=granularity,
        focal_size=focal_size,
        focal_position=(focal_x, focal_y),
        repetition=repetition,
        fragmentation=fragmentation,
        flow=flow,
        dispersion=dispersion,
        background_complexity=background_complexity,
        visual_weight=visual_weight,
        spatial_balance=spatial_balance,
        directionality=directionality,
        palette_scheme=palette_scheme,
        palette=palette,
        lighting=lighting,
    )


def visual_plan_distance(left: VisualPlan, right: VisualPlan) -> float:
    hue_distance = min(abs(left.primary_hue - right.primary_hue), 360.0 - abs(left.primary_hue - right.primary_hue)) / 180.0
    numeric = (
        hue_distance,
        abs(left.saturation - right.saturation),
        abs(left.luminance - right.luminance),
        abs(left.contrast - right.contrast),
        abs(left.curvature - right.curvature),
        abs(left.angularity - right.angularity),
        abs(left.symmetry - right.symmetry),
        abs(left.density - right.density),
        abs(left.texture_roughness - right.texture_roughness),
        abs(left.focal_size - right.focal_size),
        abs(left.fragmentation - right.fragmentation),
        abs(left.flow - right.flow),
        abs(left.visual_weight - right.visual_weight),
    )
    geometry_bonus = 0.16 if left.geometry != right.geometry else 0.0
    return clamp(sum(numeric) / len(numeric) + geometry_bonus)


def _lighting(dna: VisualDNA, contrast: float) -> str:
    if dna.darkness > 0.62 and contrast > 0.58:
        return "low-key light with localized highlights and retained shadow detail"
    if dna.brightness > 0.64 and dna.valence > 0.55:
        return "open high-key light with crisp spectral highlights"
    if dna.section_contrast > 0.60:
        return "alternating pools of light that mirror section-to-section contrast"
    return "balanced directional light with a clear focal gradient"


def _build_palette(dna, primary_hue, saturation, luminance, contrast, variation):
    digest = hashlib.sha256(
        f"palette-v3|{dna.fingerprint}|{variation}|{dna.key}|{dna.mode}".encode("utf-8")
    ).digest()
    rng = random.Random(int.from_bytes(digest[:8], "little"))
    if dna.spectral_flatness > 0.64 or dna.aggressiveness > 0.68:
        candidates = ("dark_neon", "high_contrast", "saturated", "complementary", "triadic")
    elif dna.relaxation > 0.66 or dna.acousticness > 0.68:
        candidates = ("analogous", "pastel", "muted", "cold_dominant", "split_complementary")
    elif dna.valence > 0.64:
        candidates = ("triadic", "warm_dominant", "pastel", "saturated", "complementary")
    else:
        candidates = (
            "split_complementary", "dark_neon", "analogous", "triadic",
            "cold_dominant", "warm_dominant", "high_contrast",
        )
    scheme = rng.choice(candidates)
    offsets = {
        "analogous": (-58, -30, 0, 24, 52, 76),
        "complementary": (-24, 0, 22, 154, 180, 206),
        "split_complementary": (-28, 0, 25, 138, 218, 244),
        "triadic": (-18, 0, 34, 116, 222, 250),
        "dark_neon": (-36, 0, 42, 128, 178, 238),
        "pastel": (-42, -18, 12, 72, 142, 214),
        "muted": (-54, -20, 16, 62, 154, 224),
        "warm_dominant": (-34, -12, 10, 34, 58, 172),
        "cold_dominant": (-44, -16, 12, 46, 82, 178),
        "high_contrast": (-18, 0, 34, 162, 184, 218),
        "saturated": (-48, -10, 28, 88, 152, 218),
    }[scheme]
    count = rng.choices((3, 4, 5, 6), weights=(1, 4, 4, 1), k=1)[0]
    selected = list(offsets)
    while len(selected) < count:
        selected.append(rng.uniform(-180, 180))
    rng.shuffle(selected)
    selected = selected[:count]
    selected[0] = 0
    colors = []
    for index, offset in enumerate(selected):
        hue = (primary_hue + offset + rng.uniform(-8, 8)) % 360
        if scheme == "warm_dominant":
            hue = (22.0 + offset + rng.uniform(-7, 7)) % 360
            sat = rng.uniform(0.68, 0.98)
            value = rng.uniform(0.16, 0.34) if index == 0 else rng.uniform(0.62, 0.98)
        elif scheme == "cold_dominant":
            hue = (212.0 + offset + rng.uniform(-8, 8)) % 360
            sat = rng.uniform(0.54, 0.94)
            value = rng.uniform(0.14, 0.32) if index == 0 else rng.uniform(0.58, 0.96)
        elif scheme == "high_contrast":
            sat = rng.uniform(0.72, 1.0)
            value = rng.uniform(0.10, 0.24) if index == 0 else rng.uniform(0.76, 1.0)
        elif scheme == "saturated":
            sat = rng.uniform(0.78, 1.0)
            value = rng.uniform(0.14, 0.32) if index == 0 else rng.uniform(0.66, 1.0)
        elif scheme == "dark_neon":
            sat = clamp(saturation * rng.uniform(1.02, 1.35), 0.62, 1.0)
            value = rng.uniform(0.16, 0.40) if index == 0 else rng.uniform(0.62, 0.98)
        elif scheme == "pastel":
            sat = clamp(saturation * rng.uniform(0.46, 0.74), 0.24, 0.68)
            value = rng.uniform(0.28, 0.48) if index == 0 else rng.uniform(0.72, 0.96)
        elif scheme == "muted":
            sat = clamp(saturation * rng.uniform(0.48, 0.78), 0.22, 0.70)
            value = rng.uniform(0.18, 0.38) if index == 0 else rng.uniform(0.46, 0.80)
        else:
            sat = clamp(saturation * rng.uniform(0.90, 1.28), 0.52, 1.0)
            value = rng.uniform(0.13, 0.36) if index == 0 else clamp(
                luminance + rng.uniform(-0.04, 0.38) + contrast * 0.12, 0.48, 0.98
            )
        colors.append(hsv_hex(hue, sat, value))
    if scheme not in {"muted", "pastel"}:
        colors[-1] = hsv_hex(
            (primary_hue + selected[-1] + rng.uniform(-6, 6)) % 360,
            clamp(saturation + 0.18, 0.55, 1.0),
            clamp(0.82 + contrast * 0.16, 0.82, 1.0),
        )
    return scheme, tuple(colors)
