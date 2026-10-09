from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, replace

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .models import VisualDNA, VisualPlan
from .utils import clamp
from .character import musical_character, accent_mask, palette_positions


GENERATOR_VERSION = "contour-character-v5"
COMPOSITIONS = (
    "diagonal_pour",
    "vortex_marbling",
    "radial_bloom",
    "cellular_islands",
    "folded_currents",
)


@dataclass(frozen=True)
class ArtisticParameters:
    composition: str
    energy: float
    tempo_scale: float
    macro_scale: float
    meso_scale: float
    micro_scale: float
    warp_strength: float
    turbulence: float
    vein_strength: float
    color_regions: int
    contrast: float
    saturation: float
    grain: float
    direction_angle: float
    palette_position: float
    opposite_position: float
    accent_share: float

    def to_dict(self):
        return asdict(self)


def render_cover(
    visual_dna: VisualDNA,
    visual_plan: VisualPlan,
    size: int = 1000,
    seed: int | None = None,
    preview: bool = False,
    detail: float | None = None,
    palette: tuple[str, ...] | None = None,
    palette_stops: tuple[float, ...] | None = None,
) -> Image.Image:
    """Render an organic, texture-first album cover without signal traces."""
    requested_size = max(64, int(size))
    work_limit = 384 if preview else 640
    work_size = max(192, min(requested_size, work_limit))
    resolved_seed = deterministic_seed(visual_dna.fingerprint, seed)
    rng = np.random.default_rng(resolved_seed)
    parameters = artistic_parameters(visual_dna, visual_plan, resolved_seed)
    parameters = customize_parameters(parameters, detail)
    texture = _artistic_texture(visual_dna, visual_plan, parameters, work_size, rng,
                                palette=palette, palette_stops=palette_stops)
    image = _finish(texture, visual_dna, visual_plan, parameters, rng,
                    preserve_palette=palette is not None)
    if image.size != (requested_size, requested_size):
        image = image.resize((requested_size, requested_size), Image.Resampling.LANCZOS)
    return image.convert("RGB")


def customize_parameters(parameters, detail=None):
    if detail is None:
        return parameters
    amount = clamp(float(detail) / 100)
    return replace(
        parameters, meso_scale=clamp(parameters.meso_scale * (.5 + amount)),
        micro_scale=clamp(parameters.micro_scale * (.25 + amount * 1.5)),
        vein_strength=clamp(parameters.vein_strength * (.5 + amount)),
        grain=clamp(parameters.grain * (.3 + amount * 1.4)),
    )


def deterministic_seed(fingerprint: str, seed: int | None = None) -> int:
    payload = f"{GENERATOR_VERSION}|{fingerprint}|{0 if seed is None else int(seed)}"
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).digest()
    return int.from_bytes(digest[:8], "little") & 0x7FFFFFFF


def artistic_parameters(dna: VisualDNA, plan: VisualPlan, resolved_seed: int | None = None) -> ArtisticParameters:
    seed = deterministic_seed(dna.fingerprint, resolved_seed) if resolved_seed is None else int(resolved_seed)
    rng = np.random.default_rng(seed ^ 0x5F3759DF)
    character = musical_character(dna)
    energy = character.drive
    tempo_scale = clamp((dna.tempo - 48.0) / 158.0) * dna.tempo_confidence
    high_detail = clamp(
        dna.brightness * 0.34
        + dna.spectral_centroid * 0.24
        + dna.spectral_flux * 0.22
        + dna.zero_crossing_rate * 0.20
    )
    chaos = clamp(dna.spectral_flatness * 0.46 + dna.roughness * 0.28 + dna.dissonance * 0.26)
    # Musical evidence chooses the family; Seed only varies its fine layout.
    if dna.spectral_flatness > .6 and dna.rhythmic_density < .35:
        composition = 'cellular_islands'
    elif energy > .55 and dna.rhythmic_regularity > .58:
        composition = 'folded_currents'
    elif energy > .65 or dna.aggressiveness > .7:
        composition = 'diagonal_pour'
    elif dna.bass_mass > .6 and energy < .45:
        composition = 'radial_bloom'
    elif energy > .4:
        composition = 'vortex_marbling'
    else:
        composition = 'folded_currents'
    return ArtisticParameters(
        composition=composition,
        energy=energy,
        tempo_scale=tempo_scale,
        macro_scale=clamp(0.82 - dna.bass_mass * 0.50 + energy * 0.08, 0.22, 0.90),
        meso_scale=clamp(0.28 + tempo_scale * 0.40 + dna.harmonic_complexity * 0.22),
        micro_scale=clamp(.08 + high_detail * .35 + energy * .48),
        warp_strength=clamp(.08 + energy * .42 + chaos * .20 + dna.section_contrast * .12),
        turbulence=clamp(.05 + energy * .52 + chaos * .24 + dna.dynamic_complexity * .10),
        vein_strength=clamp(.06 + high_detail * .25 + dna.spectral_contrast * .12 + energy * .48),
        color_regions=len(plan.palette),
        contrast=clamp(0.34 + energy * 0.26 + dna.original_dynamic_range * 0.25 + plan.contrast * 0.15),
        saturation=clamp(plan.saturation * 0.64 + energy * 0.22 + rng.uniform(0.02, 0.15), 0.28, 0.98),
        grain=clamp(0.04 + plan.granularity * 0.30 + high_detail * 0.16, 0.02, 0.48),
        direction_angle=float((plan.directionality * math.tau + rng.uniform(-.15, .15)) % math.tau),
        palette_position=character.drive,
        opposite_position=character.opposite_drive,
        accent_share=character.accent_share,
    )


def _artistic_texture(dna, plan, params, size, rng, *, palette=None, palette_stops=None):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    x = x / max(1, size - 1) * 2.0 - 1.0
    y = y / max(1, size - 1) * 2.0 - 1.0

    warp_cells = int(2 + params.turbulence * 2)
    warp_x = _fbm(size, warp_cells, 3, rng, persistence=.42) * 2.0 - 1.0
    warp_y = _fbm(size, warp_cells + 1, 3, rng, persistence=.40) * 2.0 - 1.0
    xw, yw = _composition_coordinates(x, y, warp_x, warp_y, dna, plan, params)

    macro_cells = max(2, int(2 + (1.0 - params.macro_scale) * 4))
    meso_cells = int(5 + params.meso_scale * 8)
    micro_cells = int(15 + params.micro_scale * 22)
    macro = _sample_wrapped(_fbm(size, macro_cells, 3, rng, .40), xw, yw)
    macro_b = _sample_wrapped(_fbm(size, macro_cells + 1, 2, rng, .35), xw * .92, yw * .92)
    meso = _sample_wrapped(_fbm(size, meso_cells, 3, rng, .42), xw * 1.10, yw * 1.10)
    micro = _sample_wrapped(_fbm(size, micro_cells, 2, rng, 0.45), xw * 1.46, yw * 1.46)
    cellular = _cellular_field(xw, yw, 3 + int(dna.bass_mass * 4), rng)

    angle = params.direction_angle
    directional = xw * math.cos(angle) + yw * math.sin(angle)
    cross = -xw * math.sin(angle) + yw * math.cos(angle)
    flow_frequency = 0.72 + params.tempo_scale * 1.15 + dna.rhythmic_density * 0.45
    phase = directional * math.pi * flow_frequency
    phase += (macro_b - .5) * math.pi * (1.2 + params.warp_strength * 2.0)
    phase += (meso - .5) * (.25 + params.turbulence * .50)
    phase += np.sin(cross * math.pi * (0.7 + dna.harmonic_complexity * 1.1)) * (0.28 + params.turbulence * 0.55)
    currents = np.sin(phase) * 0.5 + 0.5
    folds = np.sin(phase * (0.82 + dna.chord_change_rate * 0.45) + macro_b * 1.8) * 0.5 + 0.5

    fx = plan.focal_position[0] * 2.0 - 1.0
    fy = plan.focal_position[1] * 2.0 - 1.0
    radial_x = xw - fx
    radial_y = yw - fy
    radius = np.sqrt(radial_x * radial_x + radial_y * radial_y)
    polar = np.arctan2(radial_y, radial_x)
    if params.composition == "diagonal_pour":
        composition_field = _normalize(directional + (macro_b - 0.5) * 0.46)
    elif params.composition == "vortex_marbling":
        arms = 2 + round(dna.harmonic_complexity * 2.0)
        composition_field = np.sin(
            polar * arms + radius * (3.4 + params.turbulence * 2.4) + (meso - 0.5) * 1.2
        ) * 0.5 + 0.5
    elif params.composition == "radial_bloom":
        bloom = 1.0 - radius / (1.10 + plan.focal_size * 0.75)
        petals = np.cos(polar * (3 + round(dna.rhythmic_regularity * 4))) * (0.06 + params.turbulence * 0.08)
        composition_field = np.clip(bloom + petals + (macro_b - 0.5) * 0.18, 0.0, 1.0)
    elif params.composition == "cellular_islands":
        composition_field = cellular
    else:
        composition_field = folds

    base_field = _normalize(macro * .10 + macro_b * .10 + composition_field * .46 + currents * .34)
    character = musical_character(dna)
    minority = accent_mask(base_field.shape, character, base_field)
    if character.accent_share:
        # Modulate the existing folds, not replace a disk with unrelated noise.
        detail_delta = character.opposite_drive - character.drive
        base_field = np.clip(base_field + (meso - .5) * minority * detail_delta * .22, 0, 1)
    from .custom_style import palette_rgb
    lookup = palette_rgb(plan.palette if palette is None else palette,
                         np.linspace(0, 1, 4096), palette_stops)
    positions = palette_positions(base_field, dna, minority)
    rgb = lookup[np.rint(positions * 4095).astype(np.uint16)].astype(np.float32)
    # Tonal depth is independent of hue selection, including a one-color palette.
    local_drive = params.energy * (1 - minority) + character.opposite_drive * minority
    rgb *= (.52 + .52 * base_field)[..., None]
    # Fine lamination follows the broad folds instead of adding speckled noise.
    # Energetic music has more strata; quiet material stays open and spacious.
    strata = .5 + .5 * np.sin(base_field * math.pi * (2 + local_drive * 6)
                              + (meso - .5) * .18)
    rgb *= (.86 + .14 * strata)[..., None]
    stratum_edge = np.exp(-((strata - .91) / .045) ** 2)
    edge_alpha = stratum_edge[..., None] * (.025 + local_drive[..., None] * .045)
    rgb = rgb * (1 - edge_alpha) + (rgb * .55 + 125) * edge_alpha

    ribbon_width = .028 + (1 - params.vein_strength) * .040
    ribbons = np.exp(-((currents - .56) / ribbon_width) ** 2)
    ribbons *= .35 + .65 * _smoothstep(.22, .78, macro_b)
    ribbon_alpha = ribbons[..., None] * (.08 + params.vein_strength * .18)
    highlight = rgb * .45 + 140
    rgb = rgb * (1 - ribbon_alpha) + highlight * ribbon_alpha
    # A narrow shadow next to a highlight gives folds depth without pixel edges.
    creases = np.exp(-((currents - .47) / (ribbon_width * 1.8)) ** 2)
    rgb *= (1 - creases * (.08 + local_drive * .12))[..., None]
    rgb += (micro - .5)[..., None] * (.8 + params.micro_scale * 1.8)

    fx, fy = plan.focal_position
    distance = np.sqrt((x - (fx * 2 - 1)) ** 2 + (y - (fy * 2 - 1)) ** 2)
    illumination = np.exp(-distance * (1.3 + (1.0 - plan.focal_size) * 1.8))
    illumination = (illumination - 0.35) * (10.0 + params.contrast * 20.0)
    rgb += illumination[..., None]
    return np.uint8(np.clip(rgb, 0, 255))


def _composition_coordinates(x, y, warp_x, warp_y, dna, plan, params):
    strength = 0.12 + params.warp_strength * 0.36
    xw = x + warp_x * strength
    yw = y + warp_y * strength
    fx, fy = plan.focal_position[0] * 2.0 - 1.0, plan.focal_position[1] * 2.0 - 1.0
    dx, dy = xw - fx, yw - fy
    radius = np.sqrt(dx * dx + dy * dy) + 1e-5
    angle = np.arctan2(dy, dx)
    if params.composition == "vortex_marbling":
        twist = (1.1 + params.turbulence * 3.6) * np.exp(-radius * 0.72)
        angle += twist + warp_x * 0.35
        xw, yw = fx + np.cos(angle) * radius, fy + np.sin(angle) * radius
    elif params.composition == "radial_bloom":
        pulse = np.sin(radius * math.pi * (2.0 + params.tempo_scale * 3.2) + warp_y * 2.5)
        xw += dx / radius * pulse * strength * 0.42
        yw += dy / radius * pulse * strength * 0.42
    elif params.composition == "cellular_islands":
        xw += np.sin(yw * math.pi * 1.8 + warp_y * 2.2) * strength * 0.34
        yw += np.sin(xw * math.pi * 1.5 - warp_x * 2.0) * strength * 0.34
    elif params.composition == "folded_currents":
        fold = np.sin((xw + yw) * math.pi * (1.2 + dna.rhythmic_regularity * 2.2))
        xw += fold * strength * 0.38
        yw -= fold * strength * 0.22
    else:
        drift = xw * math.cos(params.direction_angle) + yw * math.sin(params.direction_angle)
        xw += np.sin(drift * math.pi * 1.7 + warp_y * 2.6) * strength * 0.30
        yw += np.cos(drift * math.pi * 1.3 + warp_x * 2.1) * strength * 0.20
    return xw, yw


def _fbm(size, base_cells, octaves, rng, persistence=0.55):
    result = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    total = 0.0
    cells = max(2, int(base_cells))
    for _ in range(max(1, int(octaves))):
        result += _value_noise(size, cells, rng) * amplitude
        total += amplitude
        amplitude *= persistence
        cells = min(size // 2, max(cells + 1, cells * 2))
    return _normalize(result / max(total, 1e-6))


def _value_noise(size, cells, rng):
    # Periodic quintic interpolation: wrapped sampling must not expose seams
    # between unrelated opposite image edges after coordinate distortion.
    grid = rng.random((cells, cells), dtype=np.float32)
    position = np.arange(size, dtype=np.float32) * cells / size
    lower = np.floor(position).astype(np.int32)
    fraction = position - lower
    weight = fraction ** 3 * (fraction * (fraction * 6 - 15) + 10)
    upper = (lower + 1) % cells
    rows = grid[lower[:, None], lower[None, :]] * (1 - weight[None, :])
    rows += grid[lower[:, None], upper[None, :]] * weight[None, :]
    next_rows = grid[upper[:, None], lower[None, :]] * (1 - weight[None, :])
    next_rows += grid[upper[:, None], upper[None, :]] * weight[None, :]
    return rows * (1 - weight[:, None]) + next_rows * weight[:, None]


def _sample_wrapped(field, x, y):
    height, width = field.shape
    px = np.mod((x + 1.0) * 0.5, 1.0) * width
    py = np.mod((y + 1.0) * 0.5, 1.0) * height
    x0 = np.floor(px).astype(np.int32)
    y0 = np.floor(py).astype(np.int32)
    wx = px - x0
    wy = py - y0
    x0 %= width
    y0 %= height
    x1 = (x0 + 1) % width
    y1 = (y0 + 1) % height
    return (
        field[y0, x0] * (1.0 - wx) * (1.0 - wy)
        + field[y0, x1] * wx * (1.0 - wy)
        + field[y1, x0] * (1.0 - wx) * wy
        + field[y1, x1] * wx * wy
    )


def _cellular_field(x, y, point_count, rng):
    points = rng.uniform(-1.15, 1.15, (max(3, int(point_count)), 2)).astype(np.float32)
    nearest = np.full(x.shape, 10.0, dtype=np.float32)
    second = np.full(x.shape, 10.0, dtype=np.float32)
    for px, py in points:
        distance = (x - px) ** 2 + (y - py) ** 2
        replace = distance < nearest
        second = np.where(replace, nearest, np.minimum(second, distance))
        nearest = np.where(replace, distance, nearest)
    cells = np.sqrt(nearest)
    borders = np.sqrt(np.maximum(second, 0.0)) - cells
    return _normalize(cells * 0.62 + (1.0 - _normalize(borders)) * 0.38)


def _smoothstep(low, high, value):
    amount = np.clip((value - low) / max(high - low, 1e-6), 0.0, 1.0)
    return amount * amount * (3.0 - 2.0 * amount)


def _finish(array, dna, plan, params, rng, *, preserve_palette=False):
    image = Image.fromarray(array, "RGB")
    blur_radius = 0.72 + (1.0 - plan.edge_sharpness) * 1.25
    softened = image.filter(ImageFilter.GaussianBlur(blur_radius))
    image = Image.blend(image, softened, 0.24 + (1.0 - params.energy) * 0.16)
    if not preserve_palette:
        image = ImageEnhance.Color(image).enhance(0.88 + params.saturation * 0.52)
        image = ImageEnhance.Contrast(image).enhance(0.94 + params.contrast * 0.32)
    if plan.edge_sharpness > 0.58 and params.energy > 0.56:
        image = image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=24, threshold=8))
    pixels = np.asarray(image, dtype=np.float32)
    grain = rng.normal(0.0, 1.0, pixels.shape[:2]).astype(np.float32)
    pixels = np.clip(pixels + grain[..., None] * (0.7 + params.grain * 4.4), 0, 255)
    return Image.fromarray(np.uint8(pixels), "RGB")


def _normalize(field):
    low, high = np.percentile(field, (1.0, 99.0))
    if high - low < 1e-6:
        return np.zeros_like(field, dtype=np.float32)
    return np.clip((field - low) / (high - low), 0.0, 1.0).astype(np.float32)
