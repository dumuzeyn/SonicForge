"""Validate a real song read-only, reporting metrics instead of lyric text."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio')
    args = parser.parse_args()
    from lyrics_engine import LyricsService
    source = Path(args.audio)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    count = 0
    def line(segment):
        nonlocal count
        count += 1
        print(json.dumps({'line': count, 'start': segment.start, 'end': segment.end,
                          'words': len(segment.text.split()), 'ascii_only': segment.text.isascii(),
                          'confidence': segment.confidence}), flush=True)
    started = time.monotonic()
    result = LyricsService().recognize(source, language='auto', on_segment=line)
    print(json.dumps({'language': result.language, 'language_probability': result.language_confidence,
                      'alphabet': result.transcription_alphabet, 'lines': len(result.segments),
                      'ascii_only': result.text.isascii(), 'quality': result.quality,
                      'review_reason': result.review_reason, 'usable': LyricsService.is_usable(result),
                      'reported_english_phrases': any(phrase in result.text.casefold() for phrase in
                                                    ('thank you', 'see you next time', 'name of the king')),
                      'timestamps_valid': all(0 <= s.start < s.end for s in result.segments),
                      'audio_unchanged': before == hashlib.sha256(source.read_bytes()).hexdigest(),
                      'seconds': round(time.monotonic() - started, 2)}), flush=True)


if __name__ == '__main__':
    main()
