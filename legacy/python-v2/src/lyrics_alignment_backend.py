"""Forced alignment in the isolated CPU helper; supplied words are immutable."""
import json
import math
import os
import sys
from types import SimpleNamespace


def local_ranges(original, lines, duration, padding=4):
    hints = original.get('segments', ())
    if len(hints) != len(lines) or not hints or any(float(s['start']) < 0 for s in hints):
        return None
    starts = [float(s['start']) for s in hints]
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= duration:
        return None
    groups = {}
    for index, line in enumerate(lines):
        groups.setdefault(' '.join(line.casefold().split()), []).append(index)
    ranges = []
    for index, (hint, line) in enumerate(zip(hints, lines)):
        start = starts[index]
        end = float(hint['end'])
        if end <= start:
            end = starts[index + 1] if index + 1 < len(starts) else min(duration, start + 12)
        left, right = max(0, start - padding), min(duration, max(start + .5, end) + padding, start + 26)
        repeats = groups[' '.join(line.casefold().split())]
        place = repeats.index(index)
        if place:
            left = max(left, (starts[repeats[place - 1]] + start) / 2)
        if place + 1 < len(repeats):
            right = min(right, (start + starts[repeats[place + 1]]) / 2)
        if right - left < .05:
            return None
        ranges.append(dict(start=left, end=right, text=line))
    return ranges


def align_existing(model, audio_path, original, language, progress=None, aligner=None, local_aligner=None):
    if aligner is None:
        from stable_whisper.alignment import align as aligner
    from faster_whisper.audio import decode_audio
    text = original['text']
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or len(text) > 131072:
        raise ValueError('Alignment requires existing lyrics, up to 128 KiB.')
    audio = decode_audio(str(audio_path))
    duration = len(audio) / 16000
    if not 0 < duration <= 1800 or not audio.any():
        raise ValueError('Timing correction requires audible audio up to 30 minutes.')
    ranges = local_ranges(original, lines, duration)
    if original.get('segments') and ranges is None:
        raise ValueError('Original time anchors are inconsistent; review them before correcting repeats.')
    common = dict(language=language, regroup=False, verbose=None, vad=False,
                  progress_callback=lambda *_: progress('aligning') if progress else None)
    if ranges is not None:
        if local_aligner is None:
            from stable_whisper.alignment import align_words as local_aligner
        # Search windows may overlap; they are independent alternatives rather
        # than an already ordered transcript. Align each supplied line alone.
        aligned_segments = []
        for window in ranges:
            try:
                part = local_aligner(model, audio, [window], normalize_text=False, inplace=False, **common)
                aligned_segments.append(part.segments[0] if part is not None and len(part.segments) == 1 else None)
            except Exception:
                aligned_segments.append(None)
        aligned = SimpleNamespace(segments=aligned_segments)
    else:
        aligned = aligner(model, audio, '\n'.join(lines), original_split=True,
                         remove_instant_words=False, failure_threshold=.25, token_step=100, **common)
    if aligned is None or len(aligned.segments) != len(lines):
        raise ValueError('Could not align every lyric line; original text and times were retained.')
    segments, preserved = [], set()
    for index, (line, segment) in enumerate(zip(lines, aligned.segments)):
        start, end = (float(segment.start), float(segment.end)) if segment is not None else (float('nan'), 0.)
        words = segment.words if segment is not None else ()
        probabilities = [float(word.probability) for word in words if word.probability is not None]
        confidence = sum(probabilities) / len(probabilities) if probabilities else None
        uncertain = (not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start or end > duration + .05
                     or confidence is not None and confidence < .12
                     or not words or any(word.end <= word.start for word in words))
        uncertain |= ranges is not None and not ranges[index]['start'] - .02 <= start < end <= ranges[index]['end'] + .02
        if uncertain:
            if ranges is None:
                return dict(original, quality='review', review_reason='alignment')
            segments.append(dict(original['segments'][index]))
            preserved.add(index)
        else:
            segments.append(dict(start=max(0, start - .1), end=end, text=line, confidence=confidence))
    # Retained lines are fixed anchors. If a proposed correction crosses another
    # line, restore only the corrections involved until written order is safe.
    while True:
        conflicts = [(i, i + 1) for i in range(len(segments) - 1)
                     if segments[i]['start'] >= segments[i + 1]['start']]
        if not conflicts:
            break
        if ranges is None:
            return dict(original, quality='review', review_reason='alignment')
        restore = {i for pair in conflicts for i in pair if i not in preserved}
        if not restore:
            raise ValueError('Original time anchors are inconsistent; lyrics were retained.')
        for i in restore:
            segments[i] = dict(original['segments'][i])
        preserved.update(restore)
    result = dict(original)
    result.update(text=text, segments=segments, source='forced-alignment',
                  quality='partially-aligned' if preserved else 'aligned', review_reason='',
                  timings_preserved=len(preserved))
    return result


def worker_main(parent_pid=None):
    protocol = sys.stdout
    sys.stdout = sys.stderr
    model = None
    def send(event, **data):
        protocol.write(json.dumps(dict(event=event, **data), ensure_ascii=True) + '\n')
        protocol.flush()
    send('ready')
    while True:
        line = sys.stdin.readline(2 * 1024 * 1024 + 1)
        if not line:
            return
        request_id = ''
        try:
            if len(line) > 2 * 1024 * 1024:
                raise ValueError('Timing correction request is too large')
            request = json.loads(line)
            request_id = request['id']
            if request.get('operation') != 'align':
                raise ValueError('This helper accepts timing correction only')
            original = request['lyrics']
            language = request.get('language') or 'ru'
            def progress(stage):
                send('progress', id=request_id, stage=stage)
            if model is None:
                progress('loading_alignment')
                from faster_whisper import WhisperModel
                import torch
                torch.set_num_threads(4)
                model = WhisperModel(os.environ.get('SONIC_FORGE_WHISPER_MODEL', 'large-v3-turbo'),
                                     device='cpu', compute_type='int8', cpu_threads=4)
            progress('aligning')
            result = align_existing(model, request['path'], original, language, progress)
            send('result', id=request_id, result=result)
        except Exception as exc:
            send('error', id=request_id, error=f'{type(exc).__name__}: {str(exc)[:1000]}')
