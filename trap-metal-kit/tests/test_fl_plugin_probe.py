"""Loads fl-studio/device_PluginProbe.py against stub FL modules. The stub has NO setter functions, so any attempt
to write to FL from the probe would raise AttributeError and fail these tests."""
import contextlib
import importlib.util
import io
import pathlib
import sys
import types
import unittest

SCRIPT = pathlib.Path(__file__).parent.parent / "fl-studio" / "device_PluginProbe.py"


class Event:
    def __init__(self, data1, data2=100):
        self.data1, self.data2, self.handled = data1, data2, False


def load(tracks=40, chain=None, params=None, value_strings=True):
    """chain: {(track, slot): plugin name}; params: {plugin name: [(param name, value), ...]}"""
    chain = chain if chain is not None else {(0, 0): "Ozone 12", (1, 2): "Nectar 4", (6, 1): "Mangler"}
    params = params if params is not None else {
        "Ozone 12": [("Bypass", 0.0), ("Output Gain", 0.5)],
        "Nectar 4": [("Wet", 1.0)],
        "Mangler": [("Mangle", 0.25), ("", 0.0), ("Saturate", 0.5)],
    }

    def plugin_at(track, slot):
        return chain[(track, slot)]

    def get_param_name(p, track, slot=-1, g=False): return params[plugin_at(track, slot)][p][0]
    def get_param_value(p, track, slot=-1, g=False): return params[plugin_at(track, slot)][p][1]

    def get_value_string(p, track, slot=-1, g=False):
        if not value_strings:
            raise RuntimeError("not supported by this plugin")
        return "%.0f%%" % (params[plugin_at(track, slot)][p][1] * 100)

    plugins = types.SimpleNamespace(
        isValid=lambda track, slot=-1, g=False: (track, slot) in chain,
        getPluginName=lambda track, slot=-1, u=0, g=False: plugin_at(track, slot),
        getParamCount=lambda track, slot=-1, g=False: len(params[plugin_at(track, slot)]),
        getParamName=get_param_name, getParamValue=get_param_value, getParamValueString=get_value_string)
    mixer = types.SimpleNamespace(trackCount=lambda: tracks,
                                  getTrackName=lambda i: "Master" if i == 0 else "Insert %d" % i)
    sys.modules.update({"plugins": plugins, "mixer": mixer})
    spec = importlib.util.spec_from_file_location("device_PluginProbe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(module):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        results = module.probe()
    return results, out.getvalue()


class ProbeTest(unittest.TestCase):
    def test_finds_every_plugin_with_track_and_slot(self):
        results, text = run(load())
        self.assertEqual([(t, s, n) for t, s, n, _ in results], [(0, 0, "Ozone 12"), (1, 2, "Nectar 4"), (6, 1, "Mangler")])
        self.assertIn("track 0 (Master) slot 0: Ozone 12", text)
        self.assertIn("track 1 (Insert 1) slot 2: Nectar 4", text)

    def test_lists_named_parameters_with_normalised_values_and_strings(self):
        results, text = run(load())
        ozone_params = results[0][3]
        self.assertEqual([(i, n, v) for i, n, v, _ in ozone_params], [(0, "Bypass", 0.0), (1, "Output Gain", 0.5)])
        self.assertIn("[1] Output Gain = 0.500  (50%)", text)

    def test_unnamed_parameters_are_skipped_and_value_strings_are_optional(self):
        results, text = run(load(value_strings=False))
        mangler = results[2][3]
        self.assertEqual([n for _, n, _, _ in mangler], ["Mangle", "Saturate"])
        self.assertNotIn("(", text.split("Mangler   (3 params")[1].splitlines()[1])   # no value-string suffix

    def test_parameter_listing_is_capped(self):
        many = {"Big Plugin": [("P%d" % i, 0.5) for i in range(200)]}
        module = load(chain={(0, 0): "Big Plugin"}, params=many)
        module.MAX_PARAMS_PRINTED = 5
        results, text = run(module)
        self.assertEqual(len(results[0][3]), 5)
        self.assertIn("... 195 more", text)

    def test_tracks_beyond_the_mixer_are_not_probed_and_empty_mixer_is_reported(self):
        results, text = run(load(tracks=3, chain={(6, 1): "Mangler"}))
        self.assertEqual(results, [])
        self.assertIn("no plugins found", text)

    def test_only_the_probe_note_triggers_it(self):
        module = load()
        other, release, press = Event(60), Event(124, 0), Event(124)
        with contextlib.redirect_stdout(io.StringIO()):
            module.OnNoteOn(other)
            module.OnNoteOn(release)
            module.OnNoteOn(press)
        self.assertFalse(other.handled)
        self.assertFalse(release.handled)
        self.assertTrue(press.handled)


if __name__ == "__main__":
    unittest.main()
