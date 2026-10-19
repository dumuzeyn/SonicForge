"""Keep embedded artwork below the tag limits of common lyric readers."""
from io import BytesIO

from PIL import Image

from audio_tags import ID3Frame

COMPATIBLE_TAG_BYTES = 1024 * 1024
ARTWORK_BUDGET = 512 * 1024


def _image_bytes(image, budget, transparent=False):
    image = image.copy()
    for _ in range(16):
        for quality in ((None,) if transparent else (95, 92, 90)):
            output = BytesIO()
            if transparent:
                image.save(output, 'PNG', optimize=True)
                mime = b'image/png'
            else:
                # Streaming encoding avoids libjpeg's small optimized-output
                # buffer on detailed 4:4:4 covers. Keep chroma at full resolution.
                image.convert('RGB').save(output, 'JPEG', quality=quality, subsampling=0)
                mime = b'image/jpeg'
            if output.tell() <= budget:
                return mime, output.getvalue()
        image.thumbnail((max(1, round(image.width * .85)), max(1, round(image.height * .85))), Image.Resampling.LANCZOS)
    raise ValueError('Artwork cannot fit the compatible tag size limit')


def compact_artwork(frames):
    """Recode only oversized APIC images; preserve all other frame payloads."""
    frames = list(frames)
    total = 10 + 1024 + sum(10 + len(frame.payload) for frame in frames)
    if total < COMPATIBLE_TAG_BYTES:
        return frames
    pictures = [frame for frame in frames if frame.name == 'APIC']
    if not pictures:
        return frames
    non_artwork = 10 + 1024 + sum(10 + len(frame.payload) for frame in frames if frame.name != 'APIC')
    budget = min(ARTWORK_BUDGET, (COMPATIBLE_TAG_BYTES - non_artwork - 4096) // len(pictures))
    if budget < 16 * 1024:
        raise ValueError('Other metadata leaves insufficient room for compatible artwork')
    result = []
    for frame in frames:
        if frame.name != 'APIC':
            result.append(frame)
            continue
        if frame.flags != b'\0\0':
            raise ValueError('Compressed or flagged artwork requires a different tag editor')
        payload = frame.payload
        mime_end = payload.index(b'\0', 1)
        description_start = mime_end + 2
        width = 2 if payload[0] in (1, 2) else 1
        end = description_start
        while end + width <= len(payload) and payload[end:end + width] != b'\0' * width:
            end += width
        image_start = end + width
        with Image.open(BytesIO(payload[image_start:])) as image:
            mime, data = _image_bytes(image, budget, 'A' in image.getbands() or 'transparency' in image.info)
        header = payload[:1] + mime + b'\0' + payload[mime_end + 1:image_start]
        result.append(ID3Frame('APIC', header + data))
    if 10 + 1024 + sum(10 + len(frame.payload) for frame in result) >= COMPATIBLE_TAG_BYTES:
        raise ValueError('Artwork descriptions exceed the compatible tag limit')
    return result
