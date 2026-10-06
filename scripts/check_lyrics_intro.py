"""Compare introductory hallucinations without printing or saving full lyrics."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lyrics_engine.providers import FasterWhisperProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--mode", choices=("baseline", "silence", "vad", "clip", "verified", "provider"), default="baseline")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--beam", type=int, default=8)
    parser.add_argument("--context", action="store_true")
    args = parser.parse_args()
    if args.mode == "provider":
        import time
        started = time.monotonic()
        result = FasterWhisperProvider().transcribe(args.audio, language="ru")
        text = result.text.casefold().replace("ё", "е")
        print(json.dumps({"first_start": result.segments[0].start if result.segments else None,
                          "lines": len(result.segments),
                          "reported_hallucination": "девушки отдыхают" in text,
                          "opening_words": "в комнате темно" in text,
                          "dream_phrase_count": text.count("сон вчерашний"),
                          "wrong_dream_phrase_count": text.count("солнце вчерашний"),
                          "seconds": round(time.monotonic() - started, 2)}), flush=True)
        return
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    audio = decode_audio(args.audio, sampling_rate=16000)[int(args.start * 16000):int((args.start + args.duration) * 16000)]
    vad_options = VadOptions(threshold=0.25, min_speech_duration_ms=100,
                             min_silence_duration_ms=1000, speech_pad_ms=600)
    speech = get_speech_timestamps(audio, vad_options=vad_options)
    print(json.dumps({"voice_regions": [(round(s["start"] / 16000, 2), round(s["end"] / 16000, 2))
                                       for s in speech]}), flush=True)
    model = FasterWhisperProvider()._get_model()
    options = dict(language="ru", beam_size=args.beam, best_of=5, word_timestamps=True,
                   vad_filter=False, condition_on_previous_text=args.context,
                   max_initial_timestamp=30.0, temperature=(0.0, 0.2, 0.4))
    if args.mode == "silence":
        options["hallucination_silence_threshold"] = 2.0
    elif args.mode == "vad":
        options.update(vad_filter=True, vad_parameters=vad_options)
    elif args.mode == "clip" and speech:
        options["clip_timestamps"] = [speech[0]["start"] / 16000]
    segments, _ = model.transcribe(audio, **options)
    if args.mode == "verified":
        from lyrics_engine.verification import verified_segments
        segments = verified_segments(model, audio, segments, options)
    for segment in segments:
        text = segment.text.strip().lower().replace("ё", "е")
        print(json.dumps({"mode": args.mode, "start": segment.start + args.start, "end": segment.end + args.start,
                          "characters": len(segment.text.strip()),
                          "reported_hallucination": "девушки отдыхают" in text,
                          "opening_words": "в комнате темно" in text,
                          "dream_phrase": "сон вчерашний" in text,
                          "dream_word": "сон" in text.split(),
                          "sun_word": "солнце" in text.replace(",", "").split(),
                          "no_speech": segment.no_speech_prob, "avg_logprob": segment.avg_logprob,
                          "word_timings": [(w.start, w.end, round(w.probability, 3)) for w in segment.words or []]},
                         ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
