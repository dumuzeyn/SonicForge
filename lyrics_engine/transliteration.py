"""Approximate sound spelling of native ASR text, never semantic translation."""
import re


_LATIN_TO_RUSSIAN = {
    "shch": "щ", "sch": "щ", "ch": "ч", "sh": "ш", "zh": "ж",
    "kh": "х", "gh": "г", "ts": "ц", "dz": "дз", "th": "т",
    "ph": "ф", "ya": "я", "yu": "ю", "yo": "ё", "ye": "е",
    **dict(zip("abcdefghijklmnopqrstuvwxyz", (
        "а", "б", "к", "д", "е", "ф", "г", "х", "и", "дж", "к", "л", "м",
        "н", "о", "п", "к", "р", "с", "т", "у", "в", "в", "кс", "й", "з",
    ))),
}
_RUSSIAN_PATTERN = re.compile("|".join(sorted(_LATIN_TO_RUSSIAN, key=len, reverse=True)), re.I)
_GEORGIAN_TO_RUSSIAN = dict(zip(
    "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ",
    ("а", "б", "г", "д", "э", "в", "з", "т", "и", "к", "л", "м", "н", "о", "п",
     "ж", "р", "с", "т", "у", "ф", "к", "г", "к", "ш", "ч", "ц", "дз", "ц", "ч", "х", "дж", "х"),
))


def _language_aware_latin(text, language):
    """Handle frequent pronunciation rules before the generic letter map."""
    rules = {
        "es": (
            (r"h", ""), (r"ll", "й"), (r"ny", "нь"), (r"j", "х"),
            (r"g(?=[ei])", "х"), (r"c(?=[ei])", "с"), (r"z", "с"),
            (r"qu(?=[ei])", "к"),
        ),
        "de": (
            (r"tsch", "ч"), (r"sch", "ш"), (r"ch", "х"), (r"z", "ц"),
            (r"w", "в"), (r"j", "й"), (r"v", "ф"), (r"ei", "ай"),
        ),
        "it": (
            (r"gli(?=[aeou])", "ль"), (r"gn", "нь"), (r"ch(?=[ei])", "к"),
            (r"c(?=[ei])", "ч"), (r"g(?=[ei])", "дж"), (r"qu", "ку"),
        ),
        "fr": (
            (r"eaux?\b", "о"), (r"ou", "у"), (r"oi", "уа"), (r"ch", "ш"),
            (r"j", "ж"), (r"g(?=[ei])", "ж"), (r"h", ""),
        ),
        "pt": (
            (r"nh", "нь"), (r"lh", "ль"), (r"ch", "ш"), (r"j", "ж"),
            (r"h", ""), (r"qu(?=[ei])", "к"),
        ),
    }
    value = text
    for pattern, replacement in rules.get((language or "").lower(), ()):
        value = re.sub(pattern, replacement, value, flags=re.I)
    return value


def sound_spelling(text, alphabet, language):
    from anyascii import anyascii
    if alphabet == "ru" and language == "ka":
        # Georgian has a phonemic alphabet. Avoid losing consonants via a
        # second generic Latin conversion, including ejective apostrophes.
        return "".join(_GEORGIAN_TO_RUSSIAN.get(c.lower(), c) for c in text)
    prepared = text.replace("ñ", "ny").replace("Ñ", "Ny") if language == "es" else text
    latin = anyascii(prepared)
    if alphabet == "en":
        return latin
    latin = _language_aware_latin(latin, language)
    def replace(match):
        value = _LATIN_TO_RUSSIAN[match.group().lower()]
        return value.capitalize() if match.group()[0].isupper() else value
    return _RUSSIAN_PATTERN.sub(replace, latin)
