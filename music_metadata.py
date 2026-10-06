import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from audio_tags import read_metadata


AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
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


def require_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg was not found in PATH.")


def run(command):
    subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **SUBPROCESS_STARTUP_KWARGS,
    )


def check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Processing was cancelled.")


def audio_files(source):
    from audio_paths import find_audio_files
    return find_audio_files(source, AUDIO_EXTENSIONS)


def clean_stem(path):
    return Path(path).stem.rstrip(". ")


def normalize_label(value):
    return " ".join(str(value).lower().replace("_", " ").replace("-", " ").split())


def load_genres(genres=None, genres_file=None):
    loaded = []

    if genres_file:
        path = Path(genres_file)
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                loaded.append(value)

    if genres:
        loaded.extend(part.strip() for part in genres.split(",") if part.strip())

    if not loaded:
        loaded = DEFAULT_GENRES

    unique = []
    seen = set()
    for genre in loaded:
        key = normalize_label(genre)
        if key and key not in seen:
            seen.add(key)
            unique.append(genre)
    return unique


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


def read_existing_genre(audio_path):
    return read_all_metadata(audio_path).get("genre", "")


def read_all_metadata(audio_path):
    return read_metadata(audio_path)


def normalized_extra_metadata(extra_metadata=None):
    if not extra_metadata:
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in extra_metadata.items()
        if str(key).strip() and str(value).strip()
    }


def write_metadata(
    audio_path,
    title,
    genre,
    dry_run=False,
    extra_metadata=None,
    overwrite_all_metadata=False,
):
    audio_path = Path(audio_path)
    temp_path = audio_path.with_name(f"{audio_path.stem}.metadata_tmp{audio_path.suffix}")
    extra_metadata = normalized_extra_metadata(extra_metadata)
    if dry_run:
        extras = ", ".join(f"{key}={value!r}" for key, value in extra_metadata.items())
        extras_text = f", {extras}" if extras else ""
        mode = "replace all metadata" if overwrite_all_metadata else "preserve other metadata"
        print(f"Dry run: {audio_path.name} -> title={title!r}, genre={genre!r}{extras_text} ({mode})")
        return

    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(audio_path),
        "-map",
        "0",
        "-c",
        "copy",
        "-map_metadata",
        "-1" if overwrite_all_metadata else "0",
        "-metadata",
        f"title={title}",
        "-metadata",
        f"genre={genre}",
    ]
    if overwrite_all_metadata:
        command.extend(
            ["-map_metadata:s", "-1", "-map_chapters", "-1", "-fflags", "+bitexact"]
        )
    for key, value in extra_metadata.items():
        command.extend(["-metadata", f"{key}={value}"])
    if audio_path.suffix.lower() == ".mp3":
        command.extend(["-id3v2_version", "3"])
    command.append(str(temp_path))
    run(command)
    temp_path.replace(audio_path)


def clear_metadata(audio_path, dry_run=False):
    audio_path = Path(audio_path)
    if dry_run:
        print(f"Dry run: clear all metadata from {audio_path.name}")
        return

    temp_path = audio_path.with_name(f"{audio_path.stem}.metadata_tmp{audio_path.suffix}")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(audio_path),
        "-map",
        "0",
        "-c",
        "copy",
        "-map_metadata",
        "-1",
        "-map_metadata:s",
        "-1",
        "-map_chapters",
        "-1",
        "-fflags",
        "+bitexact",
    ]
    if audio_path.suffix.lower() == ".mp3":
        command.extend(["-id3v2_version", "3"])
    command.append(str(temp_path))
    run(command)
    temp_path.replace(audio_path)


def clear_music_metadata(source, dry_run=False, cancel_event=None):
    source_path = Path(source).resolve()
    files = audio_files(source_path)
    if not files:
        raise RuntimeError(f"No supported audio files found in {source_path}")
    for index, audio_path in enumerate(files, start=1):
        check_cancelled(cancel_event)
        print(f"[{index}/{len(files)}] Clear metadata: {audio_path.name}")
        clear_metadata(audio_path, dry_run=dry_run)
    check_cancelled(cancel_event)
    print("Metadata cleanup finished.")


def choose_files_interactively(files):
    print("Songs:")
    for index, audio_path in enumerate(files, start=1):
        print(f"  {index}. {audio_path.name}")

    while True:
        answer = input("Choose song numbers, comma-separated, or press Enter for all: ").strip()
        if not answer:
            return files

        try:
            selected = []
            for part in answer.split(","):
                number = int(part.strip())
                if number < 1 or number > len(files):
                    raise ValueError
                selected.append(files[number - 1])
        except ValueError:
            print("Please enter numbers from the list, for example: 1,3,5")
            continue

        unique = []
        seen = set()
        for audio_path in selected:
            if audio_path not in seen:
                seen.add(audio_path)
                unique.append(audio_path)
        return unique


def choose_genre_interactively(audio_path, allowed_genres, suggested_genre):
    print(f"\nSong: {audio_path.name}")
    print(f"Suggested genre: {suggested_genre}")
    for index, genre in enumerate(allowed_genres, start=1):
        print(f"  {index}. {genre}")

    while True:
        answer = input("Choose genre number, type custom genre, or press Enter for suggested: ").strip()
        if not answer:
            return suggested_genre
        if answer.isdigit():
            number = int(answer)
            if 1 <= number <= len(allowed_genres):
                return allowed_genres[number - 1]
            print("Please enter a valid genre number.")
            continue
        return answer


def update_music_metadata(
    source,
    genres=None,
    genres_file=None,
    dry_run=False,
    manual=False,
    select=False,
    genre_override=None,
    overwrite_genre=False,
    extra_metadata=None,
    overwrite_all_metadata=False,
    title_override=None,
    cancel_event=None,
):
    source_path = Path(source).resolve()
    files = audio_files(source_path)
    allowed_genres = load_genres(genres, genres_file)

    if not files:
        print(f"No supported audio files found in {source_path}")
        return

    if genre_override:
        genre_override = genre_override.strip()
        if genre_override and normalize_label(genre_override) not in {normalize_label(genre) for genre in allowed_genres}:
            allowed_genres.append(genre_override)

    if select and len(files) > 1:
        files = choose_files_interactively(files)

    print(f"Allowed genres: {', '.join(allowed_genres)}")
    for index, audio_path in enumerate(files, start=1):
        check_cancelled(cancel_event)
        existing_tags = read_all_metadata(audio_path)
        if title_override:
            title = str(title_override).strip()
        elif not overwrite_all_metadata and existing_tags.get("title"):
            title = existing_tags["title"]
        else:
            title = clean_stem(audio_path)
        existing_genre = read_existing_genre(audio_path)
        if existing_genre and not overwrite_genre and not overwrite_all_metadata:
            genre = existing_genre
            action = "keep existing genre"
        else:
            suggested_genre = estimate_genre(audio_path, allowed_genres)
            if genre_override:
                genre = genre_override
            elif manual:
                genre = choose_genre_interactively(audio_path, allowed_genres, suggested_genre)
            else:
                genre = suggested_genre
            action = "write genre" if not existing_genre else "overwrite genre"

        extra_metadata = normalized_extra_metadata(extra_metadata)
        extras = ", ".join(f"{key}={value!r}" for key, value in extra_metadata.items())
        extras_text = f", {extras}" if extras else ""
        print(f"[{index}/{len(files)}] Metadata: {audio_path.name} -> title={title!r}, genre={genre!r}{extras_text} ({action})")
        write_metadata(
            audio_path,
            title,
            genre,
            dry_run=dry_run,
            extra_metadata=extra_metadata,
            overwrite_all_metadata=overwrite_all_metadata,
        )

    check_cancelled(cancel_event)
    print("Metadata update finished.")


def main():
    parser = argparse.ArgumentParser(description="Write title and genre metadata for one song or a folder.")
    parser.add_argument("--source", required=True, help="Audio file or folder with audio files.")
    parser.add_argument("--genres", help="Comma-separated custom genre list, for example: Pop,Rock,Techno")
    parser.add_argument("--genres-file", help="UTF-8 text file with one allowed genre per line.")
    parser.add_argument("--genre", help="Set this genre manually for all selected songs.")
    parser.add_argument("--artist", help="Set artist metadata. Empty means no artist is written.")
    parser.add_argument("--album", help="Set album metadata. Empty means no album is written.")
    parser.add_argument("--album-artist", help="Set album artist metadata. Empty means no album artist is written.")
    parser.add_argument("--composer", help="Set composer metadata. Empty means no composer is written.")
    parser.add_argument("--date", help="Set date/year metadata. Empty means no date is written.")
    parser.add_argument("--track", help="Set track metadata. Empty means no track number is written.")
    parser.add_argument("--comment", help="Set comment metadata. Empty means no comment is written.")
    parser.add_argument("--manual", action="store_true", help="Ask which genre to write for each song.")
    parser.add_argument("--select", action="store_true", help="Choose song numbers from the source folder before writing metadata.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without modifying audio files.")
    parser.add_argument("--overwrite-genre", action="store_true", help="Replace an existing genre tag. Without this, existing genre is preserved.")
    parser.add_argument("--overwrite-all-metadata", action="store_true", help="Clear existing metadata before writing the selected fields.")
    args = parser.parse_args()

    require_ffmpeg()
    update_music_metadata(
        args.source,
        genres=args.genres,
        genres_file=args.genres_file,
        dry_run=args.dry_run,
        manual=args.manual,
        select=args.select,
        genre_override=args.genre,
        overwrite_genre=args.overwrite_genre,
        overwrite_all_metadata=args.overwrite_all_metadata,
        extra_metadata={
            "artist": args.artist,
            "album": args.album,
            "album_artist": args.album_artist,
            "composer": args.composer,
            "date": args.date,
            "track": args.track,
            "comment": args.comment,
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
