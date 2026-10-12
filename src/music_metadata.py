import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from audio_tags import read_metadata, read_id3, update_id3, probe_audio
from genre_classifier import GENRE_LABELS


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
DEFAULT_GENRES = list(dict.fromkeys([*GENRE_LABELS.values(), *DEFAULT_GENRES, 'OST', 'Nightcore', 'Slowed']))


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


def read_audio(audio_path, sample_rate=22050, start=0, seconds=9, cancel_event=None):
    """Decode only a bounded fragment; preserve its physical amplitude."""
    from genre_classifier import decode_fragment
    return decode_fragment(audio_path, start, seconds, sample_rate, cancel_event)


def keyword_genre_from_name(audio_path, allowed_genres):
    """Compatibility shim: filenames cannot establish a musical genre."""
    return None


def choose_allowed_genre(canonical_genre, allowed_genres):
    if not canonical_genre:
        return None
    aliases = {"rnb": "r&b", "hip hop": "hip hop"}
    def key(value):
        normalized = normalize_label(value)
        return aliases.get(normalized, normalized)
    return next((genre for genre in allowed_genres if key(genre) == key(canonical_genre)), None)


def estimate_genre(audio_path, allowed_genres, cancel_event=None):
    """Legacy string API backed by the actual local neural tagger."""
    from genre_classifier import classify_genre
    return classify_genre(audio_path, allowed_genres, cancel_event).tag


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


def is_lyrics_key(key):
    key = str(key).casefold().replace(' ', '').replace('_', '').replace('-', '')
    return key in {'uslt', 'sylt'} or key.startswith(('lyrics', 'unsyncedlyrics', 'syncedlyrics', 'sonicforgelyrics'))


def lyrics_snapshot(path):
    """Keep exact MP3 lyric frames, including timing/language and custom tags."""
    if Path(path).suffix.lower() == '.mp3':
        version, _, frames = read_id3(path)
        protected = [f for f in frames if f.name in ('USLT', 'SYLT')
                     or (f.name == 'TXXX' and is_lyrics_key(f.description))]
        return version, protected, {}
    tags = probe_audio(path)['metadata']
    return None, [], {key: value for key, value in tags.items() if is_lyrics_key(key)}


def restore_lyrics(path, snapshot):
    version, frames, _ = snapshot
    if version is None:
        actual = lyrics_snapshot(path)[2]
        expected = {key.casefold(): value for key, value in snapshot[2].items()}
        found = {key.casefold(): value for key, value in actual.items()}
        if expected != found:
            raise RuntimeError('Container could not preserve embedded lyrics; original file retained.')
        return
    _, _, current = read_id3(path)
    custom = tuple(f.description for f in current if f.name == 'TXXX' and is_lyrics_key(f.description))
    if frames or any(f.name in ('USLT', 'SYLT') for f in current) or custom:
        update_id3(path, frames, remove_names=('USLT', 'SYLT'), remove_custom=custom, target_version=version)


def write_metadata(
    audio_path,
    title,
    genre,
    dry_run=False,
    extra_metadata=None,
    overwrite_all_metadata=False,
    preserve_lyrics=False,
):
    audio_path = Path(audio_path)
    temp_path = audio_path.with_name(f"{audio_path.stem}.metadata_tmp{audio_path.suffix}")
    extra_metadata = normalized_extra_metadata(extra_metadata)
    if preserve_lyrics:
        extra_metadata = {key: value for key, value in extra_metadata.items() if not is_lyrics_key(key)}
    if dry_run:
        extras = ", ".join(f"{key}={value!r}" for key, value in extra_metadata.items())
        extras_text = f", {extras}" if extras else ""
        mode = "replace all metadata" if overwrite_all_metadata else "preserve other metadata"
        print(f"Dry run: {audio_path.name} -> title={title!r}, genre={genre!r}{extras_text} ({mode})")
        return

    snapshot = lyrics_snapshot(audio_path) if preserve_lyrics else None

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
    ]
    # None means do not touch a genre field; empty string is explicit removal.
    if genre is not None:
        command.extend(["-metadata", f"genre={genre}"])
    if overwrite_all_metadata:
        command.extend(
            ["-map_metadata:s", "-1", "-map_chapters", "-1", "-fflags", "+bitexact"]
        )
    for key, value in extra_metadata.items():
        command.extend(["-metadata", f"{key}={value}"])
    if snapshot:
        for key, value in snapshot[2].items():
            command.extend(['-metadata', f'{key}={value}'])
    if audio_path.suffix.lower() == ".mp3":
        command.extend(["-id3v2_version", str(snapshot[0] if snapshot else 3)])
    command.append(str(temp_path))
    try:
        run(command)
        if snapshot:
            restore_lyrics(temp_path, snapshot)
        temp_path.replace(audio_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def clear_metadata(audio_path, dry_run=False, preserve_lyrics=False):
    audio_path = Path(audio_path)
    if dry_run:
        print(f"Dry run: clear all metadata from {audio_path.name}")
        return

    temp_path = audio_path.with_name(f"{audio_path.stem}.metadata_tmp{audio_path.suffix}")
    snapshot = lyrics_snapshot(audio_path) if preserve_lyrics else None
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
        command.extend(["-id3v2_version", str(snapshot[0] if snapshot else 3)])
    if snapshot:
        for key, value in snapshot[2].items():
            command.extend(['-metadata', f'{key}={value}'])
    command.append(str(temp_path))
    try:
        run(command)
        if snapshot:
            restore_lyrics(temp_path, snapshot)
        temp_path.replace(audio_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def clear_music_metadata(source, dry_run=False, cancel_event=None, preserve_lyrics=False):
    source_path = Path(source).resolve()
    files = audio_files(source_path)
    if not files:
        raise RuntimeError(f"No supported audio files found in {source_path}")
    for index, audio_path in enumerate(files, start=1):
        check_cancelled(cancel_event)
        print(f"[{index}/{len(files)}] Clear metadata: {audio_path.name}")
        clear_metadata(audio_path, dry_run=dry_run, preserve_lyrics=preserve_lyrics)
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
    genre_progress=None,
    preserve_lyrics=False,
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
        existing_genre = existing_tags.get("genre", "")
        if existing_genre and not overwrite_genre and not overwrite_all_metadata:
            genre = existing_genre
            action = "keep existing genre"
        else:
            if genre_override:
                genre = genre_override
            else:
                from genre_classifier import classify_genre
                result = classify_genre(audio_path, allowed_genres, cancel_event)
                if genre_progress:
                    genre_progress(audio_path, result)
                else:
                    alternatives = ', '.join(f'{c.genre}: {c.score:.3f} (support {c.support:.0%})'
                                             for c in result.alternatives)
                    print(f'Genre analysis: {audio_path.name}: {result.tag or "undefined"}; '
                          f'scores (uncalibrated): {alternatives}; context: {", ".join(result.context)}; '
                          f'{result.reason}')
                if manual:
                    genre = choose_genre_interactively(audio_path, allowed_genres, result.tag)
                else:
                    # Abstention does not erase an existing tag even when an
                    # overwrite was requested: there is no reliable replacement.
                    genre = result.tag or existing_genre or None
            action = "write genre" if not existing_genre else "overwrite genre"

        extra_metadata = normalized_extra_metadata(extra_metadata)
        extras = ", ".join(f"{key}={value!r}" for key, value in extra_metadata.items())
        extras_text = f", {extras}" if extras else ""
        print(f"[{index}/{len(files)}] Metadata: {audio_path.name} -> title={title!r}, genre={genre!r}{extras_text} ({action})")
        check_cancelled(cancel_event)
        try:
            write_metadata(
                audio_path,
                title,
                genre,
                dry_run=dry_run,
                extra_metadata=extra_metadata,
                overwrite_all_metadata=overwrite_all_metadata,
                preserve_lyrics=preserve_lyrics,
            )
        except subprocess.CalledProcessError as exc:
            # A malformed container cannot be retagged; keep its original and
            # continue the folder instead of abandoning subsequent songs.
            print(f'Metadata skipped: {audio_path.name}: decoder/remux error {exc.returncode}')

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
