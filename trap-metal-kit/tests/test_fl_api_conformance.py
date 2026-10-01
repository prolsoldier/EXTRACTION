"""Checks the FL scripts against Image-Line's published API stubs (pip install fl-studio-api-stubs).

The other FL tests run the scripts against stand-ins written for this kit. This is the independent half: every FL
function the scripts call must exist in the real API and accept the arguments it is given. Runs the checker in a
subprocess so the other tests' fake `mixer` / `playlist` modules cannot get in the way. Skipped when the stubs
package is not installed.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parent.parent
CHECKER = ROOT / "tools" / "check_fl_api.py"


def run_checker(*args):
    return subprocess.run([sys.executable, str(CHECKER), *args], capture_output=True, text=True, cwd=str(ROOT))


def stubs_available():
    return run_checker(str(ROOT / "fl-studio" / "device_PluginProbe.py")).returncode != 2


@unittest.skipUnless(stubs_available(), "pip install fl-studio-api-stubs to run the FL API conformance check")
class ConformanceTest(unittest.TestCase):
    def test_every_script_only_uses_real_fl_api(self):
        result = run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("TrapMetalKit", "TrapDJ", "VocalSetup", "PluginProbe", "PinkTheme"):
            self.assertIn("device_%s.py" % name, result.stdout)

    def _check_text(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "device_Bad.py"
            path.write_text(source, encoding="utf-8")
            return run_checker(str(path))

    def test_checker_catches_a_function_that_does_not_exist(self):
        result = self._check_text("import mixer\nmixer.setTrackNamee(1, 'x')\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("mixer.setTrackNamee does not exist", result.stdout)

    def test_checker_catches_wrong_arguments(self):
        result = self._check_text("import mixer\nmixer.setRouteToLevel(1, 2)\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing a required argument: 'level'", result.stdout)

    def test_checker_catches_unknown_constants(self):
        result = self._check_text("import midi\nx = midi.TLC_Nope\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("midi.TLC_Nope does not exist", result.stdout)

    def test_checker_catches_misspelled_callbacks(self):
        result = self._check_text("def OnNoteon(event):\n    pass\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("OnNoteon() is not a callback FL calls", result.stdout)


class CheckerWithoutStubsTest(unittest.TestCase):
    def test_exit_status_two_means_stubs_missing(self):
        # Importing the checker with no stubs must not crash; it reports and exits 2.
        code = ("import sys; sys.path.insert(0, %r); import check_fl_api as c; "
                "c.load_stubs = lambda: None; sys.exit(c.main([%r]))" % (str(ROOT / "tools"), str(ROOT / "fl-studio" / "device_TrapDJ.py")))
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("pip install fl-studio-api-stubs", result.stderr)


if __name__ == "__main__":
    unittest.main()
