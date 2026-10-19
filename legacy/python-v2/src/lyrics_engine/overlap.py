"""Short acoustic windows with word-aware stitching on the original timeline."""
import copy
import re
from types import SimpleNamespace
from itertools import chain

from .audio import SAMPLE_RATE

WINDOW_SECONDS = 20.0
OVERLAP_SECONDS = 6.0


def windows(samples, sample_rate=SAMPLE_RATE):
    width = int(WINDOW_SECONDS * sample_rate)
    step = int((WINDOW_SECONDS - OVERLAP_SECONDS) * sample_rate)
    start = 0
    while start < samples:
        end = min(samples, start + width)
        yield start, end
        if end == samples:
            break
        start += step


def _token(word):
    return ''.join(re.findall(r'\w+', word.word.casefold()))


def _words(segments):
    return [word for segment in segments for word in (getattr(segment, 'words', None) or ())]


def _text(words):
    separator = '' if any(w.word[:1].isspace() for w in words) else ' '
    return separator.join(w.word for w in words).strip()


def _part(segment, words):
    result = copy.copy(segment)
    result.words = words
    result.start, result.end = words[0].start, words[-1].end
    result.text = _text(words)
    return result


def _slice(segments, words, before, cut):
    selected = {id(word) for word in words}
    result = []
    for segment in segments:
        original = getattr(segment, 'words', None) or ()
        if original:
            keep = [word for word in original if id(word) in selected]
            if keep:
                result.append(segment if len(keep) == len(original) else _part(segment, keep))
        elif ((segment.start + segment.end) / 2 < cut) == before:
            # No word alignment: preserve complete segments, never cut text.
            result.append(segment)
    return result


def stitch(left, right, overlap_start, overlap_end):
    """Finalize the older window and retain the new one for the next overlap.

    Prefer a shared word with matching acoustic time and adjacent context. Only
    the same occurrence in the overlap is removed; later chorus repetitions stay.
    If decoders disagree, switch at a whole word in the center of the overlap.
    """
    midpoint = (overlap_start + overlap_end) / 2
    left_present = any(s.end > overlap_start and s.start < overlap_end for s in left)
    right_present = any(s.end > overlap_start and s.start < overlap_end for s in right)
    if not left_present or not right_present:
        # A missed/empty context is not permission to delete the other window's
        # real opening, or the beginning of a later repeated chorus.
        return list(left), list(right)
    old, new = _words(left), _words(right)
    anchors = []
    for i, word in enumerate(old):
        center = (word.start + word.end) / 2
        if not overlap_start <= center <= overlap_end or not _token(word):
            continue
        for j, other in enumerate(new):
            other_center = (other.start + other.end) / 2
            if (not overlap_start <= other_center <= overlap_end or
                    abs(center - other_center) > .75 or _token(word) != _token(other)):
                continue
            context = sum(0 <= i + delta < len(old) and 0 <= j + delta < len(new)
                          and _token(old[i + delta]) == _token(new[j + delta])
                          and abs(old[i + delta].start - new[j + delta].start) <= .75
                          for delta in (-1, 1))
            anchors.append((context, -abs((center + other_center) / 2 - midpoint), i, j))
    if anchors:
        _, _, i, j = max(anchors)
        cut = max(old[i].end, new[j].end)
        return (_slice(left, old[:i + 1], True, cut),
                _slice(right, new[j + 1:], False, cut))
    old_overlap = [w for w in old if w.end > overlap_start and w.start < overlap_end]
    new_overlap = [w for w in new if w.end > overlap_start and w.start < overlap_end]
    if new_overlap:
        first = min(new_overlap, key=lambda w: abs(w.start - midpoint))
        cut = first.start
        # Prefer the new window's complete word to the old edge's fragment.
        prefix = [w for w in old if w.end <= cut + .05]
        suffix = new[new.index(first):]
    elif old_overlap:
        cut = overlap_end
        prefix, suffix = old, new
    else:
        cut = midpoint
        prefix = [w for w in old if (w.start + w.end) / 2 < cut]
        suffix = [w for w in new if (w.start + w.end) / 2 >= cut]
    return _slice(left, prefix, True, cut), _slice(right, suffix, False, cut)


def transcribe_overlapping(model, audio, language, options, cancel_event=None, progress=None, retry_empty=False):
    info = SimpleNamespace(language=language or 'unknown', language_probability=None, truncated=False)
    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError('Lyrics recognition was cancelled.')

    def generate():
        pending = []
        previous_end = 0.0
        for start, end in windows(len(audio)):
            check_cancel()
            offset, stop = start / SAMPLE_RATE, end / SAMPLE_RATE
            clip = audio[start:end]  # view, no second song-sized waveform
            current = []
            if progress:
                progress('transcribing')
            if clip.any():
                rows, window_info = model.transcribe(clip, language=language, **options)
                rows = iter(rows)
                first = next(rows, None)
                check_cancel()
                if first is None and retry_empty:
                    # Retry this missed excerpt, even if later song windows have
                    # lyrics. A whole-song empty check cannot recover an intro.
                    if progress:
                        progress('verifying')
                    retry_options = dict(options, beam_size=3, temperature=0.0,
                                         no_speech_threshold=None, log_prob_threshold=None)
                    rows, window_info = model.transcribe(clip, language=language, **retry_options)
                    rows = iter(rows)
                    first = next(rows, None)
                    check_cancel()
                rows = chain((first,), rows) if first is not None else iter(())
                for index, raw in enumerate(rows):
                    check_cancel()
                    if index >= 256:
                        info.truncated = True
                        break
                    if raw.start >= stop - offset:
                        break
                    if (raw.start >= stop - offset - 1 and raw.end - raw.start <= .5
                            and sum(c.isalpha() for c in raw.text) >= 20):
                        # Do not collect an endlessly repeated padded final sliver.
                        break
                    if not raw.text.strip() or raw.end <= max(0, raw.start):
                        continue
                    segment = copy.copy(raw)
                    segment.start, segment.end = max(offset, raw.start + offset), min(stop, raw.end + offset)
                    segment.words = []
                    raw_words = getattr(raw, 'words', None) or ()
                    for word in raw_words:
                        if word.end <= max(0, word.start) or word.start >= stop - offset:
                            continue
                        word_audio = clip[max(0, int(word.start * SAMPLE_RATE)):min(len(clip), int(word.end * SAMPLE_RATE))]
                        if not word_audio.any():
                            continue  # Reject guesses in exact digital silence, not quiet singing.
                        rebased = copy.copy(word)
                        rebased.start, rebased.end = max(offset, word.start + offset), min(stop, word.end + offset)
                        segment.words.append(rebased)
                    if raw_words and not segment.words:
                        continue
                    if not raw_words and not clip[max(0, int(raw.start * SAMPLE_RATE)):min(len(clip), int(raw.end * SAMPLE_RATE))].any():
                        continue
                    if segment.words:
                        segment.text = _text(segment.words)
                        segment.start, segment.end = segment.words[0].start, segment.words[-1].end
                    if segment.end > segment.start:
                        current.append(segment)
                if current:
                    info.language = getattr(window_info, 'language', None) or info.language
                    info.language_probability = getattr(window_info, 'language_probability', None)
            check_cancel()
            if start:
                complete, pending = stitch(pending, current, offset, previous_end)
                yield from complete
            else:
                pending = current
            previous_end = stop
        check_cancel()
        yield from pending
    return generate(), info
