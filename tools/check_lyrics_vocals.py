"""Read-only A/B check on real music, with optional independent reference.

No reference or lyrics are passed as decoder prompts. Reports are local only.
"""
import argparse
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
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--duration', type=float, default=45)
    parser.add_argument('--language', default='ru')
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'validation/lyrics-vocals/result.json')
    args = parser.parse_args()
    from audio_editor import run_ffmpeg
    from lyrics_engine import LyricsService
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.audio.open('rb') as handle:
        before = hashlib.file_digest(handle, 'sha256').hexdigest()
    clip = args.output.parent / 'source_excerpt.wav'
    if clip.exists():
        raise FileExistsError(clip)
    run_ffmpeg(['-ss', str(args.start), '-t', str(args.duration), '-i', str(args.audio),
                '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', str(clip)])
    service = LyricsService(separate_vocals=False)
    reports = {}
    try:
        for separated in (False, True):
            name = 'vocals' if separated else 'mix'
            service.separate_vocals = separated
            start = time.monotonic()
            last = ['', 0.0]
            def progress(stage):
                now = time.monotonic()
                if stage != last[0] or now - last[1] > 15:
                    last[:] = [stage, now]
                    print(json.dumps({'mode': name, 'stage': stage, 'seconds': round(now-start, 2)}), flush=True)
            result = service.recognize(clip, language=args.language, progress=progress)
            from dataclasses import asdict
            confidence = [s.confidence for s in result.segments if s.confidence is not None]
            report = {'seconds': time.monotonic()-start, 'characters': len(result.text),
                      'segments': len(result.segments), 'mean_model_confidence': sum(confidence)/len(confidence) if confidence else None,
                      'review_reason': result.review_reason, 'result': asdict(result)}
            if args.reference:
                sys.path.insert(0, str(ROOT / 'scripts'))
                from benchmark_lyrics_words import word_error_rate
                report['wer'] = word_error_rate(args.reference.read_text(encoding='utf-8-sig'), result.text)
            reports[name] = report
            print(json.dumps({k:v for k,v in report.items() if k!='result'}), flush=True)
    finally:
        service.close()
    with args.audio.open('rb') as handle:
        unchanged = hashlib.file_digest(handle, 'sha256').hexdigest() == before
    assert unchanged, 'Original audio was modified'
    args.output.write_text(json.dumps({'source_sha256': before, 'source_unchanged': unchanged,
        'start': args.start, 'duration': args.duration, 'reports': reports,
        'limitations': 'Model confidence is not accuracy. Without an independent reference, WER is not measured. First mix run includes cold ASR load; vocals run reuses the same ASR worker.'},
        indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
