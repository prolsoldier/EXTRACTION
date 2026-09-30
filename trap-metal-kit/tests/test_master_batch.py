"""Tests for tools/master_batch.py (needs numpy, scipy, soundfile, pyloudnorm)."""
import contextlib
import io
import pathlib
import shutil
import sys
import tempfile
import unittest

try:
    import numpy as np
    import pyloudnorm as pyln
    import soundfile as sf
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))
    import master_batch as mb
    HAVE_LIBS = True
except ImportError:  # pragma: no cover
    HAVE_LIBS = False

RATE = 44100


def synth_mix(seconds=6, seed=3, peak=0.25):
    """Stereo 'mix': band-limited noise bed, a bass sine and a few loud spikes."""
    rng = np.random.default_rng(seed)
    n = seconds * RATE
    t = np.arange(n) / RATE
    bed = rng.normal(0, 0.05, (n, 2))
    bass = 0.3 * np.sin(2 * np.pi * 55 * t)[:, None]
    audio = bed + bass
    audio[rng.integers(0, n, 30)] *= 4
    return audio * (peak / np.max(np.abs(audio)))


@unittest.skipUnless(HAVE_LIBS, "numpy/scipy/soundfile/pyloudnorm not installed")
class MasterTest(unittest.TestCase):
    def measure(self, audio):
        return pyln.Meter(RATE).integrated_loudness(audio)  # independent meter instance

    def test_limiter_never_exceeds_ceiling(self):
        audio = synth_mix(peak=1.0) * 3
        out = mb.limit(audio, RATE, -1.0)
        self.assertLessEqual(np.max(np.abs(out)), 10 ** (-1.0 / 20) + 1e-9)

    def test_limiter_leaves_quiet_audio_untouched(self):
        audio = synth_mix(peak=0.1)
        np.testing.assert_allclose(mb.limit(audio, RATE, -1.0), audio, atol=1e-12)

    def test_master_hits_streaming_target_within_tolerance_and_true_peak_ceiling(self):
        out, info = mb.master(synth_mix(), RATE, -14.0, -1.0)
        self.assertAlmostEqual(self.measure(out), -14.0, delta=0.2)
        self.assertLessEqual(mb.true_peak_db(out, RATE), -1.0 + 0.05)
        self.assertTrue(info["reached"])

    def test_master_quiet_source_is_boosted(self):
        quiet = synth_mix(peak=0.02)
        out, info = mb.master(quiet, RATE, -14.0, -1.0)
        self.assertGreater(info["gain_db"], 10)
        self.assertAlmostEqual(self.measure(out), -14.0, delta=0.3)

    def test_loud_target_keeps_the_ceiling(self):
        out, info = mb.master(synth_mix(peak=0.9), RATE, -9.0, -1.0)
        self.assertLessEqual(mb.true_peak_db(out, RATE), -1.0 + 0.05)
        self.assertLess(abs(self.measure(out) - -9.0), 1.5)  # may not hit exactly; must be close and safe

    def test_silence_is_handled(self):
        out, info = mb.master(np.zeros((RATE, 2)), RATE, -14.0)
        self.assertFalse(info["reached"])
        self.assertEqual(float(np.max(np.abs(out))), 0.0)

    def test_prep_trims_silence_highpasses_and_sets_peak(self):
        t = np.arange(RATE) / RATE
        voice = 0.5 * np.sin(2 * np.pi * 440 * t)
        rumble = 0.3 * np.sin(2 * np.pi * 20 * t)
        take = np.concatenate([np.zeros(2 * RATE), voice + rumble, np.zeros(3 * RATE)])[:, None]
        out, info = mb.prep_vocal(take, RATE)
        self.assertLess(len(out), 1.3 * RATE)                        # ~1 s voice + 2 * 50 ms pad
        self.assertGreater(len(out), 0.9 * RATE)
        self.assertAlmostEqual(20 * np.log10(np.max(np.abs(out))), -6.0, delta=0.05)
        spectrum = np.abs(np.fft.rfft(out[:, 0]))
        freqs = np.fft.rfftfreq(len(out), 1 / RATE)
        self.assertGreater(spectrum[np.argmin(abs(freqs - 440))], 10 * spectrum[np.argmin(abs(freqs - 20))])

    def test_prep_silent_take_does_not_crash(self):
        out, info = mb.prep_vocal(np.zeros((RATE, 1)), RATE)
        self.assertEqual(info["note"], "silent")


@unittest.skipUnless(HAVE_LIBS, "numpy/scipy/soundfile/pyloudnorm not installed")
class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "in").mkdir()
        sf.write(str(self.tmp / "in" / "a.wav"), synth_mix(), RATE, subtype="PCM_16")

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = mb.main(list(argv))
        return code, out.getvalue()

    def test_master_writes_24_bit_file_and_reports(self):
        code, text = self.run_cli("master", str(self.tmp / "in"), "-o", str(self.tmp / "out"), "--preset", "streaming")
        self.assertEqual(code, 0)
        info = sf.info(str(self.tmp / "out" / "a_master.wav"))
        self.assertEqual(info.subtype, "PCM_24")
        self.assertIn("a.wav:", text)
        self.assertIn("LUFS", text)

    def test_prep_mode_writes_prepped_file(self):
        code, text = self.run_cli("prep", str(self.tmp / "in" / "a.wav"), "-o", str(self.tmp / "out"))
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "out" / "a_prep.wav").is_file())

    def test_missing_input_is_an_error(self):
        code, text = self.run_cli("master", str(self.tmp / "nope"), "-o", str(self.tmp / "out"))
        self.assertEqual(code, 1)
        self.assertIn("not found", text)

    def test_measure_reports_without_writing_or_changing_anything(self):
        before = (self.tmp / "in" / "a.wav").read_bytes()
        code, text = self.run_cli("measure", str(self.tmp / "in"))
        self.assertEqual(code, 0)
        self.assertIn("a.wav:", text)
        self.assertIn("LUFS", text)
        self.assertIn("dBTP", text)
        self.assertIn("1 file(s) checked", text)
        self.assertEqual((self.tmp / "in" / "a.wav").read_bytes(), before)
        self.assertFalse((self.tmp / "out").exists())

    def test_measure_warns_on_target_miss_and_true_peak_and_strict_gates(self):
        code, text = self.run_cli("measure", str(self.tmp / "in"), "--lufs", "-9")
        self.assertEqual(code, 0)                                    # warnings only, not strict
        self.assertIn("WARN", text)
        self.assertIn("from the -9.0 target", text)
        code, text = self.run_cli("measure", str(self.tmp / "in"), "--lufs", "-9", "--strict")
        self.assertEqual(code, 2)
        loud = synth_mix(peak=0.999)
        sf.write(str(self.tmp / "in" / "hot.wav"), loud, RATE, subtype="PCM_24")
        code, text = self.run_cli("measure", str(self.tmp / "in" / "hot.wav"), "--ceiling", "-6", "--strict")
        self.assertEqual(code, 2)
        self.assertIn("over the -6.0 ceiling", text)

    def test_measure_passes_a_file_that_was_mastered_to_the_target(self):
        self.run_cli("master", str(self.tmp / "in"), "-o", str(self.tmp / "out"), "--lufs", "-12")
        code, text = self.run_cli("measure", str(self.tmp / "out"), "--lufs", "-12", "--strict")
        self.assertEqual(code, 0, text)
        self.assertNotIn("WARN", text)

    def test_measure_flags_silence(self):
        sf.write(str(self.tmp / "in" / "quiet.wav"), np.zeros((RATE, 2)), RATE, subtype="PCM_16")
        code, text = self.run_cli("measure", str(self.tmp / "in" / "quiet.wav"), "--strict")
        self.assertEqual(code, 2)
        self.assertIn("silent or too short", text)

    def test_master_still_requires_an_output_folder(self):
        code, text = self.run_cli("master", str(self.tmp / "in"))
        self.assertEqual(code, 1)
        self.assertIn("-o/--output is required", text)

    def test_custom_lufs_overrides_preset(self):
        code, text = self.run_cli("master", str(self.tmp / "in"), "-o", str(self.tmp / "out"), "--lufs", "-16")
        self.assertEqual(code, 0)
        audio, _ = sf.read(str(self.tmp / "out" / "a_master.wav"), always_2d=True)
        self.assertAlmostEqual(pyln.Meter(RATE).integrated_loudness(audio), -16.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
