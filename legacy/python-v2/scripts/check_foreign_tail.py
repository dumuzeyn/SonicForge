"""Read-only end-of-song termination check; no lyric text or tag writes."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio')
    args = parser.parse_args()
    from faster_whisper.audio import decode_audio
    from lyrics_engine.providers import FasterWhisperProvider, _implausible_text
    from lyrics_engine.verification import verified_segments
    from lyrics_engine.transliteration import sound_spelling
    source = Path(args.audio)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    audio = decode_audio(str(source), sampling_rate=16000)[120 * 16000:]
    duration = len(audio) / 16000
    started = time.monotonic()
    provider = FasterWhisperProvider()
    model = provider._get_native_model('ka')
    options = dict(language='ka', task='transcribe', beam_size=8, best_of=5, vad_filter=False,
                   word_timestamps=True, condition_on_previous_text=False, max_initial_timestamp=30,
                   temperature=(0.0, .2, .4))
    raw, _ = model.transcribe(audio, **options)
    count = 0
    for segment in verified_segments(model, audio, raw, options, limit=0, audio_duration=duration):
        count += 1
        print(json.dumps({'line': count, 'start': segment.start + 120, 'end': segment.end + 120,
                          'ascii_only': sound_spelling(segment.text, 'en', 'ka').isascii(),
                          'requires_review': _implausible_text(segment, 'ka')}), flush=True)
    print(json.dumps({'completed': True, 'audio_end': duration + 120, 'lines': count,
                      'source_unchanged': before == hashlib.sha256(source.read_bytes()).hexdigest(),
                      'seconds': round(time.monotonic() - started, 2)}), flush=True)


if __name__ == '__main__':
    main()
