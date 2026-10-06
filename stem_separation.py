"""Stdlib-only application bridge to the isolated, cancellable separator."""
from pathlib import Path
import json
import math
import os
import subprocess
import sys
import tempfile
import uuid

from audio_editor import Cancelled, run_ffmpeg


def worker_command():
    if getattr(sys, 'frozen', False):
        executable = Path(sys._MEIPASS) / 'separator' / 'SonicForgeSeparator.exe'
        if not executable.is_file():
            raise RuntimeError('Separation module is missing; reinstall Sonic Forge')
        return [str(executable)]
    root = Path(__file__).resolve().parent
    interpreter = root / 'build/stem-python/Scripts/python.exe'
    if not interpreter.is_file():
        raise RuntimeError('Build the separation runtime with build_stems.ps1 first')
    return [str(interpreter), str(root / 'scripts/stem_worker.py'), '--model', str(root / 'build/stem-model')]


def separate_clip(source, start, end, mode='four', cancel=None, progress=None, cache_root=None):
    source = Path(source).resolve(strict=True)
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start or mode not in {'two', 'four'}:
        raise ValueError('Invalid separation range or mode')
    command = worker_command()
    original = source.stat()
    root = Path(cache_root) if cache_root is not None else Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'SonicForge/editor-stems'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.working-', dir=root) as directory:
        working = Path(directory)
        input_path = working / 'input.wav'
        run_ffmpeg(['-ss', f'{start:.6f}', '-t', f'{end - start:.6f}', '-i', str(source), '-vn',
                    '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', str(input_path)], cancel)
        output = working / 'stems'
        progress_path = working / 'progress.jsonl'
        with (working / 'worker.log').open('w+b') as log:
            environment = dict(os.environ, OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
            process = subprocess.Popen([*command, '--input', str(input_path), '--output', str(output),
                                        '--progress', str(progress_path), '--parent-pid', str(os.getpid())], stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, env=environment,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            delivered = 0
            try:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    if progress and progress_path.exists():
                        lines = progress_path.read_text(encoding='utf-8').splitlines()
                        for line in lines[delivered:]:
                            try:
                                progress(float(json.loads(line)['progress']))
                            except (ValueError, KeyError):
                                continue
                        delivered = len(lines)
                    try:
                        code = process.wait(timeout=.1)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                if code:
                    log.seek(0)
                    raise RuntimeError(log.read()[-4000:].decode('utf-8', 'replace'))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
        names = ('vocals', 'drums', 'bass', 'other')
        if any(not (output / (name + '.wav')).is_file() for name in names):
            raise RuntimeError('Separator did not return all components')
        if mode == 'two':
            run_ffmpeg(['-i', str(output / 'drums.wav'), '-i', str(output / 'bass.wav'), '-i', str(output / 'other.wav'),
                        '-filter_complex', '[0:a][1:a][2:a]amix=inputs=3:normalize=0[out]', '-map', '[out]',
                        '-c:a', 'pcm_f32le', str(output / 'instrumental.wav')], cancel)
            names = ('vocals', 'instrumental')
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        current = source.stat()
        if (current.st_size, current.st_mtime_ns) != (original.st_size, original.st_mtime_ns):
            raise ValueError('Source changed during separation')
        target = root / uuid.uuid4().hex
        output.rename(target)
        if progress:
            progress(1.0)
        return tuple(target / (name + '.wav') for name in names)
