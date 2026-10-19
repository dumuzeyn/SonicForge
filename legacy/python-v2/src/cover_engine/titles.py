import re
from dataclasses import asdict, dataclass


TITLE_MODES = ("original", "cleaned", "stylized", "short")
AUDIO_EXTENSIONS = ("mp3", "wav", "flac", "m4a", "aac", "ogg", "opus", "wma", "aiff")
NOISE_TAGS = (
    "official audio", "official video", "lyrics", "lyric video", "audio",
    "remastered", "music video", "visualizer", "клип", "текст песни",
    "официальное видео", "официальное аудио", "hq", "hd",
)
STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "и", "или", "в", "на", "из", "к", "с", "по", "для", "под", "над", "от",
}
TECHNICAL_WORDS = {
    "track", "song", "audio", "music", "file", "untitled", "demo", "final",
    "трек", "песня", "аудио", "файл", "без", "названия",
}


@dataclass(frozen=True)
class TitleResolution:
    original: str
    cleaned: str
    stylized: str
    short: str
    selected: str
    mode: str
    display_lines: tuple[str, ...]
    display_title: str
    line_emphasis: tuple[float, ...]
    case_strategy: str
    emphasis_words: tuple[str, ...]
    confidence: float
    fallback_used: bool

    def to_dict(self):
        return asdict(self)


def clean_title(value):
    original = str(value or "").strip()
    text = re.sub(rf"\.(?:{'|'.join(AUDIO_EXTENSIONS)})$", "", original, flags=re.I)
    text = text.replace("_", " ")
    text = re.sub(r"^\s*(?:\[?\d{1,3}\]?\s*[-–—._)]\s*)+", "", text)
    text = re.sub(r"\s*[\[(]?\s*\d{2,4}\s*(?:k(?:b|bit)?ps|kb/s)\s*[\])]?(?:\s|$)", " ", text, flags=re.I)
    text = re.sub(r"\s*[-–—]\s*(?:normalized|mastered|cover\s*\d*|final\s*mix)\s*$", "", text, flags=re.I)
    for tag in NOISE_TAGS:
        text = re.sub(rf"\s*[\[(]\s*{re.escape(tag)}\s*[\])]", "", text, flags=re.I)
    text = re.sub(
        r"\s*(?:[-–—|]\s*)?(?:official\s+(?:audio|video)|lyric\s+video|youtube\s+audio)\s*$",
        "", text, flags=re.I,
    )
    text = re.sub(r"\s*(?:[-–—|]\s*)?(?:uploaded\s+by\s+)?@[\w.-]+\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*(?:[-–—|]\s*)?(?:https?://|www\.)\S+\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*(?:[-–—|]\s*)?[\w.-]+\.(?:com|net|org|ru|io)\s*$", "", text, flags=re.I)
    text = re.sub(r"(?:\s+[-–—|]\s+|[-–—|]{2,})", " — ", text)
    text = re.sub(r"\s+", " ", text).strip(" ._-–—|")
    return text or original or "Untitled"


def clean_artist(value):
    text = str(value or "").strip()
    text = re.sub(r"\s*[\[(](?:https?://|www\.)?[^\])]*\.[a-z]{2,}[^\])]*[\])]", "", text, flags=re.I)
    text = re.sub(r"\s+(?:https?://|www\.)\S+", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ._-–—|")
    return text


def stylize_title(value, profile=None):
    return _build_treatment(value, profile).stylized


def short_display_title(value, max_words=4, max_length=28, profile=None):
    return _build_treatment(value, profile, max_words=max_words, max_length=max_length).short


def resolve_title(value, mode="stylized", profile=None, short_enabled=True):
    mode = mode if mode in TITLE_MODES else "cleaned"
    treatment = _build_treatment(value, profile)
    selected_mode = mode
    fallback_used = treatment.fallback_used if mode == "stylized" else False
    if mode == "short" and (not short_enabled or treatment.short == treatment.cleaned):
        selected_mode = "cleaned"
        fallback_used = True
    selected = {
        "original": treatment.original,
        "cleaned": treatment.cleaned,
        "stylized": treatment.stylized,
        "short": treatment.short,
    }[selected_mode]
    if selected_mode == "stylized" and not fallback_used:
        display_lines, line_emphasis, case_strategy = _display_treatment(
            selected, treatment.emphasis_words, profile
        )
    elif selected_mode == "short":
        display_lines = _balanced_lines(selected, max_lines=2)
        line_emphasis = tuple(1.0 if index == len(display_lines) - 1 else .78 for index in range(len(display_lines)))
        case_strategy = "compact hierarchy"
    else:
        display_lines = (selected,)
        line_emphasis = (1.0,)
        case_strategy = "canonical"
    return TitleResolution(
        original=treatment.original,
        cleaned=treatment.cleaned,
        stylized=treatment.stylized,
        short=treatment.short,
        selected=selected,
        mode=selected_mode,
        display_lines=display_lines,
        display_title="\n".join(display_lines),
        line_emphasis=line_emphasis,
        case_strategy=case_strategy,
        emphasis_words=treatment.emphasis_words,
        confidence=treatment.confidence,
        fallback_used=fallback_used,
    )


def _build_treatment(value, profile=None, max_words=4, max_length=28):
    original = str(value or "").strip() or "Untitled"
    cleaned = clean_title(original)
    words = cleaned.split()
    meaningful = [word for word in words if _word_key(word) not in STOP_WORDS]
    technical_ratio = sum(_word_key(word) in TECHNICAL_WORDS or word.isdigit() for word in meaningful) / max(1, len(meaningful))
    has_structure = any(mark in cleaned for mark in (" — ", ": ", "(", ")"))
    lexical_strength = min(1.0, len("".join(meaningful)) / 16.0)
    confidence = max(0.0, min(1.0, .28 + lexical_strength * .48 + (.16 if has_structure else 0) - technical_ratio * .55))
    emphasis = _emphasis_words(words, profile)

    # Styling changes editorial structure and hierarchy, not merely letter case.
    stylized = cleaned
    if confidence >= .55:
        stylized = re.sub(r"\s*\(([^()]{2,36})\)\s*$", r": \1", stylized)
        stylized = re.sub(r"\s+—\s+", ": ", stylized, count=1) if stylized.count(" — ") == 1 else stylized
        stylized = _normalize_word_case(stylized)
    fallback_used = confidence < .55
    if fallback_used:
        stylized = cleaned

    short = _short_semantic_span(stylized, emphasis, max_words, max_length)
    if confidence < .62 or short == "":
        short = cleaned
    return TitleResolution(
        original=original,
        cleaned=cleaned,
        stylized=stylized,
        short=short,
        selected=cleaned,
        mode="cleaned",
        display_lines=(cleaned,),
        display_title=cleaned,
        line_emphasis=(1.0,),
        case_strategy="canonical",
        emphasis_words=emphasis,
        confidence=round(confidence, 3),
        fallback_used=fallback_used,
    )


def _emphasis_words(words, profile):
    context = []
    for field in ("themes", "imagery", "objects", "conflicts"):
        context.extend(getattr(profile, field, ()) or ())
    context_tokens = {_word_key(token) for item in context for token in str(item).split()}
    scored = []
    for index, word in enumerate(words):
        key = _word_key(word)
        if not key or key in STOP_WORDS:
            continue
        semantic_match = any(key in token or token in key for token in context_tokens if len(token) > 3)
        score = (2.2 if semantic_match else 0.0) + min(len(key), 10) / 10 + (0.18 if index in (0, len(words) - 1) else 0)
        if key in TECHNICAL_WORDS or word.isdigit():
            score -= 2.5
        scored.append((score, index, word.strip(".,:;!?()[]")))
    scored.sort(reverse=True)
    return tuple(item[2] for item in scored[:2] if item[0] > 0)


def _short_semantic_span(title, emphasis_words, max_words, max_length):
    words = title.replace(":", " ").split()
    if len(words) <= max_words and len(title) <= max_length:
        return title
    emphasis_keys = {_word_key(word) for word in emphasis_words}
    best = None
    for start in range(len(words)):
        for end in range(start + 1, min(len(words), start + max_words) + 1):
            phrase_words = words[start:end]
            phrase = " ".join(phrase_words).strip(" .,:;—")
            if not phrase or len(phrase) > max_length:
                continue
            content = [_word_key(word) for word in phrase_words if _word_key(word) not in STOP_WORDS]
            if not content:
                continue
            score = sum(2.4 if word in emphasis_keys else min(len(word), 9) / 9 for word in content)
            score += .16 * len(phrase_words) - .05 * start
            candidate = (score, len(phrase), -start, phrase)
            if best is None or candidate > best:
                best = candidate
    return best[3] if best else ""


def _balanced_lines(title, max_lines=2):
    parts = [part.strip() for part in re.split(r"\s*:\s*|\s+—\s+", title) if part.strip()]
    if 1 < len(parts) <= max_lines:
        return tuple(parts)
    words = title.split()
    if len(words) < 4:
        return (title,)
    target = len(title) / min(max_lines, 2)
    split = min(range(1, len(words)), key=lambda index: abs(len(" ".join(words[:index])) - target))
    return tuple(line for line in (" ".join(words[:split]), " ".join(words[split:])) if line)


def _display_treatment(title, emphasis_words, profile=None):
    words = title.split()
    emphasis = {_word_key(word) for word in emphasis_words}
    narrative = getattr(profile, "narrative_mode", "")
    energy = float(getattr(profile, "energy", 0.5) or 0.5)

    if 2 <= len(words) <= 3 and len(title) <= 34:
        emphasized_index = next(
            (index for index, word in enumerate(words) if _word_key(word) in emphasis),
            len(words) - 1,
        )
        if len(words) == 2:
            lines = (words[0], words[1])
        elif emphasized_index == 0:
            lines = (words[0], " ".join(words[1:]))
        else:
            lines = (" ".join(words[:emphasized_index]), " ".join(words[emphasized_index:]))
    else:
        lines = _balanced_lines(title, max_lines=3)

    dominant = max(
        range(len(lines)),
        key=lambda index: sum(
            1 for word in lines[index].split() if _word_key(word) in emphasis
        ) * 4 + len(lines[index]),
    )
    rendered = list(lines)
    if narrative in {"aggressive", "rhythmic_mechanical", "epic"} or energy > .76:
        rendered[dominant] = rendered[dominant].upper()
        strategy = "impact emphasis"
    elif narrative in {"intimate", "tragic"} and len(lines) > 1:
        rendered[dominant] = rendered[dominant].upper()
        strategy = "emotional contrast"
    else:
        strategy = "mixed-case hierarchy"
    weights = tuple(1.0 if index == dominant else .72 for index in range(len(rendered)))
    return tuple(rendered), weights, strategy


def _normalize_word_case(title):
    words = re.split(r"(\s+)", title)
    output = []
    word_index = 0
    for token in words:
        if not token or token.isspace():
            output.append(token)
            continue
        clean = token.strip(".,:;!?()[]")
        key = _word_key(clean)
        if clean.isupper() and len(clean) <= 4:
            rendered = token
        elif word_index and key in STOP_WORDS:
            rendered = token.lower()
        else:
            rendered = token[:1].upper() + token[1:]
        output.append(rendered)
        word_index += 1
    return "".join(output)


def _word_key(word):
    return re.sub(r"[^a-zа-яё0-9]+", "", str(word).lower())
