"""Narrow, local-file validation for media accepted by Sonic Forge.

The application never executes selected media.  These checks additionally reject
links, device files, misleading extensions and oversized images before a decoder
is allowed to inspect them.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from PIL import Image, UnidentifiedImageError


AUDIO_EXTENSIONS = frozenset({".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma"})
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000


class UnsafeMediaError(ValueError):
    """The selected path is not a supported, ordinary local media file."""


def _ordinary_local_file(path: str | os.PathLike, allowed_extensions: frozenset[str]) -> Path:
    candidate = Path(path).expanduser()
    if candidate.suffix.lower() not in allowed_extensions:
        raise UnsafeMediaError(f"Unsupported file type: {candidate.suffix or '(none)'}")
    if not candidate.exists() or not candidate.is_file():
        raise UnsafeMediaError("The selected file does not exist or is not a regular file.")
    if candidate.is_symlink():
        raise UnsafeMediaError("Links are not accepted as media input.")
    mode = candidate.stat().st_mode
    if not stat.S_ISREG(mode):
        raise UnsafeMediaError("Only ordinary local files are accepted.")
    return candidate.resolve(strict=True)


def validate_audio_file(path: str | os.PathLike) -> Path:
    """Check that an audio extension agrees with a small, fixed file signature."""
    candidate = _ordinary_local_file(path, AUDIO_EXTENSIONS)
    with candidate.open("rb") as stream:
        header = stream.read(64)
    suffix = candidate.suffix.lower()
    valid = {
        ".mp3": header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0),
        ".flac": header.startswith(b"fLaC"),
        ".wav": header.startswith(b"RIFF") and header[8:12] == b"WAVE",
        ".m4a": len(header) >= 12 and header[4:8] == b"ftyp",
        ".aac": len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 in (0xF0, 0xF4),
        ".ogg": header.startswith(b"OggS"),
        ".opus": header.startswith(b"OggS") and b"OpusHead" in header,
        ".wma": header.startswith(bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c")),
    }[suffix]
    if not valid:
        raise UnsafeMediaError("The file contents do not match its audio extension.")
    return candidate


def validate_image_file(path: str | os.PathLike) -> Path:
    """Fully parse image structure without retaining decoded pixels."""
    candidate = _ordinary_local_file(path, IMAGE_EXTENSIONS)
    if candidate.stat().st_size > MAX_IMAGE_BYTES:
        raise UnsafeMediaError("The image is larger than 50 MB.")
    try:
        with Image.open(candidate) as image:
            if image.format not in IMAGE_FORMATS:
                raise UnsafeMediaError("Only PNG, JPEG and WebP images are accepted.")
            width, height = image.size
            if width < 16 or height < 16:
                raise UnsafeMediaError("The image is too small.")
            if width * height > MAX_IMAGE_PIXELS:
                raise UnsafeMediaError("The image dimensions are too large.")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise UnsafeMediaError("The selected image is damaged or is not a supported image.") from exc
    return candidate


def validate_source(source: str | os.PathLike) -> tuple[Path, list[Path]]:
    """Resolve a source and validate every discovered audio file before processing."""
    from audio_paths import find_audio_files

    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise UnsafeMediaError("The selected source does not exist.")
    if source_path.is_symlink():
        raise UnsafeMediaError("Links are not accepted as a source.")
    source_path = source_path.resolve(strict=True)
    files = find_audio_files(source_path, AUDIO_EXTENSIONS)
    if not files:
        raise UnsafeMediaError("No supported audio files were found.")
    return source_path, [validate_audio_file(path) for path in files]


def validate_output_directory(source: Path, output: str | os.PathLike) -> Path:
    """Keep output distinct from the source and reject an existing link target."""
    output_path = Path(output).expanduser()
    if output_path.exists() and output_path.is_symlink():
        raise UnsafeMediaError("A linked folder cannot be used as the output folder.")
    resolved = output_path.resolve(strict=False)
    if resolved == source:
        raise UnsafeMediaError("The output folder must be different from the source.")
    return resolved
