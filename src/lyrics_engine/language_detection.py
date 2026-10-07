"""Detect the song's language across its vocals, not only its introduction."""

from collections import Counter

import numpy as np


def language_windows(audio, sampling_rate=16000):
    """Three separated 20-second windows; preserve short clips in full."""
    window = min(len(audio), 20 * sampling_rate)
    if len(audio) <= 40 * sampling_rate:
        return [(0.0, audio)] if len(audio) else []
    starts = sorted({
        max(0, min(len(audio) - window, int(len(audio) * fraction) - window // 2))
        for fraction in (0.20, 0.50, 0.75)
    })
    return [(start / sampling_rate, audio[start:start + window]) for start in starts]


def combine_language_predictions(predictions):
    if not predictions:
        return None, None
    votes = Counter(language for language, _probability, _all in predictions)
    scores = Counter()
    for language, probability, distribution in predictions:
        scores.update(dict(distribution or [(language, probability)]))
    count = len(predictions)
    selected = max(scores, key=lambda language: (
        0.65 * scores[language] / count + 0.35 * votes[language] / count,
        scores[language],
    ))
    # This is the mean acoustic model probability, not a made-up "accuracy".
    return selected, min(1.0, max(0.0, scores[selected] / count))


def wide_language_windows(audio, sampling_rate=16000):
    """Longer context for an independent classifier on singing over music."""
    window = min(len(audio), 40 * sampling_rate)
    starts = sorted({max(0, min(len(audio) - window, int(len(audio) * fraction) - window // 2))
                     for fraction in (0.15, 0.35, 0.55, 0.75, 0.90)})
    return [(start / sampling_rate, audio[start:start + window]) for start in starts] if len(audio) else []


def _supported_prediction(predictions, minimum, vote_share, margin=0.0, peak=0.0):
    language, probability = combine_language_predictions(predictions)
    if language is None:
        return None, None
    count = len(predictions)
    votes = sum(item[0] == language for item in predictions) / count
    scores = Counter()
    for selected, confidence, distribution in predictions:
        scores.update(dict(distribution or [(selected, confidence)]))
    runner_up = max((value / count for code, value in scores.items() if code != language), default=0)
    strongest = max(dict(all_scores or [(code, confidence)]).get(language, 0.0)
                    for code, confidence, all_scores in predictions)
    if probability >= minimum and votes >= vote_share and probability - runner_up >= margin and strongest >= peak:
        return language, probability
    return None, probability


def detect_song_language(model, audio, cancel_event=None, identifier=None):
    predictions = []
    for _start, sample in language_windows(audio):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Lyrics recognition was cancelled.")
        if not len(sample) or float(np.sqrt(np.mean(sample ** 2))) < 0.001:
            continue
        predictions.append(model.detect_language(
            audio=sample, vad_filter=False,
            language_detection_segments=1, language_detection_threshold=1.0,
        ))
        if len(predictions) >= 2:
            language, probability = _supported_prediction(predictions, 0.80, 1.0, margin=0.35)
            if language is not None:
                return language, probability
    # Keep strong Whisper evidence: an independent model can confuse Russian
    # singing with Belarusian. Use it only to resolve weak/inconsistent votes.
    language, probability = _supported_prediction(predictions, 0.60, 2 / 3, margin=0.15)
    if language is not None:
        return language, probability
    if not predictions:
        return None, None
    if identifier is None:
        from .language_identifier import LocalLanguageIdentifier
        identifier = LocalLanguageIdentifier()
    fallback = []
    try:
        for _start, sample in wide_language_windows(audio):
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Lyrics recognition was cancelled.")
            if float(np.sqrt(np.mean(sample ** 2))) >= 0.001:
                fallback.append(identifier.detect_language(sample))
                if len(fallback) >= 3:
                    language, confidence = _supported_prediction(fallback, 0.50, 1.0, margin=0.25, peak=0.55)
                    if language is not None:
                        return language, confidence
    except (OSError, RuntimeError, ValueError, ImportError):
        # Missing offline model must never silently turn an uncertain song English.
        return None, probability
    return _supported_prediction(fallback, 0.35, 0.60, margin=0.12, peak=0.55)
