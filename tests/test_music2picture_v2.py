import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import ImageChops, ImageStat

import music2picture
import music2picture_v2
from music2picture_v2 import (
    DescriptionStore,
    Music2PicturePipeline,
    STAGE_ORDER,
    analyze_audio_array,
    build_visual_dna,
    build_visual_plan,
    create_song_description,
    generate_descriptions,
    render_cover,
    visual_plan_distance,
)
from music2picture_v2.renderer import COMPOSITIONS, artistic_parameters, deterministic_seed


class StubValue:
    def __init__(self, **values):
        self.__dict__.update(values)

    def to_dict(self):
        return dict(self.__dict__)


class StubPipeline:
    def __init__(self, broken=()):
        self.calls = []
        self.broken = set(broken)

    def analyse(self, path, progress=None, **_kwargs):
        path = Path(path)
        self.calls.append(path.name)
        if path.name in self.broken:
            raise RuntimeError("damaged audio")
        if progress:
            for stage in STAGE_ORDER:
                progress(stage)
        fingerprint = f"fingerprint-{path.stem}"
        return SimpleNamespace(
            analysis=StubValue(fingerprint=fingerprint),
            visual_dna=StubValue(identity=path.stem),
            visual_plan=StubValue(identity=path.stem),
            song_description=f"description for {path.stem}",
            visual_brief=f"brief for {path.stem}",
            language="en",
        )


class Music2PictureV2Tests(unittest.TestCase):
    def test_audio_analysis_does_not_require_scipy(self):
        source = (Path(music2picture_v2.__file__).parent / "audio_analysis.py").read_text(encoding="utf-8")
        self.assertNotIn("scipy", source.lower())

    def test_music2picture_is_the_only_cover_renderer(self):
        self.assertTrue(callable(music2picture.make_cover))
        self.assertFalse(hasattr(music2picture_v2, "MODES"))
        self.assertFalse(hasattr(music2picture_v2, "select_mode"))

    def test_absolute_loudness_is_not_erased_by_relative_normalization(self):
        sample_rate = 8000
        time = np.arange(sample_rate * 2) / sample_rate
        quiet = analyze_audio_array((np.sin(2 * np.pi * 220 * time) * 0.03).astype(np.float32), sample_rate)
        loud = analyze_audio_array((np.sin(2 * np.pi * 220 * time) * 0.75).astype(np.float32), sample_rate)
        self.assertGreater(loud.rms_dbfs - quiet.rms_dbfs, 20.0)
        self.assertAlmostEqual(loud.relative_dynamic_range, quiet.relative_dynamic_range, delta=0.08)

    def test_short_silent_and_varied_signals_all_produce_valid_descriptions(self):
        sample_rate = 8000
        time = np.arange(sample_rate * 2) / sample_rate
        rng = np.random.default_rng(7)
        impulse = np.zeros_like(time, dtype=np.float32)
        impulse[::800] = 0.9
        dynamic = np.sin(2 * np.pi * (110 + time * 260) * time) * np.linspace(0.03, 0.9, time.size)
        signals = {
            "short": np.asarray([0.0, 0.2, -0.2], dtype=np.float32),
            "silent": np.zeros(sample_rate, dtype=np.float32),
            "sine": (np.sin(2 * np.pi * 440 * time) * 0.35).astype(np.float32),
            "noise": (rng.normal(0, 0.18, time.size)).astype(np.float32),
            "bass": (np.sin(2 * np.pi * 62 * time) * 0.65).astype(np.float32),
            "percussion": impulse,
            "calm": (np.sin(2 * np.pi * 180 * time) * 0.08).astype(np.float32),
            "dynamic": dynamic.astype(np.float32),
        }
        descriptions = []
        plans = []
        for signal in signals.values():
            analysis = analyze_audio_array(signal, sample_rate)
            dna = build_visual_dna(analysis)
            descriptions.append(create_song_description(dna, "en"))
            plans.append(build_visual_plan(dna))
        self.assertTrue(all(len(description) > 80 for description in descriptions))
        self.assertGreaterEqual(len(set(descriptions)), 5)
        self.assertGreater(max(visual_plan_distance(plans[0], plan) for plan in plans[1:]), 0.08)

    def test_description_takes_its_image_from_lyrics_when_available(self):
        sample_rate = 8000
        time = np.arange(sample_rate) / sample_rate
        analysis = analyze_audio_array((np.sin(2 * np.pi * 220 * time) * 0.2).astype(np.float32), sample_rate)
        dna = build_visual_dna(analysis)
        text = create_song_description(
            dna, "ru", lyrics="[00:01.20]Ночной поезд уходит домой\n[00:04.00]Ночной поезд уходит домой"
        )
        self.assertIn("Ночной поезд уходит домой", text)
        self.assertNotIn("[00:01.20]", text)
        self.assertNotEqual(text, create_song_description(dna, "ru"))

    def test_universal_renderer_is_deterministic_and_audio_sensitive(self):
        sample_rate = 8000
        time = np.arange(sample_rate * 2) / sample_rate
        left_dna = build_visual_dna(analyze_audio_array((np.sin(2 * np.pi * 70 * time) * 0.6).astype(np.float32), sample_rate))
        rng = np.random.default_rng(11)
        right_dna = build_visual_dna(analyze_audio_array(rng.normal(0, 0.25, time.size).astype(np.float32), sample_rate))
        first = render_cover(left_dna, build_visual_plan(left_dna), size=192, seed=42)
        repeated = render_cover(left_dna, build_visual_plan(left_dna), size=192, seed=42)
        different = render_cover(right_dna, build_visual_plan(right_dna), size=192, seed=42)
        self.assertIsNone(ImageChops.difference(first, repeated).getbbox())
        self.assertGreater(sum(ImageStat.Stat(ImageChops.difference(first, different)).mean), 8.0)

    def test_artistic_renderer_has_no_signal_trace_drawing(self):
        source = (Path(music2picture_v2.__file__).parent / "renderer.py").read_text(encoding="utf-8").lower()
        for forbidden in ("draw.line", "waveform", "oscillogram", "spectrum graph", "energy_curve["):
            self.assertNotIn(forbidden, source)

    def test_seed_combines_track_fingerprint_and_variation(self):
        self.assertEqual(deterministic_seed("track-a", 4), deterministic_seed("track-a", 4))
        self.assertNotEqual(deterministic_seed("track-a", 4), deterministic_seed("track-b", 4))
        self.assertNotEqual(deterministic_seed("track-a", 4), deterministic_seed("track-a", 5))

    def test_palette_and_composition_vary_across_distinct_signals(self):
        sample_rate = 8000
        time = np.arange(sample_rate * 2) / sample_rate
        rng = np.random.default_rng(7)
        signals = (
            np.zeros(sample_rate),
            np.sin(2 * np.pi * 60 * time) * 0.6,
            np.sin(2 * np.pi * 440 * time) * 0.3,
            rng.normal(0, 0.2, time.size),
            np.sin(2 * np.pi * (80 + time * 500) * time) * 0.5,
            ((np.arange(time.size) % 400) < 10) * 0.8,
            np.sin(2 * np.pi * 180 * time) * np.linspace(0.02, 0.9, time.size),
            np.sin(2 * np.pi * 900 * time) * 0.2,
        )
        schemes = set()
        compositions = set()
        palettes = set()
        for signal in signals:
            dna = build_visual_dna(analyze_audio_array(np.asarray(signal, dtype=np.float32), sample_rate))
            plan = build_visual_plan(dna)
            params = artistic_parameters(dna, plan, deterministic_seed(dna.fingerprint, 0))
            self.assertGreaterEqual(len(plan.palette), 3)
            self.assertLessEqual(len(plan.palette), 7)
            schemes.add(plan.palette_scheme)
            compositions.add(params.composition)
            palettes.add(plan.palette)
        self.assertGreaterEqual(len(schemes), 4)
        self.assertGreaterEqual(len(compositions), len(COMPOSITIONS) - 1)
        self.assertEqual(len(palettes), len(signals))

    def test_text_first_stage_order(self):
        self.assertLess(STAGE_ORDER.index("building_visual_dna"), STAGE_ORDER.index("creating_song_description"))
        self.assertLess(STAGE_ORDER.index("creating_song_description"), STAGE_ORDER.index("creating_visual_brief"))

    def test_batch_keeps_tracks_separate_survives_errors_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one.wav", "broken.wav", "two.wav"):
                (root / name).write_bytes(name.encode())
            store = DescriptionStore(root / "cache.json")
            first_pipeline = StubPipeline(broken={"broken.wav"})
            first = generate_descriptions(root, pipeline=first_pipeline, store=store)
            self.assertEqual([result.status for result in first].count("error"), 1)
            generated = [result for result in first if result.status == "generated"]
            self.assertEqual(len(generated), 2)
            self.assertEqual(len({result.song_description for result in generated}), 2)
            self.assertNotEqual(generated[0].fingerprint, generated[1].fingerprint)

            second_pipeline = StubPipeline(broken={"broken.wav"})
            second = generate_descriptions(root, pipeline=second_pipeline, store=DescriptionStore(root / "cache.json"))
            self.assertEqual([result.status for result in second].count("cached"), 2)
            self.assertEqual(second_pipeline.calls, ["broken.wav"])

            selected = generate_descriptions(root / "one.wav", pipeline=StubPipeline(), store=store, regenerate=True)
            self.assertEqual(selected[0].status, "generated")


if __name__ == "__main__":
    unittest.main()
