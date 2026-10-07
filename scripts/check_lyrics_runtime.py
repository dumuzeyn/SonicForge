"""Read-only end-to-end recognition check; never embeds lyrics in the source."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import tempfile
import wave
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lyrics_engine import LyricsService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio', type=Path)
    parser.add_argument('--language', default='auto')
    parser.add_argument('--worker-exe', type=Path)
    parser.add_argument('--stress', type=int, default=0, help='Follow with this many distinct synthetic silent WAVs')
    args = parser.parse_args()
    if args.worker_exe:
        import lyrics_engine.isolated
        lyrics_engine.isolated.worker_command = lambda: [str(args.worker_exe.resolve()), '--lyrics-worker',
                                                         '--parent-pid', str(os.getpid())]
    with args.audio.open('rb') as stream:
        before = hashlib.file_digest(stream, 'sha256').hexdigest()
    service = LyricsService()
    started = time.monotonic()
    memory = dict(peak_worker_mb=0, peak_private_mb=0,
                  minimum_available_mb=psutil.virtual_memory().available // 1024 ** 2)
    def progress(stage):
        memory['minimum_available_mb'] = min(memory['minimum_available_mb'],
                                              psutil.virtual_memory().available // 1024 ** 2)
        worker = getattr(service.provider, '_process', None)
        if worker is not None:
            try:
                usage = psutil.Process(worker.pid).memory_info()
                memory['peak_worker_mb'] = max(memory['peak_worker_mb'],
                    getattr(usage, 'peak_wset', usage.rss) // 1024 ** 2)
                memory['peak_private_mb'] = max(memory['peak_private_mb'],
                    getattr(usage, 'peak_pagefile', getattr(usage, 'private', usage.rss)) // 1024 ** 2)
            except psutil.NoSuchProcess:
                pass
        print(json.dumps(dict(stage=stage, seconds=round(time.monotonic() - started, 2))), flush=True)
    try:
        result = service.recognize(args.audio, language=args.language, progress=progress)
        details = [dict(start=s.start, end=s.end, characters=len(s.text),
                        letters=sum(c.isalpha() for c in s.text), confidence=s.confidence,
                        word_repetitions=sorted(Counter(s.text.casefold().split()).values(), reverse=True)[:4])
                   for s in result.segments if len(s.text) > 300 or (s.confidence or 0) < .35]
        print(json.dumps(dict(seconds=round(time.monotonic() - started, 2), lines=len(result.segments),
                              characters=len(result.text), language=result.language,
                              quality=result.quality, instrumental=result.instrumental,
                              usable=service.is_usable(result), review_reason=result.review_reason,
                              questionable_segments=details, memory=memory)), flush=True)
        if args.stress:
            with tempfile.TemporaryDirectory(prefix='sonicforge-lyrics-stress-') as directory:
                for index in range(args.stress):
                    path = Path(directory) / f'silent-{index:03d}.wav'
                    with wave.open(str(path), 'wb') as audio:
                        audio.setnchannels(1)
                        audio.setsampwidth(2)
                        audio.setframerate(16000)
                        audio.writeframes(b'\0\0' * 8000)
                    silent = service.recognize(path)
                    assert not silent.text and silent.instrumental
                print(json.dumps(dict(synthetic_files=args.stress, completed=args.stress)), flush=True)
    finally:
        service.close()
    with args.audio.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == before, 'Source changed'


if __name__ == '__main__':
    main()
