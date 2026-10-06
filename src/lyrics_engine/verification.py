"""Verify doubtful singing against shifted audio context, never a lyric dictionary."""
import re
import copy
from collections import Counter, defaultdict
from dataclasses import replace
from difflib import SequenceMatcher
from itertools import islice


def tokens(text):
    return re.findall(r"[^\W_]+", text.casefold().replace("ё", "е"), re.UNICODE)


def doubtful_words(segment):
    return [word for word in getattr(segment, "words", None) or ()
            if any(len(token) >= 3 for token in tokens(word.word))
            and float(word.probability) < 0.8]


def suspicious_after_pause(segment, previous_end):
    words = getattr(segment, "words", None) or ()
    # Instrumental intros can produce even very confident invented phrases.
    # A short phrase after a long pause deserves acoustic confirmation too.
    return (segment.start - previous_end >= 8.0 and bool(words)
            and (len(tokens(segment.text)) <= 4
                 or (bool(doubtful_words(segment))
                     and any(word.end - word.start < 0.12 for word in words))))


def trim_unconfirmed_prefix(original, candidates):
    """Remove weak inserted words only when the remaining words align in time."""
    old_tokens = tokens(original.text)
    old_words = tuple(getattr(original, "words", None) or ())
    matches = list(re.finditer(r"[^\W_]+", original.text, re.UNICODE))
    if len(old_words) != len(old_tokens) or len(matches) != len(old_tokens):
        return original
    if any(tokens(word.word) != [token] for word, token in zip(old_words, old_tokens)):
        return original
    for candidate in candidates:
        new_tokens = tokens(candidate.text)
        skipped = len(old_tokens) - len(new_tokens)
        if not 1 <= skipped <= 4 or len(new_tokens) < 2 or new_tokens != old_tokens[skipped:]:
            continue
        prefix = old_words[:skipped]
        if not all(float(w.probability) < .65 or w.end - w.start < .12 for w in prefix):
            continue
        if (abs(candidate.start - old_words[skipped].start) > .75
                or abs(candidate.end - original.end) > 1.0
                or float(getattr(candidate, "avg_logprob", -10))
                < float(getattr(original, "avg_logprob", 0)) - .1):
            continue
        cleaned = copy.copy(original)
        cleaned.text = original.text[matches[skipped].start():].strip()
        cleaned.start = old_words[skipped].start
        cleaned.words = list(old_words[skipped:])
        return cleaned
    return original


def choose_verified_segment(original, candidates, after_pause=False):
    """Keep the original unless shifted decoding provides positive evidence."""
    original_tokens = tokens(original.text)
    nearby = [candidate for candidate in candidates if candidate.text.strip()
              and candidate.end > original.start - 1.0
              and candidate.start < original.end + 1.5]
    cleaned = trim_unconfirmed_prefix(original, nearby)
    if cleaned is not original:
        return cleaned
    if after_pause:
        # A short, anomalous utterance after a long pause must be reproduced in
        # shifted context. Do not use no_speech_prob alone: it can be overconfident.
        confirmed = any(SequenceMatcher(None, original_tokens, tokens(c.text)).ratio() >= 0.65
                        and c.start < original.end and c.end > original.start
                        for c in nearby)
        following_voice = any(c.start <= original.end + 1.5
                              and float(getattr(c, "avg_logprob", -10)) > -0.5
                              and len(tokens(c.text)) >= 3 for c in nearby)
        if not confirmed and following_voice:
            return None
    for candidate in nearby:
        if abs(candidate.start - original.start) > 1.5 or abs(candidate.end - original.end) > 1.5:
            continue
        candidate_tokens = tokens(candidate.text)
        if len(candidate_tokens) != len(original_tokens) or len(original_tokens) < 4:
            continue
        differences = [i for i, pair in enumerate(zip(original_tokens, candidate_tokens)) if pair[0] != pair[1]]
        if len(differences) != 1:
            continue
        index = differences[0]
        old_words = getattr(original, "words", None) or ()
        new_words = getattr(candidate, "words", None) or ()
        # One Whisper word can contain multiple tokens: avoid guessing alignment.
        if len(old_words) != len(original_tokens) or len(new_words) != len(candidate_tokens):
            continue
        if any(len(tokens(w.word)) != 1 for w in (*old_words, *new_words)):
            continue
        if (float(old_words[index].probability) < 0.8
                and float(new_words[index].probability) >= float(old_words[index].probability) + 0.01
                and float(getattr(candidate, "avg_logprob", -10)) >= float(getattr(original, "avg_logprob", 0)) + 0.03):
            return candidate
    return original


def verified_segments(model, audio, raw_segments, options, cancel_event=None, progress=None, limit=12,
                      audio_duration=None):
    def recheck(original, start, end):
        verification_options = dict(options, temperature=0.0, clip_timestamps=[start, end])
        verification, _ = model.transcribe(audio, **verification_options)
        candidates = []
        for candidate in islice(verification, 16):
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Lyrics recognition was cancelled.")
            if candidate.start >= original.end + 1.5:
                break
            candidates.append(candidate)
        return candidates

    previous_end = 0.0
    previous_segment = None
    attempts = 0
    for raw in raw_segments:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Lyrics recognition was cancelled.")
        if audio_duration is not None:
            if raw.start >= audio_duration:
                break
            # Whisper's word alignment can stop advancing its seek position on
            # a padded final sliver, repeatedly inventing a whole sentence.
            # Never chase a sentence in the last sub-second forever.
            if (raw.start >= audio_duration - 1.0 and raw.end - raw.start <= 0.5
                    and sum(c.isalpha() for c in raw.text) >= 20):
                if progress:
                    progress("unreliable_tail")
                break
        if duplicate_boundary_segment(raw, previous_segment):
            continue
        after_pause = suspicious_after_pause(raw, previous_end)
        opening = previous_segment is None and bool(getattr(raw, "words", None))
        if opening and len(tokens(raw.text)) <= 4 and doubtful_words(raw):
            after_pause = True
        if attempts < limit and (opening or after_pause or doubtful_words(raw)):
            attempts += 1
            if progress:
                progress("verifying")
            start = max(0.0, raw.start - 5.0)
            # Short isolated singing clips can lose entire words. Keep one full
            # Whisper window of context, shifted away from the original boundary.
            original = raw
            candidates = recheck(raw, start, max(start + 30.0, raw.end + 5.0))
            raw = choose_verified_segment(raw, candidates, after_pause)
            # Do not discard a confident real opening just because one shifted
            # pass missed it. Require a second acoustic context to agree.
            if raw is None and not doubtful_words(original):
                if attempts >= limit:
                    raw = original
                else:
                    attempts += 1
                    second_start = max(0.0, original.start - 2.0)
                    candidates = recheck(original, second_start,
                                         max(second_start + 25.0, original.end + 3.0))
                    raw = choose_verified_segment(original, candidates, after_pause)
        if raw is not None:
            previous_end = max(previous_end, raw.end)
            previous_segment = raw
            yield raw
            if audio_duration is not None and previous_end >= audio_duration - 0.25:
                break


def duplicate_boundary_segment(segment, previous):
    """Reject an adjacent duplicated sentence crammed into a timestamp sliver."""
    if previous is None or segment.end - segment.start > 0.35:
        return False
    letters = sum(c.isalpha() for c in segment.text)
    if letters < 20 or abs(segment.start - previous.end) > 1.0:
        return False
    return SequenceMatcher(None, tokens(previous.text), tokens(segment.text)).ratio() >= 0.8


def repair_repeated_words(segments, word_groups):
    """Resolve one weak word using repeated six-word context within this song."""
    entries = []
    for index, (segment, words) in enumerate(zip(segments, word_groups)):
        matches = list(re.finditer(r"[^\W_]+", segment.text, re.UNICODE))
        aligned = (len(words) == len(matches)
                   and [tokens(w.word) for w in words] == [tokens(m.group()) for m in matches])
        for offset, match in enumerate(matches):
            entries.append((index, match.span(), tokens(match.group())[0],
                            float(words[offset].probability) if aligned else 1.0,
                            float(words[offset].start) if aligned else segment.start))
    groups = defaultdict(list)
    for i in range(3, len(entries) - 3):
        if len(entries[i][2]) >= 3:
            context = tuple(entries[j][2] for j in (i - 3, i - 2, i - 1, i + 1, i + 2, i + 3))
            groups[context].append(i)
    changes = defaultdict(list)
    for positions in groups.values():
        votes = Counter(entries[i][2] for i in positions)
        winner, count = votes.most_common(1)[0]
        supporters = [i for i in positions if entries[i][2] == winner]
        if (count < 2 or count / len(positions) < 2 / 3
                or max(entries[i][4] for i in supporters) - min(entries[i][4] for i in supporters) < 15
                or sum(entries[i][3] for i in supporters) / count < 0.5):
            continue
        for i in positions:
            index, span, word, probability, _ = entries[i]
            if word != winner and probability < 0.9:
                original = segments[index].text[span[0]:span[1]]
                replacement = winner.capitalize() if original[:1].isupper() else winner
                changes[index].append((span, replacement))
    result = list(segments)
    for index, replacements in changes.items():
        text = segments[index].text
        for (start, end), word in sorted(replacements, reverse=True):
            text = text[:start] + word + text[end:]
        result[index] = replace(segments[index], text=text)
    return result
