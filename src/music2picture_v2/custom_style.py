"""Validated, reproducible background controls for the custom artwork style."""
from dataclasses import asdict, dataclass
import math
import re

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


@dataclass(frozen=True)
class CustomCoverSettings:
    pattern: str = "modern"
    colors: tuple[str, ...] = ("#6551c7", "#e89096")
    positions: tuple[float, ...] = ()
    detail: float = 50
    contrast: float = 100
    saturation: float = 100
    softness: float = 0

    @classmethod
    def parse(cls, value=None):
        if isinstance(value, cls):
            value = asdict(value)
        if value is not None and not isinstance(value, dict):
            raise ValueError("Custom cover settings must be a dictionary")
        value = dict(value or {})
        # Keep previously saved two-color profiles usable.
        low = value.pop("color_low", cls().colors[0])
        high = value.pop("color_high", cls().colors[-1])
        colors = value.get("colors", (low, high))
        if not isinstance(colors, (list, tuple)) or not colors:
            raise ValueError("Palette must contain at least one color")
        value["colors"] = tuple(colors)
        positions = value.get("positions", ())
        if not isinstance(positions, (list, tuple)):
            raise ValueError("Palette positions must be a list")
        if not positions:
            positions = tuple(float(item) for item in np.linspace(0, 1, len(colors)))
        if len(positions) != len(colors):
            raise ValueError("Every palette color needs a position")
        for position in positions:
            if isinstance(position, bool) or not isinstance(position, (int, float)):
                raise ValueError("Palette positions must be numbers")
            if not math.isfinite(position) or not 0 <= position <= 1:
                raise ValueError("Palette positions must be between 0 and 1")
        if any(left > right for left, right in zip(positions, positions[1:])):
            raise ValueError("Palette positions must be ordered")
        value["positions"] = tuple(positions)
        try:
            settings = cls(**value)
        except TypeError as exc:
            raise ValueError("Unknown custom cover setting") from exc
        if settings.pattern not in ("modern", "legacy"):
            raise ValueError("Unknown custom artwork pattern")
        for color in settings.colors:
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Palette colors must use #RRGGBB")
        for key, lower, upper in (("detail", 0, 100), ("contrast", 50, 150),
                                  ("saturation", 0, 150), ("softness", 0, 100)):
            number = getattr(settings, key)
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ValueError(f"{key} must be a number")
            if not math.isfinite(number) or not lower <= number <= upper:
                raise ValueError(f"{key} must be between {lower} and {upper}")
        return settings

    def to_dict(self):
        data = asdict(self)
        data["colors"] = list(self.colors)
        data["positions"] = list(self.positions)
        return data


def palette_rgb(colors, positions, stops=None):
    """Interpolate every user stop in its given order, without a stop-count cap."""
    swatches = np.asarray([tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
                           for color in colors], dtype=np.float32)
    if len(swatches) == 1:
        # A single chosen hue still has tonal texture, rather than a flat fill.
        swatches = np.vstack((swatches * .22, swatches))
        stops = None
    if stops is None or len(stops) == 0:
        stops = np.linspace(0, 1, len(swatches))
    position = np.clip(np.asarray(positions), 0, 1)
    return np.uint8(np.clip(np.stack([np.interp(position, stops, swatches[:, channel])
                                     for channel in range(3)], axis=-1), 0, 255))


def finish_custom_background(image, settings, visual_dna=None, *, recolor=True):
    """Apply palette and filters before typography so lettering stays sharp."""
    settings = CustomCoverSettings.parse(settings)
    if not recolor:
        return _apply_filters(image, settings)
    luminance = ImageOps.autocontrast(image.convert("L"), cutoff=1)
    # Build the 8-bit lookup once instead of allocating three image-sized
    # float64 interpolation arrays, especially for 4096px output.
    if visual_dna is None:
        lookup = palette_rgb(settings.colors, np.arange(256, dtype=np.float64) / 255, settings.positions)
        pixels = lookup[np.asarray(luminance)]
    else:
        from .character import palette_positions, musical_character, accent_mask
        texture = np.asarray(luminance, dtype=np.float32) / 255
        character = musical_character(visual_dna)
        minority = accent_mask(texture.shape, character, texture)
        positions = palette_positions(texture, visual_dna, minority)
        lookup = palette_rgb(settings.colors, np.linspace(0, 1, 4096), settings.positions)
        pixels = lookup[np.rint(positions * 4095).astype(np.uint16)]
        local_drive = character.drive * (1 - minority) + character.opposite_drive * minority
        shade = .46 + texture * (.62 + .10 * local_drive)
        pixels = np.uint8(np.clip(pixels.astype(np.float32) * shade[..., None], 0, 255))
    image = Image.fromarray(pixels, "RGB")
    return _apply_filters(image, settings)


def _apply_filters(image, settings):
    image = image.convert('RGB')
    image = ImageEnhance.Contrast(image).enhance(settings.contrast / 100)
    image = ImageEnhance.Color(image).enhance(settings.saturation / 100)
    if settings.softness:
        image = image.filter(ImageFilter.GaussianBlur(image.width * .008 * settings.softness / 100))
    return image.convert("RGB")
