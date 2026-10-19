"""An independent cold-to-hot chromatic scale of measured rhythmic speed."""
import numpy as np
from PIL import Image, ImageOps

from music2picture_v2.custom_style import palette_rgb
from .renderer import smooth_field, flowing_time_coordinates

SPEED_COLOR_VERSION = 'rhythmic-speed-v4'
SPEED_PALETTE = ('#21103F', '#5E2A92', '#173D87', '#157FAF', '#40C8B0', '#EDD96B', '#EF743D', '#DB283D', '#870D24')
SPEED_STOPS = (0, .12, .24, .35, .45, .55, .65, .75, 1)


def apply_speed_colors(image, structure):
    texture = np.asarray(ImageOps.autocontrast(image.convert('L'), cutoff=1), dtype=np.float32) / 255
    values = structure.speed_curve or (0.,)
    profile = np.interp(np.linspace(0, 1, image.width), np.linspace(0, 1, len(values)), values)[None, :]
    profile = smooth_field(profile, max(3, image.width * .065))[0]
    time = flowing_time_coordinates(image.height, image.width, .6)
    speed = np.interp(time, np.linspace(0, 1, image.width), profile)
    position = np.clip(.10 + speed * .78 + (texture - .5) * .38, 0, 1)
    lookup = palette_rgb(SPEED_PALETTE, np.linspace(0, 1, 4096), SPEED_STOPS)
    rgb = lookup[np.rint(position * 4095).astype(np.uint16)].astype(np.float32)
    rgb *= (.40 + texture * .76)[..., None]
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), 'RGB')
