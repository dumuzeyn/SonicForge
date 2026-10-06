"""Full read-only ASR runs against a user-provided phonetic reference.

The reference is used only after decoding for scoring, never as a model prompt.
Only timing and comparison statistics are printed; no song tags are written.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CYRILLIC_SOUNDS = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ("a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "i", "k", "l", "m", "n", "o",
     "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"),
))


def normalize(text):
    text = "".join(CYRILLIC_SOUNDS.get(c, c) for c in text.casefold())
    return re.sub(r"[^a-z]", "", text).replace("q", "k")


def edit_distance(reference, candidate, substring=False):
    row = [0] * (len(candidate) + 1) if substring else list(range(len(candidate) + 1))
    for i, expected in enumerate(reference, 1):
        next_row = [i]
        for j, actual in enumerate(candidate, 1):
            next_row.append(min(row[j] + 1, next_row[-1] + 1, row[j - 1] + (expected != actual)))
        row = next_row
    return min(row) if substring else row[-1]


def audio_replays(audio):
    """Waveform evidence of sampled/replayed verses, independent of ASR text."""
    import numpy as np
    audio = audio[::4].astype(np.float64)
    reference = audio[:int(8.74 * 4000)]
    reference = reference - reference.mean()
    length = 1 << int(np.ceil(np.log2(len(audio) + len(reference) - 1)))
    cross = np.fft.irfft(np.fft.rfft(audio, length) * np.fft.rfft(reference[::-1], length), length)
    cross = cross[len(reference) - 1:len(audio)]
    sums = np.concatenate(([0.], np.cumsum(audio)))
    squares = np.concatenate(([0.], np.cumsum(audio * audio)))
    energy = squares[len(reference):] - squares[:-len(reference)]
    energy -= (sums[len(reference):] - sums[:-len(reference)]) ** 2 / len(reference)
    score = cross / np.sqrt(np.maximum(energy, 1e-12) * np.sum(reference * reference))
    peaks = []
    for _ in range(8):
        index = int(np.argmax(score))
        peaks.append(dict(start=round(index / 4000, 3), correlation=round(float(score[index]), 3)))
        score[max(0, index - len(reference)):min(len(score), index + len(reference))] = -1
    return peaks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("reference")
    parser.add_argument("--modes", nargs="+", choices=("baseline", "short"), default=["baseline", "short"])
    parser.add_argument("--model", choices=("native", "base"), default="native")
    parser.add_argument("--check-repeats", action="store_true")
    parser.add_argument("--duration", type=float)
    args = parser.parse_args()
    from faster_whisper.audio import decode_audio
    from lyrics_engine.providers import FasterWhisperProvider, _implausible_text
    from lyrics_engine.transliteration import sound_spelling
    from lyrics_engine.verification import verified_segments

    source = Path(args.audio)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    reference = Path(args.reference).read_text(encoding="utf-8")
    lines = list(dict.fromkeys(normalize(line) for line in reference.splitlines() if normalize(line)))
    target = normalize(reference)
    audio = decode_audio(str(source), sampling_rate=16000)
    if args.duration:
        audio = audio[:int(args.duration * 16000)]
    duration = len(audio) / 16000
    if args.check_repeats:
        print(json.dumps({"waveform_replays": audio_replays(audio)}), flush=True)
        return
    provider = FasterWhisperProvider()
    model = provider._get_native_model("ka") if args.model == "native" else provider._get_model()
    for mode in args.modes:
        started = time.monotonic()
        options = dict(language="ka", task="transcribe", beam_size=8, best_of=5, vad_filter=False,
                       word_timestamps=True, condition_on_previous_text=False, max_initial_timestamp=30,
                       temperature=(0.0, .2, .4))
        if mode == "short":
            options.update(beam_size=5, chunk_length=15, max_initial_timestamp=15, temperature=0.0)
        print(json.dumps({"stage": "started", "model": args.model, "mode": mode, "duration": duration}), flush=True)
        raw, _ = model.transcribe(audio, **options)
        segments = []
        for segment in verified_segments(model, audio, raw, options, limit=0, audio_duration=duration):
            segments.append(segment)
            print(json.dumps({"mode": mode, "line": len(segments), "start": segment.start,
                              "end": segment.end, "chars": len(segment.text),
                              "compression": segment.compression_ratio,
                              "requires_review": _implausible_text(segment, "ka")}), flush=True)
        candidate = normalize(" ".join(sound_spelling(segment.text, "en", "ka") for segment in segments))
        line_errors = [round(edit_distance(line, candidate, substring=True) / len(line), 3) for line in lines]
        print(json.dumps({"completed": True, "model": args.model, "mode": mode, "duration": duration,
                          "seconds": round(time.monotonic() - started, 2), "segments": len(segments),
                          "ordered_reference_char_error": round(edit_distance(target, candidate) / len(target), 3),
                          "unique_reference_lines": len(lines), "matched_within_20pct": sum(e <= .2 for e in line_errors),
                          "line_errors": line_errors, "recognized_chars": len(candidate),
                          "review_segments": sum(_implausible_text(segment, "ka") for segment in segments),
                          "source_unchanged": before == hashlib.sha256(source.read_bytes()).hexdigest()}), flush=True)


if __name__ == "__main__":
    main()
