"""Read-only real vocal check, including an artificial long instrumental intro."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio', type=Path)
    parser.add_argument('--intro-pad', type=float, default=40)
    parser.add_argument('--duration', type=float, help='Check only this many seconds from t=0.')
    parser.add_argument('--output', type=Path, default=ROOT / 'validation/lyrics-overlap/result.json')
    args = parser.parse_args()
    if args.intro_pad < 0:
        parser.error('intro-pad must be nonnegative')
    from lyrics_engine import LyricsService
    from lyrics_engine.formats import render_lrc
    from audio_editor import run_ffmpeg
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.audio.open('rb') as handle:
        original_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
    reports = {}
    service = LyricsService()
    original_source = args.audio
    if args.duration is not None:
        if args.duration <= 0:
            parser.error('duration must be positive')
        original_source = args.output.parent / 'excerpt.wav'
        if original_source.exists():
            raise FileExistsError(original_source)
        run_ffmpeg(['-i', str(args.audio), '-t', str(args.duration), '-c:a', 'pcm_s16le', str(original_source)])
    try:
        for name in (('vocals', 'long_intro') if args.intro_pad else ('vocals',)):
            started = time.monotonic()
            last = ['', 0.0]
            def progress(stage):
                now = time.monotonic()
                if stage != last[0] or now - last[1] > 15:
                    last[:] = [stage, now]
                    print(json.dumps(dict(mode=name, stage=stage, seconds=round(now-started, 2))), flush=True)
            source = original_source
            if name == 'long_intro':
                # Reuse the real separated vocal, adding silence without moving
                # or editing any word. Do not run separation a second time.
                vocal = service._vocal_cache.prepare(original_source)
                source = args.output.parent / 'vocals-long-intro.wav'
                if source.exists():
                    raise FileExistsError(source)
                run_ffmpeg(['-i', str(vocal), '-af', f'adelay={round(args.intro_pad * 1000)}:all=1',
                            '-c:a', 'pcm_s16le', str(source)])
                service.separate_vocals = False
            result = service.recognize(source, language='ru', progress=progress)
            from audio_tags import probe_audio
            duration = probe_audio(source)['duration']
            assert all(0 <= s.start < s.end <= duration + .05 for s in result.segments)
            assert all(a.start <= b.start for a, b in zip(result.segments, result.segments[1:]))
            reports[name] = dict(seconds=round(time.monotonic()-started, 2), duration=duration,
                                 first_start=result.segments[0].start if result.segments else None,
                                 segments=len(result.segments), characters=len(result.text), result=asdict(result))
            if result.segments:
                args.output.with_name(name + '.lrc').write_text(render_lrc(result), encoding='utf-8')
            print(json.dumps({k:v for k,v in reports[name].items() if k != 'result'}), flush=True)
    finally:
        service.close()
    with args.audio.open('rb') as handle:
        assert original_hash == hashlib.file_digest(handle, 'sha256').hexdigest()
    args.output.write_text(json.dumps(dict(source_sha256=original_hash, source_unchanged=True,
        window_seconds=20, overlap_seconds=6, intro_pad=args.intro_pad, reports=reports,
        limitations='Artificial intro validates timeline handling, not recognition accuracy. No independent transcript/WER.'),
        indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
