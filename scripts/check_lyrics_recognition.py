"""Read-only real-audio validation. Never writes tags or lyric sidecars."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from lyrics_engine.providers import FasterWhisperProvider
from lyrics_engine.language_detection import language_windows, combine_language_predictions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    provider = FasterWhisperProvider()
    model = provider._get_model()
    from faster_whisper.audio import decode_audio
    with provider._vocal_audio(args.audio) as prepared:
        audio = decode_audio(str(prepared), sampling_rate=16000)
        baseline = model.detect_language(audio=audio, language_detection_segments=3)
        print(json.dumps({"initial_guess": baseline[:2]}, ensure_ascii=True), flush=True)
        predictions = []
        for start, sample in language_windows(audio):
            prediction = model.detect_language(audio=sample, language_detection_threshold=1.0)
            predictions.append(prediction)
            print(json.dumps({"sample_start": start, "language": prediction[0],
                              "probability": prediction[1]}, ensure_ascii=True), flush=True)
        language, probability = combine_language_predictions(predictions)
        print(json.dumps({"multi_sample_language": language, "probability": probability}), flush=True)
        if args.probe_only:
            return
        started = time.monotonic()
        count = cyrillic = latin = 0
        def on_segment(segment):
            nonlocal count, cyrillic, latin
            count += 1
            cyrillic += sum("а" <= letter.lower() <= "я" or letter.lower() == "ё" for letter in segment.text)
            latin += sum("a" <= letter.lower() <= "z" for letter in segment.text)
            print(json.dumps({"line": count, "start": segment.start,
                              "end": segment.end, "characters": len(segment.text),
                              "letters": sum(c.isalpha() for c in segment.text),
                              "confidence": segment.confidence}, ensure_ascii=True), flush=True)
        result = provider.transcribe(args.audio, on_segment=on_segment)
        print(json.dumps({"lines": count, "cyrillic": cyrillic, "latin": latin,
                          "model": provider.model_name, "language": result.language,
                          "language_confidence": result.language_confidence,
                          "quality": result.quality, "review_reason": result.review_reason,
                          "instrumental": result.instrumental,
                          "first_start": result.segments[0].start if result.segments else None,
                          "last_end": result.segments[-1].end if result.segments else None,
                          "elapsed": round(time.monotonic() - started, 2)}), flush=True)


if __name__ == "__main__":
    main()
