"""Validated, per-user custom artwork preferences, independent of the bundle."""
import json
import os
from pathlib import Path
import tempfile

from music2picture_v2.custom_style import CustomCoverSettings

MAX_PREFERENCE_BYTES = 8 * 1024 * 1024


def preference_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'SonicForge' / 'custom_cover.json'


def load_custom_cover_settings():
    path = preference_path()
    try:
        if path.is_symlink():
            return None
        with path.open('rb') as source:
            data = source.read(MAX_PREFERENCE_BYTES + 1)
        if len(data) > MAX_PREFERENCE_BYTES:
            return None
        return CustomCoverSettings.parse(json.loads(data)).to_dict()
    except (OSError, ValueError, TypeError, RecursionError):
        # Missing, malformed or future incompatible settings never block startup.
        return None


def save_custom_cover_settings(settings):
    settings = CustomCoverSettings.parse(settings).to_dict()
    data = json.dumps(settings, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    if len(data) > MAX_PREFERENCE_BYTES:
        raise ValueError('Custom artwork preferences exceed the safe file size limit')
    path = preference_path()
    if path.is_symlink():
        raise ValueError('A linked file cannot be used to save artwork preferences')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.custom-cover-', suffix='.tmp',
                                         dir=path.parent, delete=False) as destination:
            temporary = Path(destination.name)
            destination.write(data)
            destination.flush()
            os.fsync(destination.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return settings
