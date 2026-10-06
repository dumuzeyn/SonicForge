import argparse
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import music2picture
import music_metadata


SCRIPT_DIR = Path(__file__).resolve().parent

# PyCharm / direct Python run settings.
# Set RUN_FROM_CODE = True, edit the paths below, then press Run.
RUN_FROM_CODE = False
CODE_SOURCE = r"C:\Path\To\MusicFolder"
CODE_OUTPUT = r"C:\Path\To\ProcessedMusic"
CODE_GENRE = None
CODE_INTEGRATED_LUFS = -14.0
CODE_TRUE_PEAK = -1.5
CODE_LRA = 11.0
CODE_FINAL_GAIN = 1.0
CODE_DENOISE = False
CODE_DENOISE_MODE = "auto"
CODE_DENOISE_STRENGTH = 4.0
CODE_LIMITER = True
CODE_BASS_GAIN = 0.0
CODE_MID_GAIN = 0.0
CODE_TREBLE_GAIN = 0.0
CODE_HIGHPASS_HZ = 0.0
CODE_LOWPASS_HZ = 0.0
CODE_STEREO_WIDTH = 1.0
CODE_COMPRESSOR = False
CODE_COMPRESSOR_THRESHOLD = -18.0
CODE_COMPRESSOR_RATIO = 3.0
CODE_COMPRESSOR_ATTACK = 20.0
CODE_COMPRESSOR_RELEASE = 250.0
CODE_COMPRESSOR_MAKEUP = 0.0
CODE_PITCH_SEMITONES = 0.0
CODE_PLAYBACK_SPEED = 1.0
CODE_REVERB_MIX = 0.0
CODE_FADE_IN = 0.0
CODE_FADE_OUT = 0.0
CODE_SAMPLE_RATE = "source"
CODE_CHANNELS = "source"
CODE_MP3_QUALITY = "maximum"
CODE_OVERWRITE_GENRE = False
CODE_OVERWRITE_ALL_METADATA = False
CODE_EXTRA_METADATA = {}
CODE_COVER_SEED = None
CODE_COVER_SIZE = 1000
CODE_COVER_TEXT_MODE = "title_artist"
CODE_COVER_MOOD = "auto"
CODE_COVER_STYLE = "current"
CODE_EMBED_COVER = True
CODE_CHANGE_COVER = True
CODE_LYRICS_FORMAT = "txt"
CODE_LYRICS_LANGUAGE = "auto"
CODE_OVERWRITE_LYRICS = False


def load_python_file(name, filename):
    module_path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalize_music_file = load_python_file("normalize_music_file", "Normalize-Music.py")


def check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Processing was cancelled.")


def ask_path(prompt):
    while True:
        value = input(prompt).strip().strip('"')
        if value:
            return value
        print("Please enter a path.")


def ask_settings():
    source = ask_path("Source folder or audio file: ")
    output = ask_path("Output folder: ")
    genre = input("Genre for songs without genre, or Enter for auto-detect: ").strip()
    return source, output, genre or None


def publish_processed_tree(staging_path, output_path):
    output_path.mkdir(parents=True, exist_ok=True)
    for source_item in staging_path.rglob("*"):
        relative = source_item.relative_to(staging_path)
        target_item = output_path / relative
        if source_item.is_dir():
            target_item.mkdir(parents=True, exist_ok=True)
            continue

        target_item.parent.mkdir(parents=True, exist_ok=True)
        if target_item.exists():
            target_item.unlink()
        shutil.move(str(source_item), str(target_item))


def stage_source_files(source_path, staging_path, cancel_event=None):
    source_path = source_path.resolve()
    files = music_metadata.audio_files(source_path)
    if not files:
        raise RuntimeError(f"No supported audio files found in {source_path}")

    source_base = source_path.parent if source_path.is_file() else source_path
    for audio_path in files:
        check_cancelled(cancel_event)
        target = staging_path / audio_path.relative_to(source_base)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audio_path, target)


def process_music(
    source,
    output,
    genre=None,
    integrated_lufs=-14.0,
    true_peak=-1.5,
    lra=11.0,
    final_gain=1.0,
    denoise=False,
    denoise_mode="auto",
    denoise_strength=4.0,
    limiter=True,
    bass_gain=0.0,
    mid_gain=0.0,
    treble_gain=0.0,
    highpass_hz=0.0,
    lowpass_hz=0.0,
    stereo_width=1.0,
    compressor=False,
    compressor_threshold=-18.0,
    compressor_ratio=3.0,
    compressor_attack=20.0,
    compressor_release=250.0,
    compressor_makeup=0.0,
    pitch_semitones=0.0,
    playback_speed=1.0,
    reverb_mix=0.0,
    fade_in=0.0,
    fade_out=0.0,
    sample_rate="source",
    channels="source",
    mp3_quality="maximum",
    overwrite_genre=False,
    overwrite_all_metadata=False,
    extra_metadata=None,
    cover_seed=None,
    cover_size=1000,
    cover_text_mode="title_artist",
    cover_mood="auto",
    embed_cover=True,
    change_cover=True,
    process_steps=None,
    metadata_mode="update",
    title=None,
    cover_lyrics_text="",
    lyrics_format="txt",
    lyrics_language="auto",
    overwrite_lyrics=False,
    lyrics_service=None,
    cover_style="current",
    cancel_event=None,
    use_lyrics_for_cover=True,
    lyrics_progress=None,
    custom_cover_path=None,
):
    from security import validate_output_directory, validate_source

    source_path, _validated_files = validate_source(source)
    output_path = validate_output_directory(source_path, output)
    if not 128 <= int(cover_size) <= 4096:
        raise ValueError("cover_size must be between 128 and 4096 pixels")
    output_parent = output_path.resolve().parent
    output_parent.mkdir(parents=True, exist_ok=True)

    steps = set(process_steps or {"audio", "metadata", "lyrics", "cover"})
    allowed_steps = {"audio", "metadata", "lyrics", "cover"}
    if not steps or not steps.issubset(allowed_steps):
        raise ValueError("process_steps must contain audio, metadata, lyrics, and/or cover")

    check_cancelled(cancel_event)
    lyrics_lookup = {}
    if "cover" in steps and use_lyrics_for_cover and not custom_cover_path:
        from lyrics_engine import LyricsService

        service = LyricsService(metadata_reader=music_metadata.read_all_metadata)
        source_base = source_path.parent if source_path.is_file() else source_path
        for original_audio in music_metadata.audio_files(source_path):
            existing = service.load_existing(original_audio)
            if existing and existing.text.strip():
                relative_key = str(original_audio.relative_to(source_base).with_suffix("")).replace("\\", "/")
                lyrics_lookup[relative_key] = existing.text
        if cover_lyrics_text and source_path.is_file():
            lyrics_lookup[source_path.stem] = cover_lyrics_text.strip()

    with tempfile.TemporaryDirectory(prefix="musicpolisher_", dir=output_parent) as temp_dir:
        staging_path = Path(temp_dir) / "processed"
        generated_covers_path = Path(temp_dir) / "generated_covers"
        covers_path = staging_path / "covers"

        check_cancelled(cancel_event)
        if "cover" in steps and change_cover:
            print("\nСоздание обложек для выбранных песен")
            if not custom_cover_path or embed_cover:
                music2picture.require_ffmpeg()
            if custom_cover_path:
                music2picture.make_custom_covers(
                    source_path, custom_cover_path, generated_covers_path,
                    size=cover_size, cancel_event=cancel_event,
                )
            else:
                music2picture.make_covers(
                    source_path,
                    generated_covers_path,
                    size=cover_size,
                    embed=False,
                    seed=cover_seed,
                    lyrics_text=cover_lyrics_text if use_lyrics_for_cover else "",
                    use_lyrics_for_cover=use_lyrics_for_cover,
                    lyrics_lookup=lyrics_lookup,
                    text_mode=cover_text_mode,
                    mood_override=cover_mood,
                    style=cover_style,
                    cancel_event=cancel_event,
                )

        check_cancelled(cancel_event)
        if "audio" in steps:
            print("\nОбработка звука")
            normalize_music_file.normalize_music(
                source_path,
                staging_path,
                integrated_lufs=integrated_lufs,
                true_peak=true_peak,
                lra=lra,
                final_gain=final_gain,
                denoise=denoise,
                denoise_mode=denoise_mode,
                denoise_strength=denoise_strength,
                limiter=limiter,
                bass_gain=bass_gain,
                mid_gain=mid_gain,
                treble_gain=treble_gain,
                highpass_hz=highpass_hz,
                lowpass_hz=lowpass_hz,
                stereo_width=stereo_width,
                compressor=compressor,
                compressor_threshold=compressor_threshold,
                compressor_ratio=compressor_ratio,
                compressor_attack=compressor_attack,
                compressor_release=compressor_release,
                compressor_makeup=compressor_makeup,
                pitch_semitones=pitch_semitones,
                playback_speed=playback_speed,
                reverb_mix=reverb_mix,
                fade_in=fade_in,
                fade_out=fade_out,
                sample_rate=sample_rate,
                channels=channels,
                mp3_quality=mp3_quality,
                cancel_event=cancel_event,
            )
        else:
            print("\nПодготовка рабочей копии аудио")
            stage_source_files(
                source_path,
                staging_path,
                cancel_event=cancel_event,
            )

        check_cancelled(cancel_event)
        if "metadata" in steps and metadata_mode == "clear":
            print("\nОчистка метаданных")
            music_metadata.require_ffmpeg()
            music_metadata.clear_music_metadata(
                staging_path,
                cancel_event=cancel_event,
            )
        elif "metadata" in steps:
            print("\nЗапись выбранных метаданных")
            music_metadata.require_ffmpeg()
            music_metadata.update_music_metadata(
                staging_path,
                genre_override=genre,
                overwrite_genre=overwrite_genre,
                overwrite_all_metadata=(
                    overwrite_all_metadata or metadata_mode == "replace"
                ),
                extra_metadata=extra_metadata,
                title_override=title,
                cancel_event=cancel_event,
            )

        check_cancelled(cancel_event)
        if "cover" in steps and change_cover:
            print("\nДобавление обложек в готовые файлы")
            music2picture.apply_generated_covers(
                staging_path,
                generated_covers_path,
                covers_path,
                size=cover_size,
                embed=embed_cover,
                cancel_event=cancel_event,
            )
        elif "cover" in steps:
            print("\nОбложки оставлены без изменений")

        check_cancelled(cancel_event)
        if "lyrics" in steps:
            print("\nРаспознавание текста песен")
            from lyrics_engine import recognize_batch

            lyrics_lookup = recognize_batch(
                source_path,
                staging_path,
                output=output_path,
                service=lyrics_service,
                export_format=lyrics_format,
                overwrite=overwrite_lyrics,
                language=lyrics_language,
                cancel_event=cancel_event,
                progress=lyrics_progress,
            )

        check_cancelled(cancel_event)
        print("\nСохранение готовых файлов")
        publish_processed_tree(staging_path, output_path)

    print(f"\nГотово. Песни сохранены: {output_path.resolve()}")
    if "cover" in steps and change_cover:
        print(f"Обложки сохранены: {(output_path / 'covers').resolve()}")


def main():
    parser = argparse.ArgumentParser(
        description="All-in-one music processor: normalize audio, clean metadata, create and embed covers."
    )
    parser.add_argument("--source", help="Folder with source songs or one audio file.")
    parser.add_argument("--output", help="Folder where processed songs and covers will be saved.")
    parser.add_argument("--genre", help="Set genre for songs that do not already have genre. Omit for auto-detect.")
    parser.add_argument("--title", help="Set title metadata. For folders, the same title is applied to every file.")
    parser.add_argument("--artist", help="Set artist metadata.")
    parser.add_argument("--album", help="Set album metadata.")
    parser.add_argument("--album-artist", help="Set album artist metadata.")
    parser.add_argument("--composer", help="Set composer metadata.")
    parser.add_argument("--date", help="Set date/year metadata.")
    parser.add_argument("--track", help="Set track metadata.")
    parser.add_argument("--comment", help="Set comment metadata.")
    parser.add_argument("--integrated-lufs", type=float, default=-14.0, help="Target integrated loudness.")
    parser.add_argument("--true-peak", type=float, default=-1.5, help="Target true peak.")
    parser.add_argument("--lra", type=float, default=11.0, help="Target loudness range.")
    parser.add_argument("--final-gain", type=float, default=1.0, help="Expert gain after loudnorm.")
    parser.add_argument("--denoise", dest="denoise_mode", action="store_const", const="manual")
    parser.add_argument("--no-denoise", dest="denoise_mode", action="store_const", const="off")
    parser.add_argument("--denoise-mode", choices=("off", "auto", "manual"), default="auto")
    parser.add_argument("--denoise-strength", type=float, default=4.0, help="Gentle denoise amount in dB.")
    parser.add_argument("--limiter", dest="limiter", action="store_true", default=True, help="Use final limiter. Enabled by default.")
    parser.add_argument("--no-limiter", dest="limiter", action="store_false", help="Disable final limiter.")
    parser.add_argument("--bass-gain", type=float, default=0.0, help="Bass EQ gain in dB.")
    parser.add_argument("--mid-gain", type=float, default=0.0, help="Mid EQ gain in dB.")
    parser.add_argument("--treble-gain", type=float, default=0.0, help="Treble EQ gain in dB.")
    parser.add_argument("--highpass-hz", type=float, default=0.0, help="Low-frequency cutoff; 0 disables it.")
    parser.add_argument("--lowpass-hz", type=float, default=0.0, help="High-frequency cutoff; 0 disables it.")
    parser.add_argument("--stereo-width", type=float, default=1.0, help="Stereo width: 0 is mono, 1 unchanged, 2 wide.")
    parser.add_argument("--compressor", action="store_true", help="Enable dynamic compressor.")
    parser.add_argument("--compressor-threshold", type=float, default=-18.0)
    parser.add_argument("--compressor-ratio", type=float, default=3.0)
    parser.add_argument("--compressor-attack", type=float, default=20.0)
    parser.add_argument("--compressor-release", type=float, default=250.0)
    parser.add_argument("--compressor-makeup", type=float, default=0.0)
    parser.add_argument("--pitch-semitones", type=float, default=0.0)
    parser.add_argument("--playback-speed", type=float, default=1.0)
    parser.add_argument("--reverb-mix", type=float, default=0.0)
    parser.add_argument("--fade-in", type=float, default=0.0)
    parser.add_argument("--fade-out", type=float, default=0.0)
    parser.add_argument("--sample-rate", choices=("source", "44100", "48000"), default="source")
    parser.add_argument("--channels", choices=("source", "1", "2"), default="source")
    parser.add_argument("--mp3-quality", choices=("maximum", "high", "medium"), default="maximum")
    parser.add_argument("--overwrite-genre", action="store_true", help="Replace existing genre tags. Default keeps them.")
    parser.add_argument("--overwrite-all-metadata", action="store_true", help="Clear existing metadata before writing selected fields.")
    parser.add_argument("--cover-seed", type=int, help="Use an integer for repeatable generated covers.")
    parser.add_argument("--cover-size", type=int, default=1000, help="Generated cover size in pixels.")
    parser.add_argument("--cover-text", choices=("title_artist", "title", "none"), default="title_artist")
    parser.add_argument("--cover-mood", choices=("auto", "calm", "melancholic", "energetic", "intense", "romantic"), default="auto")
    parser.add_argument("--cover-style", choices=(
        "current", "current_legacy_colors", "blend", "legacy_current_colors", "legacy",
    ), default="current")
    parser.add_argument("--embed-cover", dest="embed_cover", action="store_true", default=True, help="Embed generated cover into MP3. Enabled by default.")
    parser.add_argument("--no-embed-cover", dest="embed_cover", action="store_false", help="Do not embed generated cover.")
    parser.add_argument("--change-cover", dest="change_cover", action="store_true", default=True, help="Generate and embed a new cover. Enabled by default.")
    parser.add_argument("--no-change-cover", dest="change_cover", action="store_false", help="Do not generate or embed a new cover.")
    parser.add_argument("--lyrics-format", choices=("txt", "lrc"), default="txt")
    parser.add_argument("--lyrics-language", default="auto", help="auto, ru, en, other_en, other_ru, or an ISO language code. Other modes approximate sounds in English/Russian letters for other detected languages.")
    parser.add_argument("--overwrite-lyrics", action="store_true")
    parser.add_argument("--steps", choices=["all", "audio", "metadata", "lyrics", "cover"], default="all", help="Choose one processing stage or run all stages.")
    parser.add_argument("--metadata-mode", choices=["update", "replace", "clear"], default="update", help="Preserve, replace, or clear metadata.")
    args = parser.parse_args()

    if args.source and args.output:
        source, output, genre = args.source, args.output, args.genre
    else:
        source, output, genre = ask_settings()

    process_music(
        source,
        output,
        genre=genre,
        title=args.title,
        integrated_lufs=args.integrated_lufs,
        true_peak=args.true_peak,
        lra=args.lra,
        final_gain=args.final_gain,
        denoise=args.denoise_mode == "manual",
        denoise_mode=args.denoise_mode,
        denoise_strength=args.denoise_strength,
        limiter=args.limiter,
        bass_gain=args.bass_gain,
        mid_gain=args.mid_gain,
        treble_gain=args.treble_gain,
        highpass_hz=args.highpass_hz,
        lowpass_hz=args.lowpass_hz,
        stereo_width=args.stereo_width,
        compressor=args.compressor,
        compressor_threshold=args.compressor_threshold,
        compressor_ratio=args.compressor_ratio,
        compressor_attack=args.compressor_attack,
        compressor_release=args.compressor_release,
        compressor_makeup=args.compressor_makeup,
        pitch_semitones=args.pitch_semitones,
        playback_speed=args.playback_speed,
        reverb_mix=args.reverb_mix,
        fade_in=args.fade_in,
        fade_out=args.fade_out,
        sample_rate=args.sample_rate,
        channels=args.channels,
        mp3_quality=args.mp3_quality,
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
        cover_seed=args.cover_seed,
        cover_size=args.cover_size,
        cover_text_mode=args.cover_text,
        cover_mood=args.cover_mood,
        cover_style=args.cover_style,
        embed_cover=args.embed_cover,
        change_cover=args.change_cover,
        process_steps=None if args.steps == "all" else {args.steps},
        metadata_mode=args.metadata_mode,
        lyrics_format=args.lyrics_format,
        lyrics_language=args.lyrics_language,
        overwrite_lyrics=args.overwrite_lyrics,
    )


def run_from_code_settings():
    process_music(
        CODE_SOURCE,
        CODE_OUTPUT,
        genre=CODE_GENRE,
        integrated_lufs=CODE_INTEGRATED_LUFS,
        true_peak=CODE_TRUE_PEAK,
        lra=CODE_LRA,
        final_gain=CODE_FINAL_GAIN,
        denoise=CODE_DENOISE,
        denoise_mode=CODE_DENOISE_MODE,
        denoise_strength=CODE_DENOISE_STRENGTH,
        limiter=CODE_LIMITER,
        bass_gain=CODE_BASS_GAIN,
        mid_gain=CODE_MID_GAIN,
        treble_gain=CODE_TREBLE_GAIN,
        highpass_hz=CODE_HIGHPASS_HZ,
        lowpass_hz=CODE_LOWPASS_HZ,
        stereo_width=CODE_STEREO_WIDTH,
        compressor=CODE_COMPRESSOR,
        compressor_threshold=CODE_COMPRESSOR_THRESHOLD,
        compressor_ratio=CODE_COMPRESSOR_RATIO,
        compressor_attack=CODE_COMPRESSOR_ATTACK,
        compressor_release=CODE_COMPRESSOR_RELEASE,
        compressor_makeup=CODE_COMPRESSOR_MAKEUP,
        pitch_semitones=CODE_PITCH_SEMITONES,
        playback_speed=CODE_PLAYBACK_SPEED,
        reverb_mix=CODE_REVERB_MIX,
        fade_in=CODE_FADE_IN,
        fade_out=CODE_FADE_OUT,
        sample_rate=CODE_SAMPLE_RATE,
        channels=CODE_CHANNELS,
        mp3_quality=CODE_MP3_QUALITY,
        overwrite_genre=CODE_OVERWRITE_GENRE,
        overwrite_all_metadata=CODE_OVERWRITE_ALL_METADATA,
        extra_metadata=CODE_EXTRA_METADATA,
        cover_seed=CODE_COVER_SEED,
        cover_size=CODE_COVER_SIZE,
        cover_text_mode=CODE_COVER_TEXT_MODE,
        cover_mood=CODE_COVER_MOOD,
        cover_style=CODE_COVER_STYLE,
        embed_cover=CODE_EMBED_COVER,
        change_cover=CODE_CHANGE_COVER,
        lyrics_format=CODE_LYRICS_FORMAT,
        lyrics_language=CODE_LYRICS_LANGUAGE,
        overwrite_lyrics=CODE_OVERWRITE_LYRICS,
    )


if __name__ == "__main__":
    try:
        if RUN_FROM_CODE:
            run_from_code_settings()
        else:
            main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
