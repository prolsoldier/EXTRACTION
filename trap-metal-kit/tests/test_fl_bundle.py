"""Loads fl-studio/device_TrapMetalKit.py (all four scripts on one MIDI input) against stub FL modules.

Proves the dispatching, the press-twice guard, the conflict warnings, that the embedded scripts are the real ones,
and that one part failing cannot take the others down. It cannot prove FL Studio's behaviour.
"""
import contextlib
import importlib.util
import io
import pathlib
import sys
import types
import unittest
from unittest import mock

TOOLS = pathlib.Path(__file__).parent.parent / "tools"
FL_DIR = pathlib.Path(__file__).parent.parent / "fl-studio"
BUNDLE = FL_DIR / "device_TrapMetalKit.py"
sys.path.insert(0, str(TOOLS))
import build_fl_bundle  # noqa: E402


class Event:
    def __init__(self, data1, data2=100):
        self.data1, self.data2, self.handled = data1, data2, False


class Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now


class FLStubs:
    """Records every call the scripts make into FL, in one list."""

    def __init__(self):
        self.calls = []
        record = lambda name: (lambda *a, **k: self.calls.append((name,) + a))
        self.names = {i: "Master" if i == 0 else "Insert %d" % i for i in range(127)}
        self.armed = set()
        self.plugin_slots = {}
        self.fail_triggers = False

        def trigger(*a):
            if self.fail_triggers:
                raise RuntimeError("boom")
            self.calls.append(("triggerLiveClip",) + a)

        self.modules = {
            "midi": types.SimpleNamespace(TLC_TrackSnap=0, TLC_GlobalSnap=8, TLC_NoSnap=16, TLC_Fill=2, TLC_MuteOthers=1),
            "playlist": types.SimpleNamespace(
                triggerLiveClip=trigger, getPerformanceModeState=lambda: True, setTrackColor=record("playlist.setTrackColor")),
            "mixer": types.SimpleNamespace(
                trackCount=lambda: 127, getTrackName=lambda i: self.names[i],
                setTrackName=lambda i, n: (self.names.__setitem__(i, n), self.calls.append(("setTrackName", i, n))),
                setTrackColor=record("mixer.setTrackColor"), setRouteTo=record("setRouteTo"),
                setRouteToLevel=record("setRouteToLevel"), afterRoutingChanged=record("afterRoutingChanged"),
                isTrackArmed=lambda i: i in self.armed, armTrack=lambda i: (self.armed.add(i), self.calls.append(("armTrack", i))),
                setTrackVolume=record("setTrackVolume")),
            "channels": types.SimpleNamespace(channelCount=lambda g=0: 3, setChannelColor=record("setChannelColor")),
            "patterns": types.SimpleNamespace(patternCount=lambda: 2, setPatternColor=record("setPatternColor")),
            "plugins": types.SimpleNamespace(
                isValid=lambda t, s=-1, g=False: (t, s) in self.plugin_slots,
                getPluginName=lambda t, s=-1, u=False, g=False: self.plugin_slots[(t, s)],
                getParamCount=lambda t, s=-1, g=False: 1,
                getParamName=lambda p, t, s=-1, g=False: "Gain",
                getParamValue=lambda p, t, s=-1, g=False: 0.5,
                getParamValueString=lambda p, t, s=-1, g=False: "0 dB"),
        }

    def of(self, name):
        return [c for c in self.calls if c[0] == name]


class BundleCase(unittest.TestCase):
    def setUp(self):
        self.fl = FLStubs()
        patcher = mock.patch.dict(sys.modules, self.fl.modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = io.StringIO()
        self.bundle = self.load()
        self.clock = Clock()
        self.bundle.time = self.clock

    def load(self):
        spec = importlib.util.spec_from_file_location("device_TrapMetalKit_under_test", BUNDLE)
        module = importlib.util.module_from_spec(spec)
        with contextlib.redirect_stdout(self.out):
            spec.loader.exec_module(module)
        return module

    def reload_parts(self):
        with contextlib.redirect_stdout(self.out):
            self.bundle._load_all()

    def press(self, note, velocity=100, fn=None):
        event = Event(note, velocity)
        with contextlib.redirect_stdout(self.out):
            (fn or self.bundle.OnNoteOn)(event)
        return event

    def printed(self):
        return self.out.getvalue()


class DefaultMapTest(BundleCase):
    def test_all_four_parts_load_and_announce_the_key_map(self):
        with contextlib.redirect_stdout(self.out):
            self.bundle.OnInit()
        text = self.printed()
        self.assertEqual(sorted(self.bundle._modules), ["PinkTheme", "PluginProbe", "TrapDJ", "VocalSetup"])
        for expected in ("ready (build", "notes 36-67 launch clips", "68-71 stop decks", "CC 1 crossfades mixer inserts 10 and 11",
                         "note 72 lists every plugin", "note 73 audits", "note 74 builds", "note 75 repaints"):
            self.assertIn(expected, text)
        self.assertNotIn("WARNING", text)

    def test_default_layout_has_no_conflicts(self):
        self.assertEqual(self.bundle.find_conflicts(), [])

    def test_dj_keys_launch_clips_and_stop_decks(self):
        first, last, stop = self.press(36), self.press(67), self.press(68)
        self.assertTrue(first.handled and last.handled and stop.handled)
        self.assertEqual(self.fl.of("triggerLiveClip"), [("triggerLiveClip", 1, 0, 0), ("triggerLiveClip", 4, 7, 0),
                                                         ("triggerLiveClip", 1, -1, 2)])

    def test_crossfader_uses_inserts_10_and_11_not_the_vocal_inserts(self):
        self.press(1, 127, self.bundle.OnControlChange)
        touched = {c[1] for c in self.fl.of("setTrackVolume")}
        self.assertEqual(touched, {10, 11})

    def test_notes_nobody_owns_pass_through(self):
        event = self.press(90)
        self.assertFalse(event.handled)
        self.assertEqual(self.fl.calls, [])
        self.assertEqual(self.fl.of("triggerLiveClip"), [])

    def test_probe_key_lists_plugins_read_only(self):
        self.fl.plugin_slots = {(0, 0): "Ozone 12"}
        event = self.press(72)
        self.assertTrue(event.handled)
        self.assertIn("Ozone 12", self.printed())
        self.assertEqual(self.fl.of("setTrackName") + self.fl.of("setRouteTo"), [])

    def test_audit_key_reports_missing_plugins_and_changes_nothing(self):
        before = len(self.fl.calls)
        event = self.press(73)
        self.assertTrue(event.handled)
        self.assertIn("MISSING", self.printed())
        self.assertEqual(len(self.fl.calls), before)

    def test_start_up_paints_the_pink_theme(self):
        with contextlib.redirect_stdout(self.out):
            self.bundle.OnInit()
        self.assertEqual(len(self.fl.of("setChannelColor")), 3)
        self.assertEqual(len(self.fl.of("setPatternColor")), 2)

    def test_on_init_can_run_twice(self):
        with contextlib.redirect_stdout(self.out):
            self.bundle.OnInit()
            self.bundle.OnInit()
        self.assertEqual(len(self.fl.of("setChannelColor")), 6)   # painted once per init, no exception


class GuardTest(BundleCase):
    def test_setup_needs_a_second_press(self):
        first = self.press(74)
        self.assertTrue(first.handled)
        self.assertEqual(self.fl.of("setTrackName"), [])
        self.assertIn("press note 74 again within 3 seconds", self.printed())
        self.clock.now += 1.5
        second = self.press(74)
        self.assertTrue(second.handled)
        self.assertEqual([c[2] for c in self.fl.of("setTrackName")][:2], ["VOX MAIN", "VOX DBL L"])
        self.assertEqual(len(self.fl.of("setTrackName")), 8)

    def test_a_slow_second_press_counts_as_a_new_first_press(self):
        self.press(74)
        self.clock.now += 10
        self.press(74)
        self.assertEqual(self.fl.of("setTrackName"), [])

    def test_confirmation_is_used_up_by_running(self):
        self.press(74)
        self.press(74)
        self.fl.names.update({i: "Insert %d" % i for i in range(1, 9)})
        self.fl.calls.clear()
        self.press(74)               # needs confirming again
        self.assertEqual(self.fl.of("setTrackName"), [])

    def test_repaint_is_guarded_too(self):
        self.press(75)
        self.assertEqual(self.fl.of("setChannelColor"), [])
        self.press(75)
        self.assertEqual(len(self.fl.of("setChannelColor")), 3)

    def test_zero_seconds_turns_the_guard_off(self):
        self.bundle.CONFIRM_SECONDS = 0
        self.press(74)
        self.assertEqual(len(self.fl.of("setTrackName")), 8)

    def test_key_release_is_not_a_press(self):
        event = self.press(74, 0)
        self.assertFalse(event.handled)
        self.assertEqual(self.bundle._pending, {})

    def test_read_only_keys_are_never_guarded(self):
        self.press(73)
        self.assertIn("Vocal chain", self.printed())

    def test_release_of_a_command_key_is_swallowed_but_unknown_releases_are_not(self):
        self.assertTrue(self.press(74, 0, self.bundle.OnNoteOff).handled)
        self.assertTrue(self.press(40, 0, self.bundle.OnNoteOff).handled)    # a DJ key
        self.assertFalse(self.press(90, 0, self.bundle.OnNoteOff).handled)


class ConfigTest(BundleCase):
    def test_a_part_can_be_switched_off(self):
        self.bundle.ENABLED["TrapDJ"] = False
        self.reload_parts()
        event = self.press(36)
        self.assertFalse(event.handled)
        self.assertEqual(self.fl.of("triggerLiveClip"), [])
        self.assertNotIn("TrapDJ", self.bundle._modules)

    def test_overrides_reach_settings_that_other_values_are_derived_from(self):
        self.bundle.OVERRIDES["TrapDJ"] = {"FIRST_NOTE": 48, "DECK_A_MIXER": 10, "DECK_B_MIXER": 11}
        self.reload_parts()
        self.assertTrue(self.press(48).handled)
        self.assertEqual(self.fl.of("triggerLiveClip")[-1], ("triggerLiveClip", 1, 0, 0))
        self.press(80)                                                    # 48 + 32 = first stop key now
        self.assertEqual(self.fl.of("triggerLiveClip")[-1], ("triggerLiveClip", 1, -1, 2))

    def test_a_typo_in_an_override_is_reported_not_silently_ignored(self):
        self.bundle.OVERRIDES["PinkTheme"] = {"REPAINT_NOTEE": 99}
        self.reload_parts()
        self.assertIn("PinkTheme has no setting called 'REPAINT_NOTEE'", self.printed())

    def test_unknown_part_names_are_reported(self):
        self.bundle.ENABLED["Nope"] = True
        self.reload_parts()
        self.assertIn("unknown part 'Nope'", self.printed())

    def test_paint_on_start_can_be_turned_off(self):
        self.bundle.OVERRIDES["PinkTheme"]["PAINT_ON_START"] = False
        self.reload_parts()
        with contextlib.redirect_stdout(self.out):
            self.bundle.OnInit()
        self.assertEqual(self.fl.of("setChannelColor"), [])


class ConflictTest(BundleCase):
    def test_deck_inserts_overlapping_the_vocal_layout_are_flagged(self):
        self.bundle.OVERRIDES["TrapDJ"] = {"DECK_A_MIXER": 1, "DECK_B_MIXER": 2}
        self.reload_parts()
        lines = self.bundle.find_conflicts()
        self.assertTrue(any("mixer insert 1 is used by" in l for l in lines), lines)
        with contextlib.redirect_stdout(self.out):
            self.bundle.OnInit()
        self.assertIn("WARNING: mixer insert 1", self.printed())

    def test_a_command_key_inside_the_dj_block_is_flagged(self):
        self.bundle.OVERRIDES["VocalSetup"] = {"SETUP_NOTE": 40}
        self.reload_parts()
        self.assertTrue(any("note 40 is claimed by TrapDJ and VocalSetup SETUP" in l for l in self.bundle.find_conflicts()))

    def test_two_parts_on_the_same_key_are_flagged(self):
        self.bundle.OVERRIDES["PluginProbe"] = {"PROBE_NOTE": 73}
        self.reload_parts()
        self.assertTrue(any(l.startswith("note 73 is claimed by") for l in self.bundle.find_conflicts()))

    def test_when_two_parts_want_a_key_only_the_first_acts(self):
        self.bundle.OVERRIDES["PluginProbe"] = {"PROBE_NOTE": 36}      # 36 is also the first DJ clip
        self.reload_parts()
        event = self.press(36)
        self.assertTrue(event.handled)
        self.assertEqual(self.fl.of("triggerLiveClip"), [("triggerLiveClip", 1, 0, 0)])
        self.assertNotIn("Plugin Probe", self.printed())               # the probe never ran

    def test_disabled_parts_claim_nothing(self):
        self.bundle.ENABLED["VocalSetup"] = False
        self.bundle.OVERRIDES["TrapDJ"] = {"DECK_A_MIXER": 1, "DECK_B_MIXER": 2}
        self.reload_parts()
        self.assertEqual(self.bundle.find_conflicts(), [])


class FaultIsolationTest(BundleCase):
    def test_one_failing_part_does_not_stop_the_others_and_is_reported_once(self):
        self.fl.fail_triggers = True
        self.press(36)
        self.press(36)
        self.assertEqual(self.printed().count("TrapDJ.OnNoteOn failed"), 1)
        self.press(1, 127, self.bundle.OnControlChange)         # same part, different callback: still works
        self.assertEqual(len(self.fl.of("setTrackVolume")), 2)
        self.press(73)                                            # other parts untouched
        self.assertIn("Vocal chain", self.printed())

    def test_a_part_that_will_not_load_is_switched_off_and_the_rest_run(self):
        original = dict(self.bundle._SOURCES)
        self.bundle._SOURCES["PluginProbe"] = "this is not python ("
        self.reload_parts()
        self.assertIn("PluginProbe could not be loaded", self.printed())
        self.assertNotIn("PluginProbe", self.bundle._modules)
        self.assertTrue(self.press(36).handled)
        self.bundle._SOURCES.update(original)


class BuildIntegrityTest(unittest.TestCase):
    def test_committed_bundle_matches_a_fresh_build(self):
        self.assertEqual(BUNDLE.read_text(encoding="utf-8"), build_fl_bundle.build(),
                         "run: python3 tools/build_fl_bundle.py")

    def test_embedded_sources_are_the_standalone_scripts(self):
        text = BUNDLE.read_text(encoding="utf-8")
        for name in build_fl_bundle.SECTIONS:
            embedded = build_fl_bundle.read_section(name)
            self.assertIn(embedded, text)
            standalone = (FL_DIR / ("device_%s.py" % name)).read_text(encoding="utf-8")
            self.assertEqual(embedded.replace("# name: ", "# name="), standalone.replace("\r\n", "\n"))

    def test_fl_sees_exactly_one_name_header(self):
        headers = [l for l in BUNDLE.read_text(encoding="utf-8").split("\n")
                   if l.lstrip("# ").lower().startswith(("name=", "url=", "receivefrom=", "supporteddevices="))]
        self.assertEqual(headers, ["# name=Trap Metal Kit"])
        self.assertEqual(BUNDLE.read_text(encoding="utf-8").split("\n")[0], "# name=Trap Metal Kit")

    def test_header_neutraliser_keeps_line_numbers(self):
        source = "# name=X\n# url=https://example.com\nprint(1)\n"
        out = build_fl_bundle.neutralise_headers(source)
        self.assertEqual(out.count("\n"), source.count("\n"))
        self.assertNotIn("name=", out)
        self.assertNotIn("url=", out)

    def test_triple_quotes_in_a_source_script_are_refused(self):
        with mock.patch("builtins.open", mock.mock_open(read_data="x = '''oops'''\n")):
            with self.assertRaises(SystemExit):
                build_fl_bundle.read_section("TrapDJ")


if __name__ == "__main__":
    unittest.main()
