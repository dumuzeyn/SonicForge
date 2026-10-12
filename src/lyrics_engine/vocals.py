"""One-song temporary vocal cache using the existing isolated HTDemucs worker."""
from pathlib import Path
import tempfile
import threading

from audio_tags import probe_audio
from audio_editor import Cancelled
from stem_separation import separate_clip
from .audio import MAX_SECONDS


class VocalCache:
    def __init__(self):
        self._temporary = None
        self._key = None
        self._path = None
        self._lock = threading.RLock()

    def close(self):
        with self._lock:
            temporary, self._temporary = self._temporary, None
            self._key = self._path = None
            if temporary is not None:
                temporary.cleanup()

    def prepare(self, source, cancel_event=None, progress=None):
        with self._lock:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError('Lyrics recognition was cancelled.')
            source = Path(source).resolve(strict=True)
            stamp = source.stat()
            key = (str(source), stamp.st_size, stamp.st_mtime_ns)
            if key == self._key and self._path and self._path.is_file():
                if progress:
                    progress('vocals_cached')
                return self._path
            self.close()
            duration = probe_audio(source)['duration']
            if not 0 < duration <= MAX_SECONDS:
                raise ValueError('Vocal recognition requires known duration up to 30 minutes.')
            temporary = tempfile.TemporaryDirectory(prefix='sonicforge-lyrics-vocals-')
            try:
                if progress:
                    progress('separating_vocals')
                paths = separate_clip(source, 0, duration, mode='four', cancel=cancel_event,
                                      progress=lambda _: progress('separating_vocals') if progress else None,
                                      cache_root=temporary.name)
                vocals = next(path for path in paths if path.stem == 'vocals')
                # Keep the timeline from t=0; no silence trimming or time shift.
                if abs(probe_audio(vocals)['duration'] - duration) > .05:
                    raise RuntimeError('Vocal timeline does not match the source.')
                for path in paths:
                    if path != vocals:
                        path.unlink()
                self._temporary, self._key, self._path = temporary, key, vocals
                return vocals
            except BaseException as exc:
                temporary.cleanup()
                if isinstance(exc, Cancelled):
                    raise InterruptedError('Lyrics recognition was cancelled.') from exc
                raise
