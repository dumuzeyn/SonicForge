"""Shared source discovery; generated projects must never become input again."""

import os
from pathlib import Path


PROJECT_FOLDER = "SonicForgeProgect"


def default_output_path(source):
    return Path(source).expanduser().parent / PROJECT_FOLDER


def find_audio_files(source, extensions):
    source = Path(source)
    if source.is_file():
        return [source] if source.suffix.lower() in extensions else []
    files = []
    for folder, directories, names in os.walk(source, followlinks=False):
        directories[:] = [
            name for name in directories
            if name.casefold() not in {PROJECT_FOLDER.casefold(), ".sonicforge"}
            and not name.casefold().startswith("musicpolisher_")
        ]
        files.extend(
            Path(folder) / name for name in names
            if Path(name).suffix.lower() in extensions
        )
    return sorted(files, key=lambda path: str(path).casefold())
