"""Private JSON-lines worker; only our code is launched, never selected media."""
import argparse
from dataclasses import asdict
import faulthandler
import gc
import io
import json
import os
import re
import sys
import threading
import time


def _standard_stream(name, identifier, flags):
    stream = getattr(sys, name)
    if stream is not None:
        return stream
    # Windowed PyInstaller sets sys.std* to None, even for redirected pipes.
    import ctypes
    import msvcrt
    kernel = ctypes.windll.kernel32
    kernel.GetStdHandle.restype = ctypes.c_void_p
    handle = kernel.GetStdHandle(identifier)
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise RuntimeError('Recognition worker has no redirected standard stream')
    descriptor = msvcrt.open_osfhandle(handle, flags | os.O_BINARY)
    return io.TextIOWrapper(os.fdopen(descriptor, 'rb' if name == 'stdin' else 'wb'), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args(sys.argv[2:])
    sys.stdin = _standard_stream('stdin', -10, os.O_RDONLY)
    protocol = _standard_stream('stdout', -11, os.O_WRONLY)
    sys.stderr = _standard_stream('stderr', -12, os.O_WRONLY)
    sys.stdout = sys.stderr  # Third-party diagnostic prints cannot corrupt JSON.
    faulthandler.enable(file=sys.stderr)

    def watch_parent():
        import psutil
        while psutil.pid_exists(args.parent_pid):
            time.sleep(2)
        os._exit(0)

    threading.Thread(target=watch_parent, daemon=True).start()

    def send(event, **details):
        protocol.write(json.dumps(dict(event=event, **details), ensure_ascii=True) + '\n')
        protocol.flush()

    from security import validate_audio_file
    from .providers import FasterWhisperProvider
    provider = FasterWhisperProvider()
    send('ready')
    while True:
        line = sys.stdin.readline(65537)
        if not line:
            break
        if len(line) > 65536:
            break
        request_id = ''
        try:
            request = json.loads(line)
            request_id = request['id']
            language = request.get('language')
            if language is not None and not re.fullmatch(r'[a-z_]{2,12}', language):
                raise ValueError('Invalid recognition language')
            path = validate_audio_file(request['path'])
            last_progress = ['', 0.0]
            def progress(stage):
                now = time.monotonic()
                if stage != last_progress[0] or now - last_progress[1] >= .5:
                    last_progress[:] = [stage, now]
                    send('progress', id=request_id, stage=stage)
            result = provider.transcribe(path, language=language, progress=progress,
                on_segment=lambda segment: send('segment', id=request_id, segment=asdict(segment)))
            send('result', id=request_id, result=asdict(result))
        except Exception as exc:
            send('error', id=request_id, error=f'{type(exc).__name__}: {str(exc)[:1000]}')
        finally:
            gc.collect()
