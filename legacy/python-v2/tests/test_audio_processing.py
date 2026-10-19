import inspect
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from easy_music_process import normalize_music_file


LOUDNESS_STATS = {
    "input_i": "-19.10",
    "input_tp": "-4.20",
    "input_lra": "5.00",
    "input_thresh": "-29.10",
    "target_offset": "0.10",
}


class AudioProcessingTests(unittest.TestCase):
    def test_neutral_settings_do_not_build_hidden_processing_filters(self):
        self.assertEqual(normalize_music_file.build_preprocessing_filters(), ())

    def test_filters_are_added_only_when_explicitly_enabled(self):
        filters = normalize_music_file.build_preprocessing_filters(
            highpass_hz=35,
            lowpass_hz=17500,
            denoise=True,
            bass_gain=2,
        )
        self.assertTrue(filters[0].startswith("highpass="))
        self.assertTrue(filters[1].startswith("lowpass="))
        self.assertTrue(any(item.startswith("afftdn=") for item in filters))
        self.assertTrue(any(item.startswith("bass=") for item in filters))

    def test_explicit_format_conversion_is_part_of_the_measured_chain(self):
        filters = normalize_music_file.build_preprocessing_filters(
            source_sample_rate=96000,
            output_sample_rate=48000,
            source_channels=2,
            output_channels=1,
        )
        self.assertEqual(filters, ("pan=mono|c0=0.5*c0+0.5*c1", "aresample=48000"))

    def test_first_pass_places_the_processing_chain_before_loudnorm(self):
        stderr = "prefix\n" + json.dumps(LOUDNESS_STATS) + "\nsuffix"
        with mock.patch.object(
            normalize_music_file.subprocess,
            "run",
            return_value=mock.Mock(stderr=stderr),
        ) as run:
            normalize_music_file.loudnorm_stats(
                "song.wav", -14, -1.5, 11, ("bass=g=2", "acompressor=ratio=2")
            )
        command = run.call_args.args[0]
        audio_filter = command[command.index("-af") + 1]
        self.assertEqual(
            audio_filter,
            "bass=g=2,acompressor=ratio=2,loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
        )

    def test_second_pass_reuses_the_exact_chain_and_has_no_default_final_gain(self):
        chain = ("bass=g=2", "acompressor=ratio=2")
        with (
            mock.patch.object(
                normalize_music_file,
                "output_audio_options",
                return_value=(["-q:a", "0", "-ar", "44100", "-ac", "2"], 44100, 2),
            ),
            mock.patch.object(normalize_music_file, "run") as run,
        ):
            normalize_music_file.normalize_file(
                "song.wav", "result.mp3", LOUDNESS_STATS, -14, -1.5, 11, 1.0,
                preprocessing_filters=chain,
            )
        command = run.call_args.args[0]
        audio_filter = command[command.index("-af") + 1]
        self.assertTrue(audio_filter.startswith("bass=g=2,acompressor=ratio=2,loudnorm="))
        self.assertNotIn("volume=", audio_filter)
        self.assertLess(audio_filter.index("loudnorm="), audio_filter.index("alimiter="))
        self.assertIn("level=false", audio_filter)

    def test_safe_defaults_are_exposed_by_the_processing_api(self):
        defaults = {
            name: parameter.default
            for name, parameter in inspect.signature(normalize_music_file.normalize_music).parameters.items()
        }
        self.assertEqual(defaults["final_gain"], 1.0)
        self.assertFalse(defaults["denoise"])
        self.assertEqual(defaults["denoise_mode"], "auto")
        self.assertEqual(defaults["highpass_hz"], 0.0)
        self.assertEqual(defaults["lowpass_hz"], 0.0)
        self.assertEqual(defaults["sample_rate"], "source")
        self.assertEqual(defaults["channels"], "source")

    def test_output_options_preserve_supported_source_rate_and_mono(self):
        with mock.patch.object(
            normalize_music_file,
            "source_audio_properties",
            return_value={"sample_rate": 44100, "channels": 1},
        ):
            options, rate, channels = normalize_music_file.output_audio_options("song.wav")
        self.assertEqual(rate, 44100)
        self.assertEqual(channels, 1)
        self.assertEqual(options[-4:], ["-ar", "44100", "-ac", "1"])

    def test_auto_denoise_only_selects_a_clear_stationary_noise_floor(self):
        rng = np.random.default_rng(7)
        quiet_noise = rng.normal(0, 0.025, 400 * 60).astype("<f4")
        time = np.arange(400 * 40, dtype=np.float32) / 8000
        loud_signal = (np.sin(2 * np.pi * 330 * time) * 0.35).astype("<f4")
        with mock.patch.object(
            normalize_music_file.subprocess,
            "check_output",
            return_value=np.concatenate((quiet_noise, loud_signal)).tobytes(),
        ):
            detected = normalize_music_file.detect_stationary_noise("song.wav")
        self.assertTrue(detected["apply"])

        with mock.patch.object(
            normalize_music_file.subprocess,
            "check_output",
            return_value=np.zeros(400 * 20, dtype="<f4").tobytes(),
        ):
            silent = normalize_music_file.detect_stationary_noise("song.wav")
        self.assertFalse(silent["apply"])

    def test_real_processing_preserves_source_rate_and_channels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            output = root / "output"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=90:sample_rate=44100:duration=4",
                    "-ac", "1", str(source),
                ],
                check=True,
            )
            normalize_music_file.normalize_music(
                source,
                output,
                denoise_mode="off",
                bass_gain=6,
                compressor=True,
                compressor_threshold=-24,
                compressor_ratio=2.5,
            )
            result = output / "source.mp3"
            self.assertTrue(result.is_file())
            properties = normalize_music_file.source_audio_properties(result)
            self.assertEqual(properties, {"sample_rate": 44100, "channels": 1})
            after = normalize_music_file.loudnorm_stats(result, -14, -1.5, 11)
            self.assertAlmostEqual(float(after["input_i"]), -14.0, delta=0.35)

    def test_ab_preview_is_loudness_matched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=4",
                    str(source),
                ],
                check=True,
            )
            filters = normalize_music_file.build_preprocessing_filters(treble_gain=5)
            original, processed = normalize_music_file.create_ab_preview(source, root / "preview", filters)
            for path in (original, processed):
                self.assertTrue(path.is_file())
                stats = normalize_music_file.loudnorm_stats(path, -18, -2, 11)
                self.assertAlmostEqual(float(stats["input_i"]), -18.0, delta=0.35)


if __name__ == "__main__":
    unittest.main()
