"""Read-only native-script recognition statistics, never full lyric output."""
import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--language", default="ka")
    parser.add_argument("--start", type=float, default=60)
    parser.add_argument("--duration", type=float, default=40)
    parser.add_argument("--model")
    args = parser.parse_args()
    from faster_whisper.audio import decode_audio
    from lyrics_engine.providers import FasterWhisperProvider
    audio = decode_audio(args.audio, sampling_rate=16000)[int(args.start * 16000):int((args.start + args.duration) * 16000)]
    model = FasterWhisperProvider(model_name=args.model)._get_model()
    segments, _ = model.transcribe(audio, language=args.language, task="transcribe", beam_size=8,
                                  vad_filter=False, word_timestamps=True, condition_on_previous_text=False,
                                  max_initial_timestamp=30.0, temperature=(0.0, 0.2, 0.4))
    previous = ""
    for segment in segments:
        print(json.dumps({"start": segment.start + args.start, "end": segment.end + args.start,
                          "characters": len(segment.text),
                          "georgian_letters": sum('\u10a0' <= c <= '\u10ff' or '\u1c90' <= c <= '\u1cbf' for c in segment.text),
                          "latin_letters": sum('a' <= c.lower() <= 'z' for c in segment.text),
                          "words": len(segment.text.split()), "compression_ratio": segment.compression_ratio,
                          "previous_similarity": SequenceMatcher(None, previous, segment.text).ratio(),
                          "avg_logprob": segment.avg_logprob, "no_speech": segment.no_speech_prob,
                          "reported_english_phrases": any(t in segment.text.lower() for t in ('thank you', 'see you next time', 'name of the king'))}), flush=True)
        previous = segment.text


if __name__ == "__main__":
    main()
