"""Local editor smoke/latency check. Reads a real source, exports temporary clips.

Use --hold for visual inspection. Does not play audio or modify the source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_editor import render
from music_polisher_gui import SonicForgeApp, configure_bundled_ffmpeg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--hold", action="store_true")
    args = parser.parse_args()
    configure_bundled_ffmpeg()
    source = args.source.resolve(strict=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    started = time.perf_counter()
    app = SonicForgeApp()
    app.update()
    startup = time.perf_counter() - started
    editor = app.view.editor
    beats = []
    def heartbeat():
        beats.append(time.perf_counter())
        if app.winfo_exists():
            app.after(15, heartbeat)
    app.after(15, heartbeat)
    started = time.perf_counter()
    editor.import_files([str(source)])
    while editor.is_busy or not editor.project.clips:
        app.update()
        time.sleep(.003)
        if time.perf_counter() - started > 45:
            raise RuntimeError(editor.status.get())
    import_seconds = time.perf_counter() - started
    imported = editor.project.clips[0]
    second = editor.project.add(editor.project.sources[imported.source], lane=1, position=5)
    editor.project.update(second.id, end=min(12, second.end), gain=-9, fade_in=1, fade_out=1)
    editor.changed()
    app.update()
    samples = []
    top_positions = []
    for _ in range(10):
        for name in app.view.tab_pages:
            started = time.perf_counter()
            app.view.show_tab(name)
            app.update_idletasks()
            samples.append((time.perf_counter() - started) * 1000)
            top_positions.append(app.view.tab_buttons["editor"].winfo_rooty())
    started = time.perf_counter()
    app.show_advanced_audio()
    app.update_idletasks()
    first_dialog = (time.perf_counter() - started) * 1000
    dialog = app.advanced_dialog
    dialog.close()
    started = time.perf_counter()
    app.show_advanced_audio()
    app.update_idletasks()
    reused_dialog = (time.perf_counter() - started) * 1000
    dialog.close()
    with tempfile.TemporaryDirectory(prefix="sonicforge-editor-test-") as directory:
        path = render(editor.project, Path(directory) / "preview.wav", start=5, length=4)
        output_size = path.stat().st_size
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    gaps = [(b - a) * 1000 for a, b in zip(beats, beats[1:])]
    metrics = dict(startup_seconds=round(startup, 3), import_seconds=round(import_seconds, 3),
                   tab_median_ms=round(statistics.median(samples), 2), tab_max_ms=round(max(samples), 2),
                   fixed_tab_bar=len(set(top_positions)) == 1,
                   dialog_first_ms=round(first_dialog, 2), dialog_reopen_ms=round(reused_dialog, 2),
                   heartbeat_count=len(beats), heartbeat_max_gap_ms=round(max(gaps, default=0), 2),
                   waveform_bins=len(editor.project.sources[imported.source].peaks),
                   preview_bytes=output_size, source_unchanged=before == after,
                   client_size=[app.winfo_width(), app.winfo_height()])
    print(json.dumps(metrics, indent=2))
    app.view.show_tab("editor")
    if args.hold:
        app.mainloop()
    else:
        app._close()


if __name__ == "__main__":
    main()
