from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import numpy as np
from PIL import Image

import music2picture
from music2picture_v2 import analyze_audio_array, build_visual_dna, build_visual_plan
from music2picture_v2.variants import render_variant
from music2picture_v2.custom_style import CustomCoverSettings
from music2picture_v3 import analyze_structure_array, SongStructure
from music2picture_v3.colors import apply_speed_colors
from music2picture_v3.renderer import timeline_fields


class CoverGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rate = 22050
        time = np.arange(rate * 16) / rate
        phase = time % .5
        cls.audio = (np.sin(2 * np.pi * 100 * time) * np.exp(-phase * 25) * .5).astype(np.float32)
        cls.dna = build_visual_dna(analyze_audio_array(cls.audio, rate))
        cls.plan = build_visual_plan(cls.dna)
        cls.structure = analyze_structure_array(cls.audio, rate)

    def test_all_nine_independent_color_and_pattern_combinations_render(self):
        results = []
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'beat.wav'
            with wave.open(str(source), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(22050)
                stream.writeframes((self.audio * 32767).astype('<i2').tobytes())
            before = source.read_bytes()
            for pattern in ('legacy', 'modern', 'timeline'):
                for color in ('legacy', 'modern', 'speed'):
                    with self.subTest(pattern=pattern, color=color):
                        image = render_variant(source, self.dna, self.plan, style='generated',
                            size=192, seed=42, custom_cover_settings=dict(pattern=pattern, color_source=color))
                        self.assertEqual(image.size, (192, 192))
                        results.append(image.tobytes())
            self.assertEqual(source.read_bytes(), before)
        self.assertEqual(len(set(results)), 9)

    def test_speed_color_tracks_tempo_without_confusing_loudness(self):
        rate = 22050
        t = np.arange(rate * 24) / rate
        profiles = []
        for bpm, gain in ((65, .35), (175, .35), (175, .10)):
            beat = np.sin(2 * np.pi * 120 * t) * np.exp(-(t % (60 / bpm)) * 30) * gain
            structure = analyze_structure_array(beat, rate)
            profiles.append(float(np.median(structure.speed_curve)))
        self.assertGreater(profiles[1] - profiles[0], .25)
        self.assertAlmostEqual(profiles[1], profiles[2], delta=.08)
        gradient = np.tile(np.linspace(0, 255, 192, dtype=np.uint8)[:, None], (1, 192))
        base = Image.fromarray(gradient, 'L').convert('RGB')
        slow = apply_speed_colors(base, replace(self.structure, speed_curve=(0.,)))
        fast = apply_speed_colors(base, replace(self.structure, speed_curve=(1.,)))
        a, b = np.asarray(slow).mean(axis=(0, 1)), np.asarray(fast).mean(axis=(0, 1))
        self.assertGreater(a[2], a[0])
        self.assertGreater(b[0], b[2])

    def test_silent_and_short_audio_have_no_invented_rhythm(self):
        for samples in (np.zeros(1), np.zeros(22050), np.array([])):
            structure = analyze_structure_array(samples)
            self.assertEqual(max(structure.speed_curve), 0)
            image = apply_speed_colors(Image.new('RGB', (64, 64), '#446688'), structure)
            self.assertEqual(image.size, (64, 64))

    def test_old_custom_preferences_and_new_choices_round_trip(self):
        self.assertEqual(CustomCoverSettings.parse(dict(pattern='legacy')).color_source, 'custom')
        for pattern in ('legacy', 'modern', 'timeline'):
            for color in ('legacy', 'modern', 'speed', 'custom'):
                settings = CustomCoverSettings.parse(dict(pattern=pattern, color_source=color))
                self.assertEqual(CustomCoverSettings.parse(json.loads(json.dumps(settings.to_dict()))), settings)
        with self.assertRaises(ValueError):
            CustomCoverSettings.parse(dict(color_source='bad'))

    def test_timeline_retains_the_position_of_a_changed_song_section(self):
        spectrum = np.zeros((128, 16), dtype=np.float32)
        spectrum[:, 12:] = .8
        structure = SongStructure(spectrum, np.ones(16), np.zeros(16))
        fields = timeline_fields(structure, self.dna, 128)
        self.assertEqual(float(fields.spectrum[:, :64].max()), 0)
        self.assertGreater(float(fields.spectrum[:, -16:].mean()), .75)

    def test_profile_records_both_selected_generations(self):
        bundle = SimpleNamespace(visual_dna=self.dna, visual_plan=self.plan, to_dict=lambda: {})
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'cover.png'
            settings = CustomCoverSettings.parse(dict(pattern='timeline', color_source='speed')).to_dict()
            music2picture._save_music2picture_profile(target, Path('test.wav'), bundle, 42, 'none',
                style='generated', custom_cover_settings=settings)
            data = json.loads((Path(temporary) / '.sonicforge/cover.profile.json').read_text(encoding='utf-8'))
            self.assertEqual(data['pattern_generation'], 'M2Pv3')
            self.assertEqual(data['color_generation'], 'M2Pv3')
            self.assertEqual(data['timeline_direction'], 'left_to_right')
            self.assertEqual(data['color_generator_version'], 'rhythmic-speed-v2')


if __name__ == '__main__':
    unittest.main()
