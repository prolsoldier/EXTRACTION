"""Checks the maths of the two JSFX plugins through their Python mirror (tests/jsfx_model.py)."""
import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from jsfx_model import SR, Crunch, Grit  # noqa: E402

N = 48000


def sine(freq, n, amp=1.0):
    return [amp * math.sin(2 * math.pi * freq * i / SR) for i in range(n)]


def rms(values):
    return math.sqrt(sum(v * v for v in values) / len(values))


def magnitude_at(signal, freq):
    re = sum(x * math.cos(2 * math.pi * freq * i / SR) for i, x in enumerate(signal))
    im = sum(x * math.sin(2 * math.pi * freq * i / SR) for i, x in enumerate(signal))
    return 2 * math.hypot(re, im) / len(signal)


def db(ratio):
    return 20 * math.log10(ratio)


class CrunchTest(unittest.TestCase):
    def test_output_stays_finite_at_extreme_settings(self):
        for amp in (0.1, 1.0, 4.0):  # up to +12 dBFS input
            for kw in (dict(), dict(drive_db=48, asym=1, fold=1, crush=1, out_db=12),
                       dict(keep=0, mix=50), dict(keep=400, drive_db=0), dict(drive_db=0, asym=0)):
                plugin = Crunch(**kw)
                out = [plugin.tick(x) for x in sine(55, 12000, amp)]
                self.assertTrue(all(math.isfinite(v) for v in out), (amp, kw))
                self.assertLess(max(abs(v) for v in out), 100)

    def test_asymmetric_shaper_dc_is_removed(self):
        plugin = Crunch(asym=1.0, fold=0.5, crush=0.5, drive_db=30, keep=0)
        out = [plugin.tick(x) for x in sine(110, N, 0.7)][N // 2:]
        self.assertLess(abs(sum(out) / len(out)), 1e-4)

    def test_crossover_bands_sum_to_a_flat_response(self):
        for freq in (30, 60, 120, 240, 1000, 5000):
            plugin = Crunch(keep=120, drive_db=0, asym=0, mix=100, out_db=0, tone=20000)
            low, high, source = [], [], sine(freq, N, 0.01)
            for x in source:
                plugin.tick(x)
                low.append(plugin.last["low"])
                high.append(plugin.last["hi"])
            total = [a + b for a, b in zip(low, high)][N // 2:]
            self.assertAlmostEqual(db(rms(total) / rms(source[N // 2:])), 0.0, delta=0.05, msg=f"{freq} Hz")

    def test_high_band_is_steeply_attenuated_below_the_crossover(self):
        plugin = Crunch(keep=200, drive_db=0, asym=0, mix=100, out_db=0, tone=20000)
        source, high = sine(40, N, 0.01), []
        for x in source:
            plugin.tick(x)
            high.append(plugin.last["hi"])
        self.assertLess(db(rms(high[N // 2:]) / rms(source[N // 2:])), -40)

    def test_keep_lows_protects_the_sub_from_heavy_drive(self):
        def sub_rms(keep):
            plugin = Crunch(keep=keep, mix=100, drive_db=40, out_db=0, tone=20000)
            return rms([plugin.tick(x) for x in sine(40, N, 0.5)][N // 2:])
        clean_sine_rms = 0.5 / math.sqrt(2)
        self.assertLess(sub_rms(200), clean_sine_rms * 1.3)   # still (nearly) a clean sine
        self.assertGreater(sub_rms(0), clean_sine_rms * 2.0)  # without the split it is crushed to a square

    def test_crush_quantises_to_few_levels(self):
        plugin, levels = Crunch(crush=1.0, drive_db=0, asym=0, keep=0), set()
        for x in sine(200, 4000, 0.9):
            plugin.tick(x)
            levels.add(round(plugin.last["pre_tone"], 6))
        self.assertLessEqual(levels, {-1.0, -0.5, 0.0, 0.5, 1.0})
        self.assertLessEqual(len(levels), 5)


class GritTest(unittest.TestCase):
    def wet(self, freq, **kw):
        plugin = Grit(width_ms=0, **kw)
        return [plugin.tick(x, x)[0] for x in sine(freq, N, 0.5)][N // 2:]

    def test_low_cut_removes_rumble_and_leaves_the_voice_alone(self):
        ref = lambda f: rms(sine(f, N // 2, 0.5))  # noqa: E731
        self.assertLess(db(rms(self.wet(20, blend=0)) / ref(20)), -20)
        self.assertAlmostEqual(db(rms(self.wet(1000, blend=0)) / ref(1000)), 0.0, delta=0.5)

    def test_grit_blend_adds_odd_harmonics_in_proportion(self):
        def third(blend):
            plugin = Grit(blend=blend, width_ms=0)
            out = [plugin.tick(x, x)[0] for x in sine(500, N, 0.3)][N // 2:N // 2 + 9600]  # whole cycles
            return magnitude_at(out, 1500)
        self.assertLess(third(0), 1e-6)
        self.assertGreater(third(100), 0.05)
        self.assertAlmostEqual(third(50) * 2, third(100), delta=0.01)

    def test_haas_delays_only_the_right_channel_by_the_requested_time(self):
        plugin = Grit(width_ms=12)
        results = [plugin.tick(x, x) for x in [1.0] + [0.0] * 2000]
        left = next(i for i, (a, _) in enumerate(results) if abs(a) > 1e-3)
        right = next(i for i, (_, b) in enumerate(results) if abs(b) > 1e-3)
        self.assertEqual(right - left, math.floor(12 * 0.001 * SR))

    def test_no_width_means_no_delay(self):
        plugin = Grit(width_ms=0)
        results = [plugin.tick(x, x) for x in [1.0] + [0.0] * 50]
        self.assertEqual(next(i for i, (a, _) in enumerate(results) if abs(a) > 1e-3),
                         next(i for i, (_, b) in enumerate(results) if abs(b) > 1e-3))

    def test_output_stays_finite_at_extreme_settings(self):
        plugin = Grit(drive_db=48, blend=100, width_ms=30, out_db=12)
        out = [v for x in sine(300, 12000, 4.0) for v in plugin.tick(x, x)]
        self.assertTrue(all(math.isfinite(v) for v in out))


if __name__ == "__main__":
    unittest.main()
