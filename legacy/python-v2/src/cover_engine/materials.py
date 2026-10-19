"""Palette-derived inks shared by lettering, focal symbols and supporting art."""
import colorsys

import numpy as np

VERSION = 'shared-palette-inks-v1'


def cover_material(image):
    sample = image.convert('RGB').resize((64, 64))
    entries = sample.quantize(colors=8).convert('RGB').getcolors(4096) or [(4096, (90, 120, 150))]
    def score(entry):
        count, rgb = entry
        _, saturation, value = colorsys.rgb_to_hsv(*(v / 255 for v in rgb))
        return count ** .5 * (.18 + saturation) * (.25 + min(value, .85))
    entries.sort(key=score, reverse=True)
    base = entries[0][1]
    hue, saturation, _ = colorsys.rgb_to_hsv(*(v / 255 for v in base))
    saturation = min(.72, max(.28, saturation * .72)) if saturation > .08 else .08
    def color(lightness, saturation_scale=1, hue_shift=0):
        return tuple(round(c * 255) for c in colorsys.hls_to_rgb(
            (hue + hue_shift) % 1, lightness, saturation * saturation_scale))
    return dict(version=VERSION, source_color=base,
                light_ink=color(.80), dark_ink=color(.23, 1.1),
                secondary_ink=color(.66, 1.05, .045),
                dark_backing=color(.035, .85), light_backing=color(.97, .7),
                shadow=color(.07, .8))


def ink_candidates(material):
    return ((True, material['light_ink']), (False, material['dark_ink']))


def backing_for_ink(material, ink):
    # An opposite tone of the same material separates ink locally without a
    # monochrome sticker or a disconnected black/white symbol.
    level = np.asarray(ink) @ np.array([.2126, .7152, .0722]) / 255
    return material['dark_backing'] if level > .45 else material['light_backing']
