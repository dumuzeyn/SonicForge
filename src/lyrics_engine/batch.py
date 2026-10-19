from pathlib import Path

from .formats import find_sidecar, save_lyrics
from .service import LyricsService


def recognize_batch(source, staging, output=None, service=None, export_format="txt",
                    overwrite=False, language="auto", cancel_event=None, progress=None, separate_vocals=None,
                    mode='recognize', supplied_lyrics=None):
    import music_metadata
    owned = service is None
    service = service or LyricsService(metadata_reader=music_metadata.read_all_metadata, separate_vocals=separate_vocals)
    if separate_vocals is not None and isinstance(service, LyricsService):
        service.separate_vocals = bool(separate_vocals)
    try:
        if mode == 'align':
            return _align_batch(source, staging, service, export_format, language, cancel_event, progress, supplied_lyrics)
        if mode != 'recognize':
            raise ValueError('Unknown lyrics mode')
        return _recognize_batch(source, staging, output, service, export_format, overwrite,
                                language, cancel_event, progress)
    finally:
        if owned:
            service.close()

def _align_batch(source, staging, service, export_format, language, cancel_event, progress, supplied_lyrics=None):
    import music_metadata
    source, staging = Path(source).resolve(), Path(staging).resolve()
    base = source.parent if source.is_file() else source
    originals = {p.relative_to(base).with_suffix(''): p for p in music_metadata.audio_files(source)}
    files = music_metadata.audio_files(staging)
    lookup = {}
    counts = dict(saved=0, preserved=0, uncertain=0, failed=0)
    if progress:
        progress('started', dict(total=len(files), mode='align'))
    for index, path in enumerate(files, 1):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError('Timing correction was cancelled')
        data = dict(index=index, total=len(files), file=path.name)
        def emit(stage, **extra):
            if progress:
                progress(stage, dict(data, **extra))
        try:
            original = originals.get(path.relative_to(staging).with_suffix(''))
            existing = supplied_lyrics if supplied_lyrics is not None and len(files) == 1 else (
                service.load_for_timing(original) if original else None)
            if existing is None or not existing.text.strip():
                counts['preserved'] += 1
                emit('preserved', reason='no_existing_lyrics')
                print(f'[{index}/{len(files)}] Timing correction skipped: {path.name}: no existing lyrics')
                continue
            # Stage the original first, including sidecars. A model error,
            # cancellation, or uncertain result must never leave words behind.
            save_lyrics(path, existing, 'lrc' if existing.segments and path.suffix.lower() != '.mp3' else export_format)
            emit('file_started', mode='align')
            corrected = service.align(path, existing, cancel_event=cancel_event, progress=lambda stage: emit('progress', step=stage), language=language)
            if corrected.text != existing.text:
                raise ValueError('Timing correction cannot replace existing lyrics')
            if corrected.review_reason:
                counts['uncertain'] += 1
                emit('uncertain', reason='alignment')
                # Retain the supplied lyrics and timestamps, even after other
                # selected stages transformed the staging container.
                continue
            save_lyrics(path, corrected, 'lrc' if path.suffix.lower() != '.mp3' else export_format)
            lookup[_relative_key(path, staging)] = corrected.text
            counts['saved'] += 1
            emit('saved', mode='align', retained=corrected.timings_preserved)
            print(f'[{index}/{len(files)}] Corrected timings: {path.name}; words retained')
        except InterruptedError:
            raise
        except Exception as exc:
            counts['failed'] += 1
            emit('failed', error=str(exc))
            print(f'[{index}/{len(files)}] Timing correction failed: {path.name}: {exc}')
    if progress:
        progress('completed', dict(total=len(files), **counts))
    return lookup


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
                if existing and existing.text.strip():
                    save_lyrics(staged_audio, existing)
                    lyrics_lookup[_relative_key(staged_audio, staging)] = existing.text
                    print(f"[{index}/{len(staged_files)}] Embedded lyrics preserved: {staged_audio.name}")
                    counts["preserved"] += 1
                    emit("preserved")
                    continue
            if not overwrite and original is not None:
                existing = service.load_existing(original)
                if existing and existing.text.strip():
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
                if loaded and loaded.text.strip():
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
