"""Reproducible native screenshots of our own app with synthetic demo media.

Does not open a user's project, recognize speech, download models, or change
installed settings. Demo lyrics are manually entered, not recognition output.
"""
from pathlib import Path
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audio_editor import read_waveform
from music_polisher_gui import SonicForgeApp
from music2picture import make_cover
from scripts.check_navigation_rendering import capture, settle


def make_demo(path, frequency, duration=16):
    rate = 22050
    t = np.arange(rate * duration) / rate
    envelope = .15 + .65 * np.maximum(0, np.sin(2 * np.pi * 1.6 * t)) ** 4
    notes = np.sin(2 * np.pi * frequency * t) + .3 * np.sin(2 * np.pi * frequency * 1.5 * t)
    samples = (.45 * envelope * notes * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(samples.tobytes())


def main():
    output = Path(__file__).resolve().parents[1] / 'docs' / 'images'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sonicforge-readme-') as temporary:
        demo = Path(temporary)
        song = demo / 'Northern Lights.wav'
        harmony = demo / 'Harmony.wav'
        make_demo(song, 220)
        make_demo(harmony, 330, 12)
        cover = demo / 'cover.png'
        make_cover(song, cover, size=440, seed=42, preview=True, use_lyrics_for_cover=False)
        app = SonicForgeApp()
        try:
            settle(app)
            app.geometry('1100x850')
            app._set_source_path(song, is_folder=False)
            # Illustrative paths are text only; never read or written by this script.
            app.source_var.set(r'C:\Music\Northern Lights.wav')
            app.output_var.set(r'C:\Music\SonicForgeProgect')
            app.title_var.set('Northern Lights')
            app.artist_var.set('SonicForge Demo')
            app.album_var.set('Practice Session')
            app.genre_var.set('Instrumental')
            app.date_var.set('2026')
            app.track_var.set('1/2')
            editor = app.view.editor
            first = editor.project.add(read_waveform(song), lane=0, position=0)
            editor.project.add(read_waveform(harmony), lane=1, position=0)
            editor.selected = first.id
            editor.cursor = 4
            editor.range = (3, 6)
            editor._range_clip_id = first.id
            editor.refresh()
            editor.fit()
            for language in ('ru', 'en'):
                if app.language != language:
                    app.toggle_language()
                app.view.set_lyrics_text(
                    'Учебный пример: текст введён вручную.\n\nСвет над рекой\nРитм под рукой\nНовый рассвет\nМузыки след'
                    if language == 'ru' else
                    'Practice example: manually entered lyrics.\n\nLight on the stream\nRhythm in a dream\nMorning in sight\nMusic and light')
                for name in ('editor', 'metadata', 'audio', 'cover', 'lyrics', 'processing', 'help', 'settings'):
                    app.view.show_tab(name)
                    if name == 'cover':
                        app.view.show_cover_preview(cover)
                    settle(app)
                    capture(app, output / f'{name}-{language}.png')
                app.show_advanced_audio()
                dialog = app.advanced_dialog
                for name, page in (('audio-advanced', dialog.enhancement_page), ('audio-effects', dialog.effects_tab)):
                    dialog.notebook.select(page)
                    settle(dialog)
                    capture(dialog, output / f'{name}-{language}.png')
                dialog.close()
            print(f'Captured 20 native-resolution screenshots in {output}')
        finally:
            app._close()


if __name__ == '__main__':
    main()
