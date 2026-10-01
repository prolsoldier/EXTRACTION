"""Loads fl-studio/device_VocalSetup.py against a stub mixer that keeps state, and checks the layout it builds."""
import contextlib
import importlib.util
import io
import pathlib
import sys
import types
import unittest

SCRIPT = pathlib.Path(__file__).parent.parent / "fl-studio" / "device_VocalSetup.py"


class Event:
    def __init__(self, data1, data2=100):
        self.data1, self.data2, self.handled = data1, data2, False


class StubMixer:
    """Just enough of FL's mixer module: names, colours, routes with levels, arming."""

    def __init__(self, tracks=127):
        self.count = tracks
        self.names = {i: "Master" if i == 0 else "Insert %d" % i for i in range(tracks)}
        self.colors, self.routes, self.levels, self.armed = {}, {(i, 0) for i in range(1, tracks)}, {}, set()
        self.arm_calls, self.routing_updates = 0, 0

    def trackCount(self): return self.count
    def getTrackName(self, i): return self.names[i]
    def setTrackName(self, i, n): self.names[i] = n
    def setTrackColor(self, i, c): self.colors[i] = c

    def setRouteTo(self, src, dst, value, updateUI=False):
        (self.routes.add if value else self.routes.discard)((src, dst))

    def setRouteToLevel(self, src, dst, level):
        assert (src, dst) in self.routes, "route must exist before its level is set"
        self.levels[(src, dst)] = level

    def afterRoutingChanged(self): self.routing_updates += 1
    def isTrackArmed(self, i): return i in self.armed

    def armTrack(self, i):
        self.arm_calls += 1
        self.armed ^= {i}  # FL's armTrack toggles


class StubPlugins:
    """slots: {(track, slot): plugin name}"""

    def __init__(self, slots):
        self.slots = slots

    def isValid(self, track, slot=-1, useGlobalIndex=False): return (track, slot) in self.slots
    def getPluginName(self, track, slot=-1, userName=0, useGlobalIndex=False): return self.slots[(track, slot)]


def load(plugin_slots=None, **kwargs):
    supports_levels = kwargs.pop("supports_levels", True)
    stub = StubMixer(**kwargs)
    functions = {n: getattr(stub, n) for n in dir(stub) if not n.startswith("_") and callable(getattr(stub, n))}
    if not supports_levels:
        del functions["setRouteToLevel"]  # old FL: the function does not exist at all
    module_mixer = types.SimpleNamespace(**functions)
    sys.modules["mixer"] = module_mixer
    if plugin_slots is None:
        sys.modules["plugins"] = None   # makes `import plugins` raise ImportError even if the real FL stubs are installed
    else:
        stub_plugins = StubPlugins(plugin_slots)
        sys.modules["plugins"] = types.SimpleNamespace(isValid=stub_plugins.isValid, getPluginName=stub_plugins.getPluginName)
    spec = importlib.util.spec_from_file_location("device_VocalSetup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, stub


class VocalSetupTest(unittest.TestCase):
    def test_names_and_colours_are_applied_in_order(self):
        m, mixer = load()
        self.assertTrue(m.setup())
        names = [mixer.names[i] for i in range(1, 9)]
        self.assertEqual(names, ["VOX MAIN", "VOX DBL L", "VOX DBL R", "ADLIBS", "SCREAMS", "VOX BUS", "REVERB", "DELAY"])
        self.assertEqual(mixer.colors[1], m.rgb_to_fl(255, 20, 147))
        self.assertEqual(len(set(mixer.colors[i] for i in range(1, 9))), 6)

    def test_vocals_route_to_bus_not_master_and_send_to_fx(self):
        m, mixer = load()
        m.setup()
        bus, reverb, delay = m.index_of("VOX BUS"), m.index_of("REVERB"), m.index_of("DELAY")
        for name in ("VOX MAIN", "VOX DBL L", "VOX DBL R", "ADLIBS", "SCREAMS"):
            t = m.index_of(name)
            self.assertIn((t, bus), mixer.routes)
            self.assertNotIn((t, 0), mixer.routes)
            self.assertEqual(mixer.levels[(t, reverb)], 0.45)
            self.assertEqual(mixer.levels[(t, delay)], 0.35)
        # bus and fx inserts keep their route to master
        for t in (bus, reverb, delay):
            self.assertIn((t, 0), mixer.routes)
        self.assertEqual(mixer.routing_updates, 1)

    def test_lead_is_armed_once_and_not_toggled_off_on_a_second_run(self):
        m, mixer = load()
        m.setup()
        m.setup()
        self.assertEqual(mixer.armed, {m.index_of("VOX MAIN")})
        self.assertEqual(mixer.arm_calls, 1)

    def test_refuses_to_overwrite_inserts_the_user_named(self):
        m, mixer = load()
        mixer.names[3] = "My Drums"
        self.assertFalse(m.setup())
        self.assertEqual(mixer.names[3], "My Drums")
        self.assertEqual(mixer.arm_calls, 0)
        self.assertEqual(mixer.colors, {})
        self.assertEqual([i for i, _ in m.blocked_inserts()], [3])

    def test_force_overrides_the_guard(self):
        m, mixer = load()
        mixer.names[3] = "My Drums"
        m.FORCE = True
        self.assertTrue(m.setup())
        self.assertEqual(mixer.names[3], "VOX DBL R")

    def test_default_and_empty_names_count_as_unused(self):
        m, mixer = load()
        mixer.names[2] = ""
        mixer.names[4] = "Insert 4"
        self.assertEqual(m.blocked_inserts(), [])

    def test_too_small_a_mixer_is_left_alone(self):
        m, mixer = load(tracks=8)
        self.assertFalse(m.setup())
        self.assertEqual(mixer.colors, {})

    def test_old_fl_without_send_levels_still_sets_up_routing(self):
        m, mixer = load(supports_levels=False)
        self.assertTrue(m.setup())
        self.assertIn((m.index_of("VOX MAIN"), m.index_of("REVERB")), mixer.routes)
        self.assertEqual(mixer.levels, {})  # no level API: routes exist, levels are left for the user

    def test_only_the_setup_note_triggers_it(self):
        m, mixer = load()
        other = Event(60)
        m.OnNoteOn(other)
        self.assertFalse(other.handled)
        self.assertEqual(mixer.colors, {})
        release = Event(126, 0)
        m.OnNoteOn(release)
        self.assertFalse(release.handled)
        press = Event(126)
        m.OnNoteOn(press)
        self.assertTrue(press.handled)
        self.assertTrue(mixer.colors)


class AuditTest(unittest.TestCase):
    """The audit reads plugin names from mixer slots and checks them against EXPECTED."""

    def chain(self, m):
        return {(m.index_of("VOX MAIN"), 1): "Nectar 4", (m.index_of("VOX MAIN"), 2): "Fruity Limiter",
                (m.index_of("SCREAMS"), 0): "Unison Mangler", (0, 0): "Ozone 12"}

    def loaded(self, extra=None, drop=()):
        probe, _ = load()
        slots = {k: v for k, v in self.chain(probe).items() if v not in drop}
        slots.update(extra or {})
        return load(plugin_slots=slots)

    def run_audit(self, m):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            report = m.audit()
        return report, out.getvalue()

    def test_full_chain_is_ok(self):
        m, _ = self.loaded()
        report, text = self.run_audit(m)
        self.assertEqual({k: v["missing"] for k, v in report.items()}, {"VOX MAIN": [], "SCREAMS": [], "MASTER": []})
        self.assertEqual(report["VOX MAIN"]["plugins"], ["Nectar 4", "Fruity Limiter"])
        self.assertIn("OK      VOX MAIN", text)
        self.assertNotIn("MISSING", text)

    def test_missing_ozone_and_nectar_are_reported_by_name(self):
        m, _ = self.loaded(drop=("Ozone 12", "Nectar 4"))
        report, text = self.run_audit(m)
        self.assertEqual(report["MASTER"]["missing"], ["ozone"])
        self.assertEqual(report["VOX MAIN"]["missing"], ["nectar"])
        self.assertIn("MISSING MASTER", text)
        self.assertIn("load: ozone", text)
        self.assertEqual(report["SCREAMS"]["missing"], [])            # Mangler still there

    def test_any_alternative_satisfies_a_group(self):
        m, _ = self.loaded(drop=("Unison Mangler",), extra={(load()[0].index_of("SCREAMS"), 3): "iZotope Trash"})
        report, _ = self.run_audit(m)
        self.assertEqual(report["SCREAMS"]["missing"], [])
        m, _ = self.loaded(drop=("Unison Mangler",))
        report, _ = self.run_audit(m)
        self.assertEqual(report["SCREAMS"]["missing"], ["mangler/trash/decapitator/saturn/nectar"])

    def test_empty_slots_are_skipped_and_matching_is_case_insensitive(self):
        m, _ = self.loaded(drop=("Ozone 12",), extra={(0, 7): "IZOTOPE OZONE 12 ADVANCED"})
        report, _ = self.run_audit(m)
        self.assertEqual(report["MASTER"]["plugins"], ["IZOTOPE OZONE 12 ADVANCED"])
        self.assertEqual(report["MASTER"]["missing"], [])

    def test_audit_without_a_plugins_module_says_so(self):
        m, _ = load()  # no plugins stub -> import fails -> plugins is None
        self.assertIsNone(m.plugins)
        report, text = self.run_audit(m)
        self.assertEqual(report, {})
        self.assertIn("cannot audit", text)

    def test_audit_note_runs_the_audit_and_never_changes_the_mixer(self):
        m, mixer = self.loaded()
        before = (dict(mixer.names), dict(mixer.colors), set(mixer.routes), set(mixer.armed))
        press = Event(125)
        with contextlib.redirect_stdout(io.StringIO()):
            m.OnNoteOn(press)
        self.assertTrue(press.handled)
        self.assertEqual(before, (dict(mixer.names), dict(mixer.colors), set(mixer.routes), set(mixer.armed)))
        other = Event(60)
        m.OnNoteOn(other)
        self.assertFalse(other.handled)
        release = Event(125, 0)
        m.OnNoteOn(release)
        self.assertFalse(release.handled)

    def test_setup_prints_hints_that_mention_nectar_and_ozone(self):
        m, _ = load()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            m.setup()
        text = out.getvalue()
        for needle in ("Nectar 4", "Vocal Assistant", "Ozone 12", "Master Assistant", "Gain Match", "Mangler"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
