"""Read-only ASR comparison; reference words are never supplied to the model."""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lyrics_engine.providers import FasterWhisperProvider


def normalized_words(text):
    return re.findall(r"[а-яa-z0-9]+", text.lower().replace("ё", "е"))


def word_error_rate(reference, hypothesis):
    expected, actual = normalized_words(reference), normalized_words(hypothesis)
    previous = list(range(len(actual) + 1))
    for row, word in enumerate(expected, 1):
        current = [row]
        for column, guess in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[column] + 1,
                               previous[column - 1] + (word != guess)))
        previous = current
    return previous[-1] / max(1, len(expected))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--duration", type=float, default=90)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--context", action="store_true")
    parser.add_argument("--reference")
    args = parser.parse_args()
    print(json.dumps({"loading": args.model, "raw": args.raw}), flush=True)
    provider = FasterWhisperProvider(model_name=args.model)
    model = provider._get_model()
    from faster_whisper.audio import decode_audio
    from contextlib import nullcontext
    with (nullcontext(args.audio) if args.raw else provider._vocal_audio(args.audio)) as prepared:
        audio = decode_audio(str(prepared), sampling_rate=16000)
        clip = audio[int(args.start * 16000):int((args.start + args.duration) * 16000)]
        started = time.monotonic()
        segments, _info = model.transcribe(
            clip, language="ru", beam_size=8, best_of=5, word_timestamps=True,
            vad_filter=False, condition_on_previous_text=args.context,
            max_initial_timestamp=30.0, temperature=(0.0, 0.2, 0.4),
        )
        rows = []
        for segment in segments:
            rows.append(segment.text.strip())
            print(json.dumps({"start": segment.start + args.start, "characters": len(segment.text.strip()),
                              "avg_logprob": segment.avg_logprob}, ensure_ascii=True), flush=True)
        result = {"model": args.model, "raw": args.raw, "seconds": round(time.monotonic() - started, 2)}
        if args.reference:
            result["wer"] = word_error_rate(Path(args.reference).read_text(encoding="utf-8"), " ".join(rows))
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
