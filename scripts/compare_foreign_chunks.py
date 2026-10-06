"""Read-only Georgian singing context comparison; prints scores, not lyrics."""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def prefix_error(text, target):
    row = list(range(len(target) + 1))
    best = len(target)
    for i, character in enumerate(text, 1):
        next_row = [i]
        for j, expected in enumerate(target, 1):
            next_row.append(min(row[j] + 1, next_row[-1] + 1, row[j - 1] + (character != expected)))
        row = next_row
        if len(target) * .6 <= i <= len(target) * 1.5:
            best = min(best, row[-1])
    return best / len(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--chunk", type=int, default=30)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--deterministic", action="store_true")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    from faster_whisper.audio import decode_audio
    from lyrics_engine.providers import FasterWhisperProvider
    from lyrics_engine.transliteration import sound_spelling
    from lyrics_engine.verification import verified_segments

    source = Path(args.audio)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    audio = decode_audio(str(source), sampling_rate=16000)
    audio = audio[int(args.start * 16000):int((args.start + args.duration) * 16000)]
    model = FasterWhisperProvider()._get_native_model("ka")
    modes = [(30, False), (15, True), (20, True)] if args.compare else [(args.chunk, args.deterministic)]
    for chunk, deterministic in modes:
        started = time.monotonic()
        options = dict(language="ka", task="transcribe", beam_size=5 if deterministic else 8,
                       best_of=5, vad_filter=False, word_timestamps=True, condition_on_previous_text=False,
                       max_initial_timestamp=float(chunk), chunk_length=chunk,
                       temperature=0.0 if deterministic else (0.0, 0.2, 0.4))
        raw, _ = model.transcribe(audio, **options)
        segments = []
        print(json.dumps({"stage": "loaded", "chunk": chunk, "deterministic": deterministic}), flush=True)
        for segment in verified_segments(model, audio, raw, options, limit=0, audio_duration=len(audio) / 16000):
            segments.append(segment)
            print(json.dumps({"start": segment.start + args.start, "end": segment.end + args.start,
                              "chars": len(segment.text), "avg_logprob": segment.avg_logprob,
                              "compression": segment.compression_ratio}), flush=True)
        # First stanza supplied by the user, used only as a phonetic diagnostic
        # reference. Not a vocabulary/prompt and never part of recognition runtime.
        reference = "tsqals napoti chamokonda alvis khis chamonatani dadek napoto miambe sakvarlis chamonatani"
        normalize = lambda text: re.sub(r"[^a-z]", "", text.lower()).replace("q", "k")
        text = normalize(" ".join(sound_spelling(s.text, "en", "ka") for s in segments))
        target = normalize(reference)
        # Edit distance against an approximate user transliteration, not native WER.
        print(json.dumps({"completed": True, "chunk": chunk, "deterministic": deterministic,
                          "segments": len(segments), "normalized_chars": len(text),
                          "first_stanza_prefix_error": prefix_error(text, target),
                          "source_unchanged": before == hashlib.sha256(source.read_bytes()).hexdigest(),
                          "seconds": round(time.monotonic() - started, 2)}), flush=True)


if __name__ == "__main__":
    main()
