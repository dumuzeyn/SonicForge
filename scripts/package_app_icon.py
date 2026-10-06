"""Package the approved PNG artwork as multi-resolution Windows ICO."""
from pathlib import Path
import sys
from PIL import Image


def main():
    source = Path(sys.argv[1]).resolve(strict=True)
    destination = Path(sys.argv[2]).resolve()
    with Image.open(source) as image:
        if image.mode != 'RGBA' or image.getchannel('A').getextrema()[0] != 0:
            raise ValueError('The icon source must have genuine transparency')
        image.save(destination, format='ICO', sizes=[(16, 16), (20, 20), (24, 24),
                                                    (32, 32), (40, 40), (48, 48),
                                                    (64, 64), (128, 128), (256, 256)])
    with Image.open(destination) as icon:
        print('Packaged icon sizes:', sorted(icon.ico.sizes()))


if __name__ == '__main__':
    main()
