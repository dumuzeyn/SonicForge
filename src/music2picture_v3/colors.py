"""An independent cold-to-hot chromatic scale of measured rhythmic speed."""
import numpy as np
from PIL import Image, ImageOps

from music2picture_v2.custom_style import palette_rgb
from .renderer import smooth_field, flowing_time_coordinates

SPEED_COLOR_VERSION = 'rhythmic-speed-v2'
SPEED_PALETTE = ('#172C69', '#137FAD', '#40C8B0', '#EDD96B', '#EF743D', '#FFE6BD')


def apply_speed_colors(image, structure):
    texture = np.asarray(ImageOps.autocontrast(image.convert('L'), cutoff=1), dtype=np.float32) / 255
    values = structure.speed_curve or (0.,)
    profile = np.interp(np.linspace(0, 1, image.width), np.linspace(0, 1, len(values)), values)[None, :]
    profile = smooth_field(profile, max(3, image.width * .035))[0]
    time = flowing_time_coordinates(image.height, image.width, .6)
    speed = np.interp(time, np.linspace(0, 1, image.width), profile)
    position = np.clip(.10 + speed * .78 + (texture - .5) * .16, 0, 1)
    lookup = palette_rgb(SPEED_PALETTE, np.linspace(0, 1, 4096))
    rgb = lookup[np.rint(position * 4095).astype(np.uint16)].astype(np.float32)
    rgb *= (.40 + texture * .76)[..., None]
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), 'RGB')
