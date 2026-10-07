"""Persistent, cancellable ASR process. Native decoder faults cannot kill the UI."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .models import LyricsResult, TranscriptSegment
from .memory import MemoryWatch, memory_snapshot, recycle_when_idle

MAX_MESSAGE = 2 * 1024 * 1024
RECYCLE_AFTER = 20


def worker_command():
    command = [sys.executable] if getattr(sys, 'frozen', False) else [
        sys.executable, str(Path(__file__).resolve().parents[1] / 'music_polisher_gui.py')]
    return [*command, '--lyrics-worker', '--parent-pid', str(os.getpid())]


def result_from_json(data):
    data = dict(data)
    data['segments'] = tuple(TranscriptSegment(**segment) for segment in data.get('segments', ()))
    data['mixed_languages'] = tuple(data.get('mixed_languages', ()))
    return LyricsResult(**data)


class IsolatedLyricsProvider:
    name = 'faster-whisper'

    def __init__(self):
        self._process = None
        self._stderr = None
        self._events = None
        self._completed = 0
        self._lock = threading.Lock()
        self._last_error = ''

    def _start(self):
        self.close()
        events = queue.Queue(maxsize=128)
        error_log = tempfile.TemporaryFile(mode='w+b')
        try:
            process = subprocess.Popen(
                worker_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=error_log, text=True, encoding='utf-8', errors='replace', bufsize=1,
                env=dict(os.environ, OMP_NUM_THREADS='8', MKL_NUM_THREADS='8', TOKENIZERS_PARALLELISM='false'),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except Exception:
            error_log.close()
            raise
        self._process, self._stderr, self._events = process, error_log, events
        self._completed = 0
        self._last_error = ''

        def read_messages():
            try:
                while True:
                    line = process.stdout.readline(MAX_MESSAGE + 1)
                    if not line:
                        break
                    if len(line) > MAX_MESSAGE:
                        raise ValueError('Recognition response exceeds the safety limit')
                    message = json.loads(line)
                    while True:
                        try:
                            events.put(message, timeout=.2)
                            break
                        except queue.Full:
                            if process.poll() is not None:
                                return
            except Exception as exc:
                events.put({'event': 'protocol_error', 'error': str(exc)}, timeout=1)
            finally:
                try:
                    events.put({'event': 'exited'}, timeout=1)
                except queue.Full:
                    pass

        threading.Thread(target=read_messages, daemon=True).start()

    def transcribe(self, audio_path, cancel_event=None, progress=None, language=None, on_segment=None):
        with self._lock:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError('Lyrics recognition was cancelled.')
            if self._process is None or self._process.poll() is not None or self._completed >= RECYCLE_AFTER:
                self._start()
            process, events = self._process, self._events
            request_id = uuid.uuid4().hex
            started = last_event = last_memory_check = time.monotonic()
            stage = 'loading_model'
            memory_watch = MemoryWatch()
            latest_memory = None
            try:
                process.stdin.write(json.dumps(dict(id=request_id, path=str(Path(audio_path).resolve()),
                                                   language=language), ensure_ascii=True) + '\n')
                process.stdin.flush()
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise InterruptedError('Lyrics recognition was cancelled.')
                    now = time.monotonic()
                    if now - last_event > (1800 if stage == 'loading_model' else 600) or now - started > 3600:
                        raise RuntimeError('Recognition timed out on this file; the batch can continue.')
                    if now - last_memory_check >= 2:
                        last_memory_check = now
                        latest_memory = memory_snapshot(process)
                        memory_watch.check(latest_memory, now)
                    try:
                        message = events.get(timeout=.1)
                    except queue.Empty:
                        if process.poll() is not None:
                            raise RuntimeError(f'Recognition module exited (code {process.returncode}); other files can continue.')
                        continue
                    kind = message.get('event')
                    if kind == 'ready':
                        continue
                    if kind in ('exited', 'protocol_error'):
                        raise RuntimeError(message.get('error', 'Recognition module stopped unexpectedly; other files can continue.'))
                    if message.get('id') != request_id:
                        raise RuntimeError('Unexpected recognition response')
                    last_event = now
                    if kind == 'progress':
                        stage = message['stage']
                        if progress:
                            progress(stage)
                    elif kind == 'segment':
                        if on_segment:
                            on_segment(TranscriptSegment(**message['segment']))
                    elif kind == 'result':
                        result = result_from_json(message['result'])
                        self._completed += 1
                        if latest_memory is not None and recycle_when_idle(latest_memory):
                            self.close()
                        return result
                    elif kind == 'error':
                        raise RuntimeError(message['error'])
                    else:
                        raise RuntimeError('Invalid recognition response')
            except BaseException as exc:
                self._last_error = f'File: {Path(audio_path).resolve()}\n{type(exc).__name__}: {str(exc)[:2000]}\n'
                if latest_memory is not None:
                    self._last_error += f'Memory snapshot: {latest_memory}\n'
                self.close()
                raise

    def close(self):
        process, error_log = self._process, self._stderr
        self._process = self._stderr = self._events = None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        if error_log is not None:
            error_log.seek(0, os.SEEK_END)
            size = error_log.tell()
            if size or self._last_error:
                error_log.seek(max(0, size - 65536))
                try:
                    root = Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'SonicForge/logs'
                    root.mkdir(parents=True, exist_ok=True)
                    (root / 'lyrics-worker-last.log').write_bytes(
                        self._last_error.encode('utf-8') + error_log.read(65536))
                except OSError:
                    pass
            error_log.close()
        self._last_error = ''
