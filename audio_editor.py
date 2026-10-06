"""Non-destructive timeline and windowless, cancellable FFmpeg rendering.

No GUI, recognizer or analysis libraries are imported here. Source audio is read
only; publishing a render uses an exclusive target so even a race cannot replace
another file.
"""
from dataclasses import asdict, dataclass, replace
from pathlib import Path
import errno
import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
import wave
from array import array


class Cancelled(Exception):
    pass


def run_ffmpeg(args, cancel=None):
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg not found")
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [executable, "-hide_banner", "-nostdin", "-loglevel", "error", *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                try:
                    code = process.wait(timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if code:
                errors.seek(0)
                raise RuntimeError(errors.read()[-4000:].decode("utf-8", "replace"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


@dataclass(frozen=True)
class AudioSource:
    path: str
    duration: float
    peaks: tuple = ()
    stamp: tuple = ()


def read_waveform(path, cancel=None):
    """Decode in the worker, then retain at most 2400 peak bins per source."""
    path = Path(path).resolve(strict=True)
    initial_stat = path.stat()
    with tempfile.TemporaryDirectory(prefix="sonicforge-wave-") as directory:
        decoded = Path(directory) / "wave.wav"
        run_ffmpeg(["-i", str(path), "-vn", "-t", "14400", "-ac", "1", "-ar", "8000",
                    "-c:a", "pcm_s16le", str(decoded)], cancel)
        with wave.open(str(decoded)) as audio:
            frames = audio.getnframes()
            duration = frames / audio.getframerate()
            if duration <= 0 or duration >= 14400:
                raise ValueError("Audio must be shorter than four hours and contain sound")
            step = max(1, math.ceil(frames / 2400))
            peaks = []
            while data := audio.readframes(step):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                values = array("h", data)
                if os.sys.byteorder != "little":
                    values.byteswap()
                peaks.append(max(abs(value) for value in values) / 32768)
    stat = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (initial_stat.st_size, initial_stat.st_mtime_ns):
        raise ValueError("Source audio changed during import; reopen it")
    return AudioSource(str(path), duration, tuple(peaks), (stat.st_size, stat.st_mtime_ns))


@dataclass(frozen=True)
class Clip:
    id: str
    source: str
    lane: int
    start: float
    end: float
    position: float = 0
    gain: float = 0
    fade_in: float = 0
    fade_out: float = 0

    @property
    def duration(self):
        return self.end - self.start


class Timeline:
    def __init__(self):
        self.sources = {}
        self.clips = []
        self.muted = set()
        self._undo = []
        self._redo = []

    @property
    def duration(self):
        return max((clip.position + clip.duration for clip in self.clips), default=0)

    def _snapshot(self):
        return (list(self.clips), set(self.muted))

    def _remember(self):
        self._undo.append(self._snapshot())
        self._undo = self._undo[-100:]
        self._redo.clear()

    def undo(self):
        if self._undo:
            self._redo.append(self._snapshot())
            self.clips, self.muted = self._undo.pop()

    def redo(self):
        if self._redo:
            self._undo.append(self._snapshot())
            self.clips, self.muted = self._redo.pop()

    def get(self, identifier):
        return next(clip for clip in self.clips if clip.id == identifier)

    def _validate(self, clip, check_overlap=True):
        source = self.sources[clip.source]
        values = (clip.start, clip.end, clip.position, clip.gain, clip.fade_in, clip.fade_out)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Values must be finite")
        if not isinstance(clip.lane, int) or isinstance(clip.lane, bool) or clip.lane < 0:
            raise ValueError("Lane must be a non-negative integer")
        if not 0 <= clip.start < clip.end <= source.duration + .001 or clip.duration < .01:
            raise ValueError("Invalid source range")
        if clip.position < 0 or clip.position + clip.duration > 14400:
            raise ValueError("Invalid timeline position")
        if not -60 <= clip.gain <= 18:
            raise ValueError("Gain must be between -60 and +18 dB")
        if min(clip.fade_in, clip.fade_out) < 0 or max(clip.fade_in, clip.fade_out) > clip.duration:
            raise ValueError("Fades must fit within the clip")
        if check_overlap and any(c.id != clip.id and c.lane == clip.lane
                                 and clip.position < c.position + c.duration - 1e-9
                                 and c.position < clip.position + clip.duration - 1e-9 for c in self.clips):
            raise ValueError("Clips on the same lane cannot overlap")

    def free_position(self, lane, position, duration, exclude=None):
        """Find the first available interval at or after the requested position."""
        for other in sorted((c for c in self.clips if c.lane == lane and c.id != exclude), key=lambda c: c.position):
            if position + duration <= other.position + 1e-9:
                break
            if position < other.position + other.duration - 1e-9:
                position = other.position + other.duration
        return position

    def add(self, source, lane=0, position=None):
        self.sources[source.path] = source
        if position is None:
            position = max((c.position + c.duration for c in self.clips if c.lane == lane), default=0)
        clip = Clip(uuid.uuid4().hex, source.path, lane, 0, source.duration, position)
        self._validate(clip, check_overlap=False)
        clip = replace(clip, position=self.free_position(lane, position, clip.duration))
        self._validate(clip)
        self._remember()
        self.clips.append(clip)
        return clip

    def update(self, identifier, **changes):
        clip = replace(self.get(identifier), **changes)
        self._validate(clip, check_overlap=False)
        if 'position' in changes or 'lane' in changes:
            clip = replace(clip, position=self.free_position(clip.lane, clip.position, clip.duration, exclude=identifier))
        self._validate(clip)
        self._remember()
        self.clips = [clip if c.id == identifier else c for c in self.clips]
        return clip

    def split(self, identifier, at):
        clip = self.get(identifier)
        offset = at - clip.position
        if not .01 <= offset <= clip.duration - .01:
            raise ValueError("Place the cursor inside the selected clip")
        left = replace(clip, end=clip.start + offset, fade_in=min(clip.fade_in, offset), fade_out=0)
        right = replace(clip, id=uuid.uuid4().hex, start=clip.start + offset,
                        position=at, fade_in=0, fade_out=min(clip.fade_out, clip.duration - offset))
        self._remember()
        index = self.clips.index(clip)
        self.clips[index:index + 1] = [left, right]
        return right

    def duplicate(self, identifier):
        clip = self.get(identifier)
        duplicate = replace(clip, id=uuid.uuid4().hex, position=clip.position + clip.duration)
        duplicate = replace(duplicate, position=self.free_position(duplicate.lane, duplicate.position, duplicate.duration))
        self._validate(duplicate)
        self._remember()
        self.clips.append(duplicate)
        return duplicate

    def delete(self, identifier):
        self.get(identifier)
        self._remember()
        self.clips = [c for c in self.clips if c.id != identifier]

    def replace_audio(self, identifier, source):
        """Replace one clip with an edited copy, keeping placement and one undo."""
        original = self.get(identifier)
        self.sources[source.path] = source
        clip = replace(original, source=source.path, start=0, end=source.duration,
                       fade_in=min(original.fade_in, source.duration),
                       fade_out=min(original.fade_out, source.duration))
        self._validate(clip)
        self._remember()
        self.clips = [clip if c.id == identifier else c for c in self.clips]
        return clip

    def toggle_mute(self, lane):
        self._remember()
        self.muted.symmetric_difference_update({lane})

    def save(self, path):
        data = dict(version=1, clips=[asdict(c) for c in self.clips], muted=sorted(self.muted))
        path = Path(path)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, path, cancel=None):
        path = Path(path)
        if path.stat().st_size > 2_000_000:
            raise ValueError("Draft is too large")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported draft")
        project = cls()
        for values in data["clips"]:
            clip = Clip(**values)
            if clip.source not in project.sources:
                project.sources[clip.source] = read_waveform(clip.source, cancel)
            project._validate(clip)
            if any(c.id == clip.id for c in project.clips):
                raise ValueError("Duplicate clip id")
            project.clips.append(clip)
        project.muted = {int(lane) for lane in data.get("muted", [])}
        return project


def remove_audio_selection(source, clip, selection_start, selection_end, cancel=None, cache_root=None):
    """Remove a range and close the gap with a bounded 40 ms crossfade.

    Write a persistent lossless edit copy for draft/undo references. The original
    file, clip and project remain untouched until the UI commits the result.
    """
    values = (clip.start, clip.end, clip.position, selection_start, selection_end)
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Selection must be finite')
    if not 0 <= clip.start < clip.end <= source.duration + .001:
        raise ValueError('Invalid source range')
    a = max(0, selection_start - clip.position)
    b = min(clip.duration, selection_end - clip.position)
    if b - a < .01:
        raise ValueError('Select at least 10 ms inside the clip')
    left, right = a, clip.duration - b
    if left + right < .01:
        raise ValueError('The entire clip is selected; remove it from the timeline')
    path = Path(source.path).resolve(strict=True)
    initial = path.stat()
    stamp = (initial.st_size, initial.st_mtime_ns)
    if source.stamp and source.stamp != stamp:
        raise ValueError('Source audio changed; reopen it in the editor')
    root = Path(cache_root) if cache_root is not None else Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'SonicForge/editor-edits'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.working-', dir=root) as directory:
        working = Path(directory)
        result_dir = working / 'result'
        result_dir.mkdir()
        output = result_dir / (path.stem + '.wav')
        inputs = []
        filters = []
        for offset, duration in ((0, left), (b, right)):
            if duration <= 1e-9:
                continue
            index = len(filters)
            inputs.extend(['-ss', f'{clip.start + offset:.9f}', '-t', f'{duration:.9f}', '-i', str(path)])
            filters.append(f'[{index}:a]asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[p{index}]')
        if len(filters) == 2:
            fade = min(.04, left / 2, right / 2, max(0, left + right - .01))
            if fade <= 1 / 44100:
                raise ValueError('Keep at least 10 ms of audio outside the selection')
            filters.append(f'[p0][p1]acrossfade=d={fade:.9f}:c1=tri:c2=tri[out]')
        else:
            filters.append('[p0]anull[out]')
        run_ffmpeg([*inputs, '-filter_complex', ';'.join(filters), '-map', '[out]', '-vn',
                    '-c:a', 'pcm_f32le', str(output)], cancel)
        audio = read_waveform(output, cancel)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        current = path.stat()
        if stamp != (current.st_size, current.st_mtime_ns):
            raise ValueError('Source audio changed during editing')
        target = root / uuid.uuid4().hex
        result_dir.rename(target)
        return replace(audio, path=str(target / output.name))


def render(project, target, cancel=None, start=0, length=None):
    target = Path(target).resolve()
    sources = {Path(c.source).resolve() for c in project.clips}
    if target in sources or target.exists():
        raise ValueError("Choose a new output filename; originals cannot be overwritten")
    formats = {".wav": ["-c:a", "pcm_s16le"], ".mp3": ["-c:a", "libmp3lame", "-q:a", "0"],
               ".m4a": ["-c:a", "aac", "-b:a", "256k"]}
    if target.suffix.lower() not in formats:
        raise ValueError("Use WAV, MP3 or M4A")
    end = project.duration if length is None else min(project.duration, start + length)
    if not math.isfinite(start) or start < 0 or end <= start:
        raise ValueError("Nothing to render")
    clips = [c for c in project.clips if c.lane not in project.muted
             and c.position < end and c.position + c.duration > start]
    if not clips:
        raise ValueError("No audible clips")
    inputs, filters, labels = [], [], []
    # Each input is seeked to the relevant range: preview never decodes a whole song.
    for index, clip in enumerate(clips):
        project._validate(clip)
        source = project.sources[clip.source]
        if source.stamp:
            stat = Path(clip.source).stat()
            if source.stamp != (stat.st_size, stat.st_mtime_ns):
                raise ValueError("Source audio changed; reopen it in the editor")
        offset = max(0, start - clip.position)
        duration = min(clip.duration - offset, end - max(start, clip.position))
        inputs.extend(["-ss", f"{clip.start + offset:.6f}", "-t", f"{duration:.6f}", "-i", clip.source])
        chain = ["asetpts=PTS-STARTPTS", "aresample=44100", "aformat=channel_layouts=stereo",
                 f"volume={clip.gain:.4f}dB"]
        # Evaluate envelopes at the original clip offset, including partial previews.
        if clip.fade_in or clip.fade_out:
            envelope = "1"
            if clip.fade_in:
                envelope += f"*min(1,(t+{offset:.6f})/{clip.fade_in:.6f})"
            if clip.fade_out:
                envelope += f"*min(1,max(0,({clip.duration:.6f}-t-{offset:.6f})/{clip.fade_out:.6f}))"
            chain.append(f"volume='{envelope}':eval=frame")
        delay = max(0, clip.position - start) * 1000
        chain.append(f"adelay={round(delay)}:all=1")
        filters.append(f"[{index}:a]" + ",".join(chain) + f"[c{index}]")
        labels.append(f"[c{index}]")
    filters.append("".join(labels) + f"amix=inputs={len(clips)}:normalize=0:duration=longest,"
                   f"apad,atrim=duration={end - start:.6f},alimiter=limit=0.95:level=0:latency=1[out]")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(".sonicforge-" + uuid.uuid4().hex + target.suffix)
    try:
        run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-vn",
                    *formats[target.suffix.lower()], str(temporary)], cancel)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        # Hard-link publication is atomic and fails if somebody created the target.
        try:
            os.link(temporary, target)
        except OSError as exc:
            if exc.errno not in {errno.EPERM, errno.EACCES, errno.ENOTSUP, errno.EXDEV, errno.EINVAL}:
                raise
            # exFAT and some network volumes cannot create hard links. Exclusive
            # creation still guarantees that an existing file is never replaced.
            created = False
            try:
                with target.open("xb") as output, temporary.open("rb") as source:
                    created = True
                    while chunk := source.read(1024 * 1024):
                        if cancel is not None and cancel.is_set():
                            raise Cancelled()
                        output.write(chunk)
            except BaseException:
                if created:
                    target.unlink(missing_ok=True)
                raise
    finally:
        temporary.unlink(missing_ok=True)
    return target
