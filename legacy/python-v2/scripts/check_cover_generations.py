"""Synthetic cover checks and screenshots of only test-created app windows."""
import hashlib
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import wave

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from music_polisher_gui import SonicForgeApp, enable_high_dpi
from music2picture_v2 import DEFAULT_PIPELINE
from music2picture_v2.variants import render_variant
from scripts.check_navigation_rendering import capture, settle
from ui.dialogs import CustomCoverDialog


def main():
    output = ROOT / 'validation/cover-generations'
    output.mkdir(parents=True, exist_ok=True)
    rate = 22050
    time = np.arange(rate * 32) / rate
    period = np.where(time < 16, 60 / 70, 60 / 175)
    audio = np.sin(2 * np.pi * 110 * time) * np.exp(-np.mod(time, period) * 28) * .5
    audio += np.sin(2 * np.pi * 330 * time) * .025
    source = output / 'synthetic-tempo.wav'
    with wave.open(str(source), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes((audio * 32767).astype('<i2').tobytes())
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    bundle = DEFAULT_PIPELINE.analyse(source)
    sheet = Image.new('RGB', (900, 984), '#f4f4fa')
    draw = ImageDraw.Draw(sheet)
    for row, pattern in enumerate(('legacy', 'modern', 'timeline')):
        for column, color in enumerate(('legacy', 'modern', 'speed')):
            image = render_variant(source, bundle.visual_dna, bundle.visual_plan,
                style='generated', size=640, seed=42,
                custom_cover_settings=dict(pattern=pattern, color_source=color))
            target = output / f'pattern-{row + 1}-color-{column + 1}.png'
            image.save(target)
            sheet.paste(image.resize((300, 300), Image.Resampling.LANCZOS), (column * 300, row * 328 + 28))
            draw.text((column * 300 + 8, row * 328 + 6),
                      f'Generation M2Pv{row + 1} / Color M2Pv{column + 1}', fill='#292938')
    sheet.save(output / 'combinations.png')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    enable_high_dpi()
    with tempfile.TemporaryDirectory() as temporary, patch('cover_preferences.preference_path',
            return_value=Path(temporary) / 'custom_cover.json'):
        app = SonicForgeApp()
        try:
            app.cover_style_var.set('Генерируемая')
            app.cover_color_var.set('M2Pv3 — скорость ритма')
            app.cover_pattern_var.set('M2Pv3 — структура песни')
            app.cover_generation_changed()
            assert len(app.cover_choice_values('style')) == 2
            assert len(app.cover_choice_values('color')) == 3
            assert len(app.cover_choice_values('pattern')) == 3
            app.view.show_tab('cover')
            app.view.show_cover_preview(output / 'pattern-3-color-3.png')
            settle(app)
            capture(app, output / 'generated-ru.png')
            app.toggle_language()
            settle(app)
            capture(app, output / 'generated-en.png')
            app.cover_style_var.set('Custom theme')
            app.view.update_cover_source()
            settle(app)
            capture(app, output / 'custom-en.png')
            dialog = CustomCoverDialog(app)
            settle(dialog)
            capture(dialog, output / 'custom-dialog-en.png')
            dialog.close()
        finally:
            app.destroy()
        restarted = SonicForgeApp()
        try:
            assert restarted.cover_choice('style', restarted.cover_style_var.get()) == 'generated'
            assert restarted.cover_choice('color', restarted.cover_color_var.get()) == 'speed'
            assert restarted.cover_choice('pattern', restarted.cover_pattern_var.get()) == 'timeline'
        finally:
            restarted.destroy()
    print('Verified nine combinations, unchanged source, UI controls and settings restored after restart.')
    print(output)


if __name__ == '__main__':
    main()
