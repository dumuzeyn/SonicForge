"""Frozen baseline from b79348d9811ccd6974a2c9befca527be3dc9744e; evaluation only."""
import subprocess
import sys
from pathlib import Path
import numpy as np
SUBPROCESS_STARTUP_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

DEFAULT_GENRES = [
    "Pop",
    "Rock",
    "Hip-Hop",
    "Electronic",
    "Dance",
    "House",
    "Techno",
    "Drum and Bass",
    "Ambient",
    "Classical",
    "Jazz",
    "Acoustic",
    "Folk",
    "R&B",
    "Reggae",
    "Metal",
    "Anime",
    "Edit",
]


GENRE_KEYWORDS = {
    "Pop": ["pop", "dance pop", "synthpop", "synth-pop"],
    "Rock": ["rock", "indie rock", "alternative"],
    "Hip-Hop": ["hip hop", "hip-hop", "rap", "trap"],
    "Electronic": ["electronic", "electronica", "edm"],
    "Dance": ["dance", "club"],
    "House": ["house", "deep house", "tech house"],
    "Techno": ["techno"],
    "Drum and Bass": ["drum and bass", "drum & bass", "dnb", "d&b", "jungle"],
    "Ambient": ["ambient", "atmospheric", "chill", "downtempo"],
    "Classical": ["classical", "classic", "orchestra", "piano"],
    "Jazz": ["jazz", "swing", "bebop"],
    "Acoustic": ["acoustic", "unplugged"],
    "Folk": ["folk"],
    "R&B": ["r&b", "rnb", "soul"],
    "Reggae": ["reggae", "dub"],
    "Metal": ["metal", "metalcore", "deathcore"],
    "Anime": ["anime", "opening", "ending", "ost", "op", "ed", "j-pop", "jrock", "j-rock"],
    "Edit": ["edit", "edits", "amv", "velocity", "slowed", "reverb", "sped up", "nightcore"],
}


def clean_stem(path):
    return Path(path).stem.rstrip(". ")


def normalize_label(value):
    return " ".join(str(value).lower().replace("_", " ").replace("-", " ").split())


def read_audio(audio_path, sample_rate=22050):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    raw = subprocess.check_output(command, **SUBPROCESS_STARTUP_KWARGS)
    data = np.frombuffer(raw, dtype=np.float32)
    if data.size == 0:
        raise RuntimeError(f"No audio data decoded from {audio_path}")
    peak = np.max(np.abs(data))
    return data / peak if peak > 0 else data


def stft_features(audio, n_fft=2048, hop=512):
    if audio.size < n_fft:
        audio = np.pad(audio, (0, n_fft - audio.size))
    frame_count = max(1, 1 + (audio.size - n_fft) // hop)
    usable = audio[: n_fft + hop * (frame_count - 1)]
    frames = np.lib.stride_tricks.sliding_window_view(usable, n_fft)[::hop]
    window = np.hanning(n_fft).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1)).T
    spectrum = np.log1p(spectrum)[:512]
    spectrum -= spectrum.min()
    if spectrum.max() > 0:
        spectrum /= spectrum.max()

    rms = np.sqrt(np.mean(frames * frames, axis=1))
    if rms.max() > 0:
        rms /= rms.max()

    bass = spectrum[:24].mean(axis=0)
    mids = spectrum[24:160].mean(axis=0)
    highs = spectrum[160:].mean(axis=0)
    centroid = (spectrum * np.arange(spectrum.shape[0])[:, None]).sum(axis=0) / (spectrum.sum(axis=0) + 1e-6)
    centroid /= max(1, spectrum.shape[0] - 1)
    return rms, bass, mids, highs, centroid


def estimate_bpm(rms, sample_rate=22050, hop=512):
    if rms.size < 16:
        return 120.0

    envelope = np.maximum(0, np.diff(rms, prepend=rms[0]))
    envelope -= envelope.mean()
    if np.max(np.abs(envelope)) > 0:
        envelope /= np.max(np.abs(envelope))

    frame_rate = sample_rate / hop
    min_lag = max(1, int(frame_rate * 60 / 240))
    max_lag = min(len(envelope) - 1, int(frame_rate * 60 / 30))
    if max_lag <= min_lag:
        return 120.0

    scores = [float(np.dot(envelope[:-lag], envelope[lag:])) for lag in range(min_lag, max_lag + 1)]
    best_lag = min_lag + int(np.argmax(scores))
    bpm = 60 * frame_rate / best_lag
    while bpm < 30:
        bpm *= 2
    while bpm > 240:
        bpm /= 2
    return float(np.clip(bpm, 30, 240))


def keyword_genre_from_name(audio_path, allowed_genres):
    text = normalize_label(clean_stem(audio_path))
    best_genre = None
    best_score = 0
    for genre in allowed_genres:
        candidates = [genre]
        for canonical, keywords in GENRE_KEYWORDS.items():
            if normalize_label(canonical) == normalize_label(genre):
                candidates.extend(keywords)

        score = 0
        for candidate in candidates:
            candidate_key = normalize_label(candidate)
            if candidate_key and candidate_key in text:
                score = max(score, len(candidate_key))
        if score > best_score:
            best_genre = genre
            best_score = score
    return best_genre


def choose_allowed_genre(canonical_genre, allowed_genres):
    canonical_key = normalize_label(canonical_genre)
    for genre in allowed_genres:
        if normalize_label(genre) == canonical_key:
            return genre

    canonical_keywords = [canonical_genre] + GENRE_KEYWORDS.get(canonical_genre, [])
    canonical_tokens = set()
    for keyword in canonical_keywords:
        canonical_tokens.update(normalize_label(keyword).split())

    best_genre = allowed_genres[0]
    best_score = -1
    for genre in allowed_genres:
        genre_tokens = set(normalize_label(genre).split())
        score = len(canonical_tokens & genre_tokens)
        for keyword in canonical_keywords:
            if normalize_label(keyword) in normalize_label(genre):
                score += 2
        if score > best_score:
            best_genre = genre
            best_score = score
    return best_genre


def estimate_genre(audio_path, allowed_genres):
    name_match = keyword_genre_from_name(audio_path, allowed_genres)
    if name_match:
        return name_match

    audio = read_audio(audio_path)
    rms, bass, mids, highs, centroid = stft_features(audio)
    bpm = estimate_bpm(rms)
    energy = float(np.mean(rms))
    low = float(np.mean(bass))
    mid = float(np.mean(mids))
    high = float(np.mean(highs))
    brightness = float(np.mean(centroid))
    bass_ratio = low / (mid + high + 1e-6)
    high_ratio = high / (low + mid + 1e-6)

    scores = {genre: 0.0 for genre in DEFAULT_GENRES}
    scores["Ambient"] += (1.0 - energy) * 2.0 + (1.0 - min(bpm, 140) / 140.0)
    scores["Classical"] += (1.0 - energy) * 1.2 + high_ratio * 0.7 + (1.0 if bpm < 105 else 0.0)
    scores["Acoustic"] += mid * 1.4 + (1.0 - bass_ratio) * 0.8 + (1.0 if bpm < 135 else 0.0)
    scores["Folk"] += mid * 1.2 + (1.0 if 75 <= bpm <= 135 else 0.0)
    scores["Jazz"] += mid * 1.1 + high_ratio * 0.8 + (1.0 if 80 <= bpm <= 160 else 0.0)
    scores["R&B"] += bass_ratio * 1.0 + mid * 0.9 + (1.0 if 65 <= bpm <= 120 else 0.0)
    scores["Reggae"] += bass_ratio * 1.1 + (1.0 if 65 <= bpm <= 100 else 0.0)
    scores["Hip-Hop"] += bass_ratio * 1.4 + (1.0 if 70 <= bpm <= 115 else 0.0)
    scores["Pop"] += energy * 1.0 + mid * 0.8 + (1.0 if 90 <= bpm <= 145 else 0.0)
    scores["Rock"] += energy * 1.1 + mid * 1.1 + brightness * 0.7 + (1.0 if 95 <= bpm <= 170 else 0.0)
    scores["Metal"] += energy * 1.4 + brightness * 1.0 + (1.0 if bpm >= 130 else 0.0)
    scores["Electronic"] += bass_ratio * 1.0 + brightness * 0.8 + (1.0 if 95 <= bpm <= 155 else 0.0)
    scores["Dance"] += energy * 1.1 + bass_ratio * 1.1 + (1.3 if 115 <= bpm <= 135 else 0.0)
    scores["House"] += bass_ratio * 1.0 + (1.4 if 118 <= bpm <= 130 else 0.0)
    scores["Techno"] += energy * 1.0 + brightness * 0.8 + (1.4 if 125 <= bpm <= 150 else 0.0)
    scores["Drum and Bass"] += bass_ratio * 1.0 + brightness * 0.8 + (1.8 if 155 <= bpm <= 190 else 0.0)
    scores["Anime"] += high_ratio * 0.7 + mid * 0.8 + (1.0 if 120 <= bpm <= 180 else 0.0)
    scores["Edit"] += bass_ratio * 1.0 + energy * 0.8 + (1.0 if 80 <= bpm <= 170 else 0.0)

    canonical = max(scores, key=scores.get)
    return choose_allowed_genre(canonical, allowed_genres)
