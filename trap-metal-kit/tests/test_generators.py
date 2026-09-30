"""Tests for tools/gen_wavetables.py and tools/gen_808.py."""
import contextlib
import io
import math
import pathlib
import shutil
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

import gen_808  # noqa: E402
import gen_wavetables  # noqa: E402

FRAME = gen_wavetables.FRAME


class WavetableTest(unittest.TestCase):
    def frames_of(self, samples):
        return [samples[i:i + FRAME] for i in range(0, len(samples), FRAME)]

    def test_every_preset_has_whole_frames_normalised_and_dc_free(self):
        for name in gen_wavetables.PRESETS:
            with self.subTest(preset=name):
                frames = self.frames_of(gen_wavetables.generate(name, frames=6))
                self.assertEqual(len(frames), 6)
                for frame in frames:
                    self.assertEqual(len(frame), FRAME)
                    self.assertAlmostEqual(max(abs(s) for s in frame), gen_wavetables.PEAK, places=6)
                    self.assertLess(abs(sum(frame) / FRAME), 1e-9)

    def test_frames_actually_morph(self):
        for name in gen_wavetables.PRESETS:
            with self.subTest(preset=name):
                frames = self.frames_of(gen_wavetables.generate(name, frames=8))
                difference = sum(abs(a - b) for a, b in zip(frames[0], frames[-1])) / FRAME
                self.assertGreater(difference, 0.01)

    def test_output_is_deterministic(self):
        self.assertEqual(gen_wavetables.generate("vowel_morph", 4), gen_wavetables.generate("vowel_morph", 4))

    def test_fold_is_identity_inside_range_and_reflects_outside(self):
        self.assertAlmostEqual(gen_wavetables.fold(0.3), 0.3)
        self.assertAlmostEqual(gen_wavetables.fold(1.5), 0.5)
        self.assertAlmostEqual(gen_wavetables.fold(-1.5), -0.5)

    def test_crushed_lead_ends_with_few_levels(self):
        first, *_, last = self.frames_of(gen_wavetables.generate("crushed_lead", frames=8))
        self.assertLessEqual(len({round(s, 6) for s in last}), 8)
        self.assertGreater(len({round(s, 6) for s in first}), 50)

    def test_needs_at_least_two_frames(self):
        with self.assertRaises(ValueError):
            gen_wavetables.generate("rage_fold", frames=1)

    def test_cli_writes_readable_16bit_mono_wav(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gen_wavetables.main(["--preset", "all", "-d", str(tmp), "--frames", "4"]), 0)
        self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["crushed_lead.wav", "rage_fold.wav", "vowel_morph.wav"])
        with wave.open(str(tmp / "rage_fold.wav")) as handle:
            self.assertEqual((handle.getnchannels(), handle.getsampwidth(), handle.getnframes()), (1, 2, 4 * FRAME))


class Gen808Test(unittest.TestCase):
    def test_length_peak_and_finite(self):
        samples = gen_808.make_808(note=33, seconds=1.0)
        self.assertEqual(len(samples), gen_808.SAMPLE_RATE)
        self.assertAlmostEqual(max(abs(s) for s in samples), gen_808.PEAK, places=6)
        self.assertTrue(all(math.isfinite(s) for s in samples))
        self.assertLess(abs(samples[-1]), 1e-3)  # faded out, no click at the end

    def test_settled_pitch_matches_requested_note(self):
        for note in (28, 33, 40):
            with self.subTest(note=note):
                samples = gen_808.make_808(note=note, seconds=1.2)
                start, end = int(0.3 * gen_808.SAMPLE_RATE), int(1.0 * gen_808.SAMPLE_RATE)
                window = samples[start:end]
                rising = sum(1 for a, b in zip(window, window[1:]) if a < 0 <= b)
                measured = rising / ((end - start) / gen_808.SAMPLE_RATE)
                expected = 440 * 2 ** ((note - 69) / 12)
                self.assertAlmostEqual(measured / expected, 1.0, delta=0.05)

    def test_pitch_starts_higher_than_it_settles(self):
        samples = gen_808.make_808(note=33, seconds=0.6, click=0)
        sr = gen_808.SAMPLE_RATE

        def crossings(a, b):
            w = samples[int(a * sr):int(b * sr)]
            return sum(1 for x, y in zip(w, w[1:]) if x < 0 <= y) / (b - a)

        self.assertGreater(crossings(0.005, 0.045), crossings(0.4, 0.6) * 1.15)

    def test_more_drive_squares_off_the_wave(self):
        # RMS/peak is 0.707 for a sine and approaches 1.0 as the wave is clipped towards a square,
        # so a rising ratio means the saturator is adding harmonics.
        def rms_over_peak(drive):
            s = gen_808.make_808(note=33, seconds=0.5, drive_db=drive, click=0, decay=5.0)[4000:4000 + 4410]
            return math.sqrt(sum(x * x for x in s) / len(s)) / max(abs(x) for x in s)
        self.assertLess(rms_over_peak(0), 0.8)
        self.assertGreater(rms_over_peak(30), rms_over_peak(0) + 0.1)

    def test_deterministic_and_seed_changes_click_only(self):
        a = gen_808.make_808(seconds=0.2, seed=1)
        self.assertEqual(a, gen_808.make_808(seconds=0.2, seed=1))
        self.assertNotEqual(a, gen_808.make_808(seconds=0.2, seed=2))
        self.assertEqual(gen_808.make_808(seconds=0.2, click=0, seed=1), gen_808.make_808(seconds=0.2, click=0, seed=9))

    def test_cli_writes_one_file_per_note_and_rejects_bad_notes(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gen_808.main(["--note", "24", "33", "--seconds", "0.2", "-d", str(tmp)]), 0)
        self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["808_24.wav", "808_33.wav"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gen_808.main(["--note", "200", "-d", str(tmp)]), 1)


if __name__ == "__main__":
    unittest.main()
