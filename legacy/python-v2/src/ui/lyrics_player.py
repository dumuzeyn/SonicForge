"""Seekable lyrics playback with cancellable rendering outside the Tk thread."""
import copy
from pathlib import Path
import queue
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import wave

from audio_editor import Timeline, render, read_waveform, Cancelled
from lyrics_engine.formats import format_timestamp
from .widgets import RoundedButton, ToolTip


class LyricsPlayer(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='Surface.TFrame')
        self.app = app
        self.columnconfigure(2, weight=1)
        self.play_button = RoundedButton(self, text='▶', command=self.toggle)
        self.play_button.grid(row=0, column=0, padx=(0, 6))
        self.stop_button = RoundedButton(self, text='■', command=self.stop)
        self.stop_button.grid(row=0, column=1, padx=(0, 10))
        self.value = tk.DoubleVar(value=0)
        self.scale = ttk.Scale(self, from_=0, to=1, variable=self.value)
        self.scale.grid(row=0, column=2, sticky='ew')
        self.scale.bind('<ButtonPress-1>', self._scrub_start)
        self.scale.bind('<ButtonRelease-1>', self._scrub_end)
        self.scale.bind('<KeyRelease>', self._scrub_end)
        self.caption = tk.StringVar(value='00:00.00 / 00:00.00')
        ttk.Label(self, textvariable=self.caption, style='SurfaceSecondary.TLabel').grid(row=0, column=3, padx=10)
        ToolTip(self.play_button, lambda: app.t('tip_lyrics_play'), title_provider=lambda: app.t('lyrics_play'))
        ToolTip(self.stop_button, lambda: app.t('tip_lyrics_stop'), title_provider=lambda: app.t('lyrics_stop'))
        self.duration = 0
        self.has_position = False
        self.playing = False
        self.scrubbing = False
        self._origin = 0
        self._started = 0
        self._after = None
        self._generation = 0
        self._cancel = threading.Event()
        self._events = queue.Queue()
        self._worker = None
        self._temp = None
        self._cache = None
        self.bind('<Destroy>', self._destroy, add='+')

    @property
    def position(self):
        if self.playing:
            return min(self.duration, self._origin + time.monotonic() - self._started)
        return self.value.get()

    def invalidate(self):
        self.stop()
        self._cache = None

    def stop(self):
        position = self.position
        if self.playing:
            self.app.stop_audio_preview()
        self.playing = False
        self.value.set(position)
        self.play_button.configure(text='▶', state='normal')
        self._cancel.set()
        self._generation += 1
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        self._show_position()

    def toggle(self):
        if self.playing:
            self.stop()
        else:
            self.play()

    def seek(self, seconds):
        resume = self.playing
        self.stop()
        self.value.set(max(0, min(self.duration, seconds)))
        self.has_position = True
        self._show_position()
        if resume:
            self.play()

    def _scrub_start(self, _event=None):
        self._resume_scrub = self.playing
        self.stop()
        self.scrubbing = True

    def _scrub_end(self, _event=None):
        self.has_position = True
        self.scrubbing = False
        self._show_position()
        if getattr(self, '_resume_scrub', False):
            self._resume_scrub = False
            self.play()

    def play(self):
        if self._worker and self._worker.is_alive():
            return
        if self.app.worker and self.app.worker.is_alive():
            return
        try:
            if self.app.editor_pipeline_var.get():
                project = copy.deepcopy(self.app.view.editor.project)
                if not project.clips:
                    raise ValueError(self.app.t('editor_empty'))
                signature = repr((project.clips, sorted(project.muted), project.sources))
                source = None
            else:
                source = self.app._single_audio_source()
                if source is None:
                    return
                stat = source.stat()
                signature = (str(source), stat.st_size, stat.st_mtime_ns)
                project = None
        except (OSError, ValueError) as exc:
            self.app.lyrics_status_var.set(str(exc))
            return
        self.stop()
        self.app.view.editor.stop()
        self.app.stop_audio_preview()
        if self._temp is None:
            self._temp = tempfile.TemporaryDirectory(prefix='sonicforge-lyrics-play-')
        root = Path(self._temp.name)
        generation = self._generation
        self._cancel = cancel = threading.Event()
        cache = self._cache if self._cache and self._cache[0] == signature else None
        start = self.value.get()
        self.play_button.configure(state='disabled')
        def work():
            try:
                if cache:
                    _, full, duration = cache
                else:
                    current = project
                    if current is None:
                        current = Timeline()
                        current.add(read_waveform(source, cancel))
                    duration = current.duration
                    full = render(current, root / f'{time.time_ns()}-full.wav', cancel)
                at = start if start < duration else 0
                preview = root / f'{time.time_ns()}-seek.wav'
                with wave.open(str(full)) as audio, wave.open(str(preview), 'wb') as output:
                    output.setparams(audio.getparams())
                    audio.setpos(min(audio.getnframes(), round(at * audio.getframerate())))
                    while data := audio.readframes(44100):
                        if cancel.is_set():
                            raise Cancelled()
                        output.writeframesraw(data)
                self._events.put((generation, 'ready', (signature, full, duration, preview, at)))
            except Cancelled:
                pass
            except Exception as exc:
                self._events.put((generation, 'error', str(exc)))
        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()
        self._after = self.after(40, self._poll)

    def _poll(self):
        self._after = None
        try:
            while True:
                generation, kind, value = self._events.get_nowait()
                if generation != self._generation:
                    continue
                self.play_button.configure(state='normal')
                if kind == 'error':
                    self.app.lyrics_status_var.set(value)
                    return
                signature, full, self.duration, preview, at = value
                self._cache = (signature, full, self.duration)
                self.scale.configure(to=self.duration)
                import winsound
                winsound.PlaySound(str(preview), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                self._origin, self._started = at, time.monotonic()
                self.has_position = self.playing = True
                self.play_button.configure(text='Ⅱ')
                self._tick()
                return
        except queue.Empty:
            if self._worker and self._worker.is_alive():
                self._after = self.after(40, self._poll)
            else:
                self.play_button.configure(state='normal')
        except (ImportError, RuntimeError, OSError) as exc:
            self.app.lyrics_status_var.set(str(exc))

    def _show_position(self):
        self.caption.set(f'{format_timestamp(self.value.get())} / {format_timestamp(self.duration)}')

    def _tick(self):
        self._after = None
        self.value.set(self.position)
        self._show_position()
        if self.value.get() >= self.duration:
            self.stop()
        elif self.playing:
            self._after = self.after(30, self._tick)

    def _destroy(self, event):
        if event.widget is not self:
            return
        # Child controls have already been destroyed when the frame receives
        # Destroy. Stop sound and workers without touching their Tcl commands.
        self._cancel.set()
        self._generation += 1
        if self.playing:
            self.app.stop_audio_preview()
        self.playing = False
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        if self._temp:
            temporary, worker = self._temp, self._worker
            def cleanup():
                if worker and worker.is_alive():
                    worker.join()
                temporary.cleanup()
            threading.Thread(target=cleanup, daemon=True).start()
