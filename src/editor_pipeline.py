"""Session-local rendered editor input shared by previews and final processing."""
from dataclasses import asdict
from pathlib import Path
import tempfile
import uuid

from audio_editor import Cancelled, render, run_ffmpeg


def project_signature(project, extension):
    if extension not in {'.mp3', '.wav', '.m4a'}:
        raise ValueError('Unsupported editor output format')
    # Stat every used source, even on a cache hit: never reuse a changed input.
    sources = []
    for path in sorted({clip.source for clip in project.clips}):
        source = project.sources[path]
        stamp = Path(path).stat()
        actual = (stamp.st_size, stamp.st_mtime_ns)
        if source.stamp and actual != source.stamp:
            raise ValueError('Source audio changed; reopen it in the editor')
        sources.append((path, actual))
    return repr((extension, [asdict(clip) for clip in project.clips],
                 sorted(project.muted), sources))


class EditorPipelineSource:
    def __init__(self):
        self._temporary = None
        self.signature = None
        self.path = None

    def current(self, project, extension):
        signature = project_signature(project, extension)
        return self.path if signature == self.signature and self.path and self.path.is_file() else None

    def prepare(self, project, extension, cancel=None):
        signature = project_signature(project, extension)
        if signature == self.signature and self.path and self.path.is_file():
            return self.path
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        audible = [clip for clip in project.clips if clip.lane not in project.muted]
        if not audible:
            raise ValueError('No audible clips')
        if self._temporary is None:
            self._temporary = tempfile.TemporaryDirectory(prefix='sonicforge-editor-pipeline-')
        folder = Path(self._temporary.name) / uuid.uuid4().hex
        folder.mkdir()
        first = Path(audible[0].source)
        target = folder / (first.stem + extension)
        mixed = folder / ('mix' + extension)
        try:
            render(project, mixed, cancel)
            # Copy the first audible source's tags/artwork onto the new mix.
            # No original is opened for writing; MP3/M4A audio is stream-copied.
            maps = ['-map', '1:a', '-map_metadata', '0']
            if extension != '.wav':
                maps += ['-map', '0:v?', '-disposition:v', 'attached_pic']
            run_ffmpeg(['-i', str(first), '-i', str(mixed), *maps, '-c', 'copy',
                        '-metadata', 'lyrics=', '-metadata', 'syncedlyrics=', str(target)], cancel)
            if extension == '.mp3':
                from audio_tags import update_id3
                update_id3(target, (), remove_names=('USLT', 'SYLT'),
                           remove_custom=('SONICFORGE_LYRICS_LANGUAGE', 'SONICFORGE_LYRICS_ALPHABET'))
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            # Old paths remain valid until shutdown; workers never lose their input.
            self.signature, self.path = signature, target
            return target
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            mixed.unlink(missing_ok=True)

    def close(self):
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
        self.path = self.signature = None
