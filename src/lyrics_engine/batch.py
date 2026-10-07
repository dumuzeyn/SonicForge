from pathlib import Path

from .formats import find_sidecar, save_lyrics
from .service import LyricsService


def recognize_batch(source, staging, output=None, service=None, export_format="txt",
                    overwrite=False, language="auto", cancel_event=None, progress=None):
    import music_metadata
    owned = service is None
    service = service or LyricsService(metadata_reader=music_metadata.read_all_metadata)
    try:
        return _recognize_batch(source, staging, output, service, export_format, overwrite,
                                language, cancel_event, progress)
    finally:
        if owned:
            service.close()

def _recognize_batch(
    source,
    staging,
    output=None,
    service=None,
    export_format="txt",
    overwrite=False,
    language="auto",
    cancel_event=None,
    progress=None,
):
    import music_metadata

    source = Path(source).resolve()
    staging = Path(staging).resolve()
    output = Path(output).resolve() if output else None
    service = service or LyricsService(metadata_reader=music_metadata.read_all_metadata)
    source_base = source.parent if source.is_file() else source
    lyrics_lookup = {}
    staged_files = music_metadata.audio_files(staging)
    original_files = {
        path.relative_to(source_base).with_suffix(""): path
        for path in music_metadata.audio_files(source)
    }
    counts = dict(saved=0, preserved=0, uncertain=0, failed=0)
    if progress:
        progress("started", {"total": len(staged_files)})
    for index, staged_audio in enumerate(staged_files, start=1):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Lyrics recognition was cancelled")
        relative = staged_audio.relative_to(staging)
        def emit(stage, **details):
            if progress:
                progress(stage, dict(index=index, total=len(staged_files), file=staged_audio.name, **details))
        emit("file_started")
        try:
            original = original_files.get(relative.with_suffix(""))
            output_audio = output / relative if output else None
            is_mp3 = staged_audio.suffix.lower() == ".mp3"
            existing_output = find_sidecar(output_audio) if output_audio and not is_mp3 else None
            if not overwrite and existing_output:
                destination = staged_audio.with_suffix(existing_output.suffix)
                destination.write_bytes(existing_output.read_bytes())
                loaded = service.load_existing(output_audio)
                if loaded and loaded.text.strip():
                    lyrics_lookup[_relative_key(staged_audio, staging)] = loaded.text
                print(f"[{index}/{len(staged_files)}] Lyrics preserved: {staged_audio.name}")
                counts["preserved"] += 1
                emit("preserved")
                continue
            if not overwrite and is_mp3 and output_audio and output_audio.is_file():
                existing = service.load_existing(output_audio)
                if existing and existing.segments:
                    save_lyrics(staged_audio, existing)
                    lyrics_lookup[_relative_key(staged_audio, staging)] = existing.text
                    print(f"[{index}/{len(staged_files)}] Embedded lyrics preserved: {staged_audio.name}")
                    counts["preserved"] += 1
                    emit("preserved")
                    continue
            if not overwrite and original is not None:
                existing = service.load_existing(original)
                if existing and existing.text.strip() and (not is_mp3 or existing.segments):
                    sidecar = find_sidecar(original)
                    existing_format = sidecar.suffix.lstrip(".") if sidecar else export_format
                    save_lyrics(staged_audio, existing, existing_format)
                    lyrics_lookup[_relative_key(staged_audio, staging)] = existing.text
                    print(f"[{index}/{len(staged_files)}] Existing lyrics copied: {staged_audio.name}")
                    counts["preserved"] += 1
                    emit("preserved")
                    continue
            if not overwrite and is_mp3:
                loaded = service.load_existing(staged_audio)
                if loaded and loaded.segments:
                    lyrics_lookup[_relative_key(staged_audio, staging)] = loaded.text
                    print(f"[{index}/{len(staged_files)}] Embedded lyrics preserved: {staged_audio.name}")
                    counts["preserved"] += 1
                    emit("preserved")
                    continue
            print(f"[{index}/{len(staged_files)}] Recognize lyrics: {staged_audio.name}")
            duration = None
            if progress:
                from audio_tags import probe_audio
                try:
                    duration = probe_audio(staged_audio)['duration']
                except (AttributeError, OSError, ValueError):
                    pass
            callbacks = {}
            if progress:
                callbacks = dict(progress=lambda stage: emit(stage),
                                 on_segment=lambda segment: emit("transcribing", audio_end=segment.end,
                                                                  duration=duration))
            result = service.recognize(staged_audio, cancel_event=cancel_event,
                                       language=language, **callbacks)
            if result.instrumental or result.review_reason or not result.text.strip():
                print(f"[{index}/{len(staged_files)}] Lyrics need review: {staged_audio.name} ({result.review_reason or 'no_text'})")
                if result.text.strip():
                    review = staged_audio.with_suffix('.lyrics-review.txt')
                    review.write_text('Needs manual review; not embedded in audio.\nReason: '
                                      + (result.review_reason or 'confidence') + '\n\n' + result.text,
                                      encoding='utf-8')
                counts["uncertain"] += 1
                emit("uncertain")
                continue
            if is_mp3 and not result.segments:
                print(f"[{index}/{len(staged_files)}] No line timestamps available: {staged_audio.name}")
                counts["uncertain"] += 1
                emit("uncertain")
                continue
            emit("saving")
            save_lyrics(staged_audio, result, export_format)
            lyrics_lookup[_relative_key(staged_audio, staging)] = result.text
            counts["saved"] += 1
            emit("saved")
        except InterruptedError:
            emit("cancelled")
            raise
        except Exception as exc:
            error = f'{type(exc).__name__}: {str(exc)[:2000]}'
            print(f"[{index}/{len(staged_files)}] Lyrics unavailable: {staged_audio.name} ({error})")
            counts["failed"] += 1
            emit("failed", error=error)
    if progress:
        progress("completed", dict(total=len(staged_files), **counts))
    return lyrics_lookup

def _relative_key(audio_path, root):
    return str(Path(audio_path).relative_to(root).with_suffix("")).replace("\\", "/")
