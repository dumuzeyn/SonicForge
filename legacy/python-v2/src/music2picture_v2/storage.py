from __future__ import annotations

import json
import hashlib
import os
import threading
from pathlib import Path
from typing import Any

from .models import AnalysisBundle


STORE_VERSION = 1


def default_store_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SonicForge" / "analysis"
    return root / "track_descriptions.json"


def _lyrics_hash(lyrics: str) -> str:
    return hashlib.sha256((lyrics or "").encode("utf-8", errors="replace")).hexdigest()


class DescriptionStore:
    """Persistent per-track description index keyed by path, size and mtime."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_store_path()
        self._lock = threading.RLock()

    def get(self, audio_path: str | Path, lyrics: str | None = None) -> dict[str, Any] | None:
        path = Path(audio_path).resolve()
        try:
            stat = path.stat()
        except OSError:
            return None
        key = self._path_key(path)
        with self._lock:
            record = self._read().get("tracks", {}).get(key)
        if not record:
            return None
        if record.get("size") != stat.st_size or record.get("mtime_ns") != stat.st_mtime_ns:
            return None
        if lyrics is not None and record.get("lyrics_hash") != _lyrics_hash(lyrics):
            return None
        return dict(record)

    def put(self, audio_path: str | Path, bundle: AnalysisBundle, lyrics: str = "") -> dict[str, Any]:
        path = Path(audio_path).resolve()
        stat = path.stat()
        record = {
            "path": str(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "lyrics_hash": _lyrics_hash(lyrics),
            "fingerprint": bundle.analysis.fingerprint,
            "song_description": bundle.song_description,
            "visual_brief": bundle.visual_brief,
            "language": bundle.language,
            "visual_dna": bundle.visual_dna.to_dict(),
            "visual_plan": bundle.visual_plan.to_dict(),
            "analysis": bundle.analysis.to_dict(),
        }
        with self._lock:
            data = self._read()
            data.setdefault("tracks", {})[self._path_key(path)] = record
            self._write(data)
        return dict(record)

    def list_for_source(self, source: str | Path) -> list[dict[str, Any]]:
        source_path = Path(source).resolve()
        with self._lock:
            records = list(self._read().get("tracks", {}).values())
        if source_path.is_file():
            candidates = [record for record in records if self._same_path(record.get("path", ""), source_path)]
        else:
            prefix = os.path.normcase(str(source_path)) + os.sep
            candidates = [record for record in records if os.path.normcase(record.get("path", "")).startswith(prefix)]
        return sorted((dict(record) for record in candidates), key=lambda item: item.get("path", "").lower())

    def export(self, records: list[dict[str, Any]], target: str | Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": STORE_VERSION, "tracks": records}
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return target

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("tracks", {}), dict):
                return value
        except (OSError, ValueError, TypeError):
            pass
        return {"version": STORE_VERSION, "tracks": {}}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _path_key(path: Path) -> str:
        return os.path.normcase(str(path.resolve()))

    @staticmethod
    def _same_path(left: str, right: Path) -> bool:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(str(right.resolve()))
