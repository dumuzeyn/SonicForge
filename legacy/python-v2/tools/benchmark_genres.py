"""Reproducible old/new comparison; read-only audio, isolated worker processes.

Use an independently labeled manifest. Reference genres must match the selected
model vocabulary. Absence of a tag in MTT is a noisy negative, not expert truth.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def validate(manifest):
    groups = {}
    for row in manifest['tracks']:
        if not row.get('artist') or not row.get('track_id') or row['split'] not in ('train', 'validation', 'test'):
            raise ValueError('Each row needs artist, track_id and a valid split.')
        path = ROOT / row['path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row['sha256']:
            raise ValueError(f'Audio checksum mismatch: {path}')
        for key in (('artist', row['artist'].strip().casefold()), ('track', row['track_id']), ('sha256', digest)):
            if key in groups and groups[key] != row['split']:
                raise ValueError(f'Leakage across splits: {key}')
            groups[key] = row['split']


def metrics(rows, labels):
    table = {}
    for label in labels:
        tp = sum(label in r['gold'] and label in r['predicted'] for r in rows)
        fp = sum(label not in r['gold'] and label in r['predicted'] for r in rows)
        fn = sum(label in r['gold'] and label not in r['predicted'] for r in rows)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        table[label] = {'precision': precision, 'recall': recall,
                        'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
                        'accuracy': 1 - (fp + fn) / len(rows), 'support': tp + fn,
                        'tp': tp, 'fp': fp, 'fn': fn}
    times = sorted(r['seconds'] for r in rows)
    return {'macro_f1': sum(r['f1'] for r in table.values()) / len(table),
            'per_genre': table, 'tracks': len(rows),
            'top1_hit_rate': sum(bool(r['predicted']) and r['predicted'][0] in r['gold'] for r in rows) / len(rows),
            'exact_match': sum(set(r['predicted']) == set(r['gold']) for r in rows) / len(rows),
            'abstentions': sum(not r['predicted'] for r in rows),
            'mean_seconds': sum(times) / len(times), 'p95_seconds': times[min(len(times)-1, int(len(times)*.95))]}


def worker(args, manifest):
    rows = []
    if args.worker == 'new':
        from genre_classifier import classify_genre
        from music_metadata import DEFAULT_GENRES
    else:
        from legacy_genre_baseline import estimate_genre, DEFAULT_GENRES
    allowed = DEFAULT_GENRES if args.defaults else manifest['genres']
    for track in manifest['tracks']:
        if track['split'] != args.split:
            continue
        started = time.perf_counter()
        path = ROOT / track['path']
        if args.worker == 'new':
            result = classify_genre(path, allowed)
            if result.reason.startswith('unavailable:'):
                raise RuntimeError(result.reason)
            predicted, details = list(result.genres), result.to_dict()
        else:
            predicted, details = [estimate_genre(path, allowed)], {}
        rows.append({'clip_id': track.get('clip_id'), 'artist': track['artist'],
                     'gold': track['genres'], 'predicted': predicted,
                     'seconds': time.perf_counter()-started, 'details': details})
    if not rows:
        raise ValueError('No tracks in requested split')
    args.output.write_text(json.dumps({'metrics': metrics(rows, manifest['genres']), 'rows': rows},
                                     indent=2, ensure_ascii=False), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT / 'docs/genre_evaluation_manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/genre_evaluation_results.json')
    parser.add_argument('--split', choices=['validation', 'test'], default='test')
    parser.add_argument('--worker', choices=['old', 'new'])
    parser.add_argument('--defaults', action='store_true', help='Also compare production default genre lists')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    validate(manifest)
    if args.worker:
        worker(args, manifest)
        return
    import psutil
    reports = {}
    work = ROOT / '.sonicforge/genre-eval'
    work.mkdir(parents=True, exist_ok=True)
    for algorithm in ('old', 'new'):
        output = work / f'{algorithm}_{args.split}.json'
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', algorithm,
                   '--manifest', str(args.manifest), '--output', str(output), '--split', args.split]
        if args.defaults:
            command.append('--defaults')
        proc = subprocess.Popen(command)
        finished = threading.Event()
        peak = [0]
        def sample():
            while not finished.is_set():
                try:
                    process = psutil.Process(proc.pid)
                    total = process.memory_info().rss
                    for child in process.children(recursive=True):
                        try:
                            total += child.memory_info().rss
                        except psutil.Error:
                            pass
                    peak[0] = max(peak[0], total)
                except psutil.Error:
                    pass
                finished.wait(.01)
        sampler = threading.Thread(target=sample)
        sampler.start()
        code = proc.wait()
        finished.set()
        sampler.join()
        if code:
            raise RuntimeError(f'{algorithm} evaluation failed: {code}')
        reports[algorithm] = json.loads(output.read_text(encoding='utf-8'))
        reports[algorithm]['peak_rss_mib_including_decoders'] = peak[0] / 1024 ** 2
        print(algorithm, reports[algorithm]['metrics'], 'RSS MiB', peak[0]/1024**2, flush=True)
    model = json.loads((ROOT / 'assets/models/genre/manifest.json').read_text())
    args.output.write_text(json.dumps({'platform': platform.platform(), 'cpu': platform.processor(),
        'python': sys.version, 'split': args.split, 'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        'model_sha256': model['sha256'], 'score_threshold': .20,
        'baseline_revision': 'b79348d9811ccd6974a2c9befca527be3dc9744e',
        'allowed_genres': 'Production default lists' if args.defaults else manifest['genres'],
        'protocol': 'Opaque clip filenames. Scores frozen before test. No training or threshold tuning. Macro-F1 is computed on the eight reference labels; additional predictions affect exact-match/top1. RSS sampled every 10 ms including child decoders; cold model load included in first new track.',
        'limitations': manifest.get('limitations', ''), 'reports': reports}, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
