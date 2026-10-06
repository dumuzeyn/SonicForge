"""Read-only real-audio smoke check of a packaged separation worker."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_editor import read_waveform
from music_polisher_gui import configure_bundled_ffmpeg
from stem_separation import separate_clip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--start', type=float, default=12)
    parser.add_argument('--length', type=float, default=8)
    args = parser.parse_args()
    configure_bundled_ffmpeg()
    source = args.source.resolve(strict=True)
    worker = args.worker.resolve(strict=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='sonicforge-stem-check-') as directory:
        with patch('stem_separation.worker_command', return_value=[str(worker)]):
            paths = separate_clip(source, args.start, args.start + args.length,
                                  cache_root=Path(directory))
        outputs = []
        for path in paths:
            audio = read_waveform(path)
            assert abs(audio.duration - args.length) < .02, audio.duration
            assert all(0 <= peak <= 1 for peak in audio.peaks)
            outputs.append({'component': path.stem, 'seconds': audio.duration,
                            'peak': max(audio.peaks, default=0)})
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before, 'Source changed'
    print(json.dumps({'elapsed_seconds': round(time.perf_counter() - started, 3),
                      'source_unchanged': True, 'components': outputs}, indent=2))


if __name__ == '__main__':
    main()
