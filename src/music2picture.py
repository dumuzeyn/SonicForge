from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageOps

from music2picture_v2 import (
    DEFAULT_PIPELINE,
    DescriptionStore,
    audio_files,
    generate_descriptions,
)
from music2picture_v2.renderer import GENERATOR_VERSION, artistic_parameters, deterministic_seed, customize_parameters
from music2picture_v2.variants import (
    LEGACY_COLOR_MODES, LEGACY_COMMIT, STYLES, STYLE_CURRENT, STYLE_LEGACY, STYLE_CUSTOM,
    render_legacy, render_variant,
)


STARTUP_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def require_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required")


def clean_stem(path):
    return Path(path).stem.replace("_normalized", "").strip()


def check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Processing was cancelled")


def make_cover(
    audio_path,
    output_path,
    size=1000,
    seed=None,
    lyrics_text="",
    text_mode="none",
    mood_override="auto",
    style=STYLE_CURRENT,
    legacy_color_mode="plasma",
    cancel_event=None,
    regenerate_description=False,
    preview=False,
    use_lyrics_for_cover=False,
    custom_cover_settings=None,
    **_compatibility,
):
    """Analyze one track, persist its text artifacts, then render its cover."""
    require_ffmpeg()
    path = Path(audio_path).resolve()
    output_path = Path(output_path)
    if style not in STYLES:
        raise ValueError(f"Unknown cover style: {style}")
    if style == STYLE_CUSTOM:
        from music2picture_v2.custom_style import CustomCoverSettings
        custom_cover_settings = CustomCoverSettings.parse(custom_cover_settings).to_dict()
    if legacy_color_mode not in LEGACY_COLOR_MODES:
        raise ValueError(f"Unknown historical color mode: {legacy_color_mode}")
    check_cancelled(cancel_event)

    if style == STYLE_LEGACY:
        import music_metadata

        tags = music_metadata.read_all_metadata(path)
        image = render_legacy(path, size=size, seed=seed, color_mode=legacy_color_mode)
        image = _add_cover_text(
            image, tags.get("title") or clean_stem(path), tags.get("artist", ""),
            text_mode=text_mode, language="unknown",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG", optimize=True)
        if not preview:
            _save_legacy_profile(output_path, path, seed, text_mode, legacy_color_mode)
        print(f"Обложка сохранена: {output_path} (Music2Picture: {style})")
        return output_path

    import music_metadata
    from lyrics_engine import LyricsService

    tags = music_metadata.read_all_metadata(path)
    resolved_lyrics = ""
    if use_lyrics_for_cover:
        resolved_lyrics = LyricsService(metadata_reader=music_metadata.read_all_metadata).resolve_for_cover(
            path, supplied_text=lyrics_text
        )
    # Lyrics enter analysis only through the explicitly resolved text. Otherwise
    # embedded lyrics could bypass the switch or override edits in the editor.
    analysis_tags = {key: value for key, value in tags.items() if "lyrics" not in str(key).lower()}
    variation = int(seed or 0)
    stages = {
        "loading_audio": "Чтение аудио...",
        "analysing_rhythm": "Анализ характера песни...",
        "building_visual_dna": "Подбор образа и композиции...",
        "creating_visual_brief": "Подготовка изображения...",
    }
    emitted_stages = set()

    def progress(stage):
        check_cancelled(cancel_event)
        message = stages.get(stage)
        if message and message not in emitted_stages:
            emitted_stages.add(message)
            print(message)

    bundle = DEFAULT_PIPELINE.analyse(
        path,
        metadata=analysis_tags,
        lyrics=resolved_lyrics,
        mood_override=mood_override,
        variation=variation,
        progress=progress,
        force=regenerate_description,
    )
    if not preview:
        DescriptionStore().put(path, bundle, lyrics=resolved_lyrics)
    check_cancelled(cancel_event)

    title = tags.get("title") or clean_stem(path)
    artist = tags.get("artist", "")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = render_variant(
        path, bundle.visual_dna, bundle.visual_plan, style=style, size=size,
        seed=seed, preview=preview, legacy_color_mode=legacy_color_mode,
        custom_cover_settings=custom_cover_settings,
    )
    image = _add_cover_text(image, title, artist, text_mode=text_mode, language=bundle.language)
    image.save(output_path, "PNG", optimize=True)
    if not preview:
        _save_music2picture_profile(output_path, path, bundle, seed, text_mode, preview, style,
                                   legacy_color_mode, custom_cover_settings)
    print(f"Обложка сохранена: {output_path} (Music2Picture: {style})")
    return output_path


def _add_cover_text(image, title, artist, *, text_mode, language):
    if text_mode == "none":
        return image
    from cover_engine.typography import TypographyEngine
    from cover_engine.titles import clean_artist, resolve_title

    title_resolution = resolve_title(title, "stylized")
    return TypographyEngine().compose(
        image, title_resolution.selected, clean_artist(artist),
        profile=SimpleNamespace(
            typography_style="artistic title", typography_locked=True,
            text_position="center",
        ),
        title_treatment=title_resolution, enabled=True,
        show_artist=text_mode == "title_artist", language=language,
        placement_override="center",
    )


def make_covers(
    source,
    output,
    size=1000,
    embed=False,
    seed=None,
    lyrics_text="",
    lyrics_lookup=None,
    text_mode="none",
    mood_override="auto",
    style=STYLE_CURRENT,
    legacy_color_mode="plasma",
    cancel_event=None,
    continue_on_error=True,
    use_lyrics_for_cover=False,
    custom_cover_settings=None,
):
    source_path = Path(source).resolve()
    output_root = Path(output).resolve()
    files = audio_files(source_path)
    if not files:
        raise RuntimeError(f"No supported audio files found in {source_path}")
    source_base = source_path.parent if source_path.is_file() else source_path
    results = []
    errors = []
    for index, path in enumerate(files, start=1):
            check_cancelled(cancel_event)
            relative = path.relative_to(source_base).with_suffix("")
            target = output_root / relative.parent / f"{relative.name}_cover_{size}.png"
            relative_key = str(relative).replace("\\", "/")
            file_lyrics = lyrics_text if use_lyrics_for_cover else ""
            if use_lyrics_for_cover and lyrics_lookup:
                file_lyrics = lyrics_lookup.get(relative_key, lyrics_lookup.get(path.stem, file_lyrics))
            print(f"[{index}/{len(files)}] {path.name}")
            try:
                cover = make_cover(
                    path,
                    target,
                    size=size,
                    seed=None if seed is None else int(seed) + index - 1,
                    lyrics_text=file_lyrics,
                    use_lyrics_for_cover=use_lyrics_for_cover,
                    text_mode=text_mode,
                    mood_override=mood_override,
                    style=style,
                    legacy_color_mode=legacy_color_mode,
                    custom_cover_settings=custom_cover_settings,
                    cancel_event=cancel_event,
                )
                if embed:
                    embed_cover(path, cover)
                results.append(cover)
            except InterruptedError:
                raise
            except Exception as exc:
                errors.append((path, str(exc)))
                print(f"Ошибка для {path.name}: {exc}")
                if not continue_on_error or len(files) == 1:
                    raise
    print(f"Готово обложек: {len(results)}; ошибок: {len(errors)}")
    return results


def make_custom_covers(source, image_path, output, size=1000, cancel_event=None):
    """Create safe, square cover copies for every selected audio file."""
    from security import validate_image_file

    source_path = Path(source).resolve()
    image_path = validate_image_file(image_path)
    output_root = Path(output).resolve()
    files = audio_files(source_path)
    if not files:
        raise RuntimeError(f"No supported audio files found in {source_path}")
    size = max(128, min(4096, int(size)))
    with Image.open(image_path) as opened:
        opened.load()
        normalized = ImageOps.fit(
            ImageOps.exif_transpose(opened).convert("RGB"),
            (size, size),
            method=Image.Resampling.LANCZOS,
        )
    source_base = source_path.parent if source_path.is_file() else source_path
    results = []
    for path in files:
        check_cancelled(cancel_event)
        relative = path.relative_to(source_base).with_suffix("")
        target = output_root / relative.parent / f"{relative.name}_cover_{size}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        normalized.save(target, "PNG", optimize=True)
        results.append(target)
    return results


def generate_text_descriptions(
    source,
    *,
    output=None,
    regenerate=False,
    include_visual_brief=True,
    cancel_event=None,
    progress=None,
):
    import music_metadata
    from lyrics_engine import LyricsService

    lyrics_service = LyricsService(metadata_reader=music_metadata.read_all_metadata)

    def lyrics_reader(path):
        value = lyrics_service.load_existing(path)
        return value.text if value is not None else ""

    results = generate_descriptions(
        source,
        metadata_reader=music_metadata.read_all_metadata,
        lyrics_reader=lyrics_reader,
        regenerate=regenerate,
        include_visual_brief=include_visual_brief,
        cancel_event=cancel_event,
        progress=progress,
    )
    if output:
        records = []
        for item in results:
            records.append({
                "path": str(item.path),
                "status": item.status,
                "fingerprint": item.fingerprint,
                "song_description": item.song_description,
                "visual_brief": item.visual_brief,
                "error": item.error,
            })
        DescriptionStore().export(records, Path(output) / ".sonicforge" / "track_descriptions.json")
    return results


def embed_cover(mp3_path, image_path):
    mp3_path = Path(mp3_path)
    if mp3_path.suffix.lower() != ".mp3":
        return False
    temporary = mp3_path.with_name(f"{mp3_path.stem}.cover_tmp.mp3")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(mp3_path), "-i", str(image_path),
            "-map", "0:a:0", "-map", "1:v:0", "-c:a", "copy", "-c:v", "mjpeg",
            "-disposition:v:0", "attached_pic", "-map_metadata", "0", "-id3v2_version", "3", str(temporary),
        ],
        check=True,
        **STARTUP_KWARGS,
    )
    temporary.replace(mp3_path)
    return True


def apply_generated_covers(audio_root, generated_root, published_root, size=1000, embed=True, cancel_event=None):
    audio_root = Path(audio_root).resolve()
    generated_root = Path(generated_root).resolve()
    published_root = Path(published_root).resolve()
    files = audio_files(audio_root)
    base = audio_root.parent if audio_root.is_file() else audio_root
    applied = 0
    for audio_path in files:
        check_cancelled(cancel_event)
        relative = audio_path.relative_to(base).with_suffix("")
        cover = generated_root / relative.parent / f"{relative.name}_cover_{size}.png"
        if not cover.exists():
            print(f"Обложка не найдена для {audio_path.name}")
            continue
        published = published_root / relative.parent / cover.name
        published.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cover, published)
        profile = cover.parent / ".sonicforge" / f"{cover.stem}.profile.json"
        if profile.exists():
            published_profile = published.parent / ".sonicforge" / profile.name
            published_profile.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(profile, published_profile)
        if embed:
            embed_cover(audio_path, cover)
        applied += 1
    print(f"Обложки привязаны к файлам: {applied}")
    return applied


def _save_music2picture_profile(output_path, audio_path, bundle, seed, text_mode, preview=False,
                                style=STYLE_CURRENT, legacy_color_mode="plasma", custom_cover_settings=None):
    import json

    directory = output_path.parent / ".sonicforge"
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "engine": "Music2Picture v2",
        "audio_path": str(audio_path),
        "seed": seed,
        "text_mode": text_mode,
        "generator_version": GENERATOR_VERSION,
        "style": style,
        "custom_cover_settings": custom_cover_settings if style == STYLE_CUSTOM else None,
        "legacy_commit": LEGACY_COMMIT if style != STYLE_CURRENT else None,
        "legacy_color_mode": legacy_color_mode if style != STYLE_CURRENT else None,
        "preview": bool(preview),
        "artistic_parameters": customize_parameters(
            artistic_parameters(bundle.visual_dna, bundle.visual_plan,
                                deterministic_seed(bundle.visual_dna.fingerprint, seed)),
            custom_cover_settings["detail"] if style == STYLE_CUSTOM and custom_cover_settings else None,
        ).to_dict(),
        "analysis_bundle": bundle.to_dict(),
    }
    target = directory / f"{output_path.stem}.profile.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def _save_legacy_profile(output_path, audio_path, seed, text_mode, color_mode):
    import json

    directory = output_path.parent / ".sonicforge"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{output_path.stem}.profile.json"
    data = {
        "engine": "Music2Picture",
        "style": STYLE_LEGACY,
        "legacy_commit": LEGACY_COMMIT,
        "legacy_color_mode": color_mode,
        "audio_path": str(audio_path),
        "seed": seed,
        "text_mode": text_mode,
    }
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def _tag_cover_profile(output_path, style, color_mode, text_mode):
    import json

    target = output_path.parent / ".sonicforge" / f"{output_path.stem}.profile.json"
    if not target.is_file():
        return
    data = json.loads(target.read_text(encoding="utf-8"))
    data.update(style=style, legacy_commit=LEGACY_COMMIT,
                legacy_color_mode=color_mode, postprocessed_text_mode=text_mode)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description="Sonic Forge cover and song-description tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    covers = subparsers.add_parser("covers")
    covers.add_argument("--source", required=True)
    covers.add_argument("--output", required=True)
    covers.add_argument("--style", choices=STYLES, default=STYLE_CURRENT)
    covers.add_argument("--legacy-color-mode", choices=LEGACY_COLOR_MODES, default="plasma")
    covers.add_argument("--size", type=int, default=1000)
    covers.add_argument("--seed", type=int)
    covers.add_argument("--text-mode", choices=("none", "title", "title_artist"), default="none")
    descriptions = subparsers.add_parser("describe")
    descriptions.add_argument("--source", required=True)
    descriptions.add_argument("--output")
    descriptions.add_argument("--regenerate", action="store_true")
    args = parser.parse_args()
    if args.command == "covers":
        make_covers(args.source, args.output, style=args.style,
                    legacy_color_mode=args.legacy_color_mode, size=args.size,
                    seed=args.seed, text_mode=args.text_mode)
    else:
        generate_text_descriptions(args.source, output=args.output, regenerate=args.regenerate)


if __name__ == "__main__":
    main()
