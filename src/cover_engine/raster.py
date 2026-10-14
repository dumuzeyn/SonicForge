"""Area coverage for supersampled ink, without ringing around high-contrast edges."""
from PIL import Image, ImageFilter


def downsample_coverage(mask, size):
    mask = mask.convert('L')
    if mask.size != size:
        # BOX integrates subpixel coverage. Lanczos ringing can make thin
        # strokes alternate in weight or add a bright fringe along diagonals.
        mask = mask.resize(size, Image.Resampling.BOX)
    # A fraction of one output pixel stabilizes diagonal edge coverage; the
    # background, letter interiors and symbol material are never blurred.
    return mask.filter(ImageFilter.GaussianBlur(.20))
