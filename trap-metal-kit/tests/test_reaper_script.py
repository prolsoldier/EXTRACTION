"""Runs reaper/key_slots.lua against a mock of the ReaScript API (needs `pip install lupa`)."""
import pathlib
import unittest

from lupa import LuaRuntime

SCRIPT = pathlib.Path(__file__).parent.parent / "reaper" / "key_slots.lua"

MOCK = r"""
console, fx_state, next_fx = {}, {}, 0
local RS5K_PARAMS = PARAMS or { "Volume", "Pan", "Note range start", "Note range end", "Obey note-offs", "Loop" }

reaper = {
  ShowConsoleMsg = function(m) console[#console + 1] = m end,
  GetSelectedTrack = function() return (not NO_TRACK) and "TRACK" or nil end,
  GetUserInputs = function() return true, USER_DIR end,
  EnumerateFiles = function(_, i) return FILES[i + 1] end,
  TrackFX_AddByName = function()
    if NO_RS5K then return -1 end
    local idx = next_fx; next_fx = next_fx + 1
    fx_state[idx] = { config = {}, params = {} }
    return idx
  end,
  TrackFX_SetNamedConfigParm = function(_, fx, key, value) fx_state[fx].config[key] = value; return true end,
  TrackFX_GetNumParams = function() return #RS5K_PARAMS end,
  TrackFX_GetParamName = function(_, _, i) return true, RS5K_PARAMS[i + 1] end,
  TrackFX_SetParamNormalized = function(_, fx, i, v) fx_state[fx].params[RS5K_PARAMS[i + 1]] = v; return true end,
  Undo_BeginBlock = function() end,
  Undo_EndBlock = function() end,
}
"""


def run(files, user_dir="/music", params=None, no_track=False, no_rs5k=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    g.FILES = lua.table_from(files)
    g.USER_DIR = user_dir
    g.NO_TRACK = no_track
    g.NO_RS5K = no_rs5k
    if params:
        g.PARAMS = lua.table_from(params)
    lua.execute(MOCK)
    lua.execute(SCRIPT.read_text())
    fx = {int(i): {"config": dict(s["config"]), "params": dict(s["params"])} for i, s in g.fx_state.items()}
    return fx, list(g.console.values())


class ReaperScriptTest(unittest.TestCase):
    def test_one_sampler_per_file_sorted_each_on_its_own_note(self):
        fx, _ = run(["b.wav", "a.wav", "readme.txt"])
        self.assertEqual(sorted(fx), [0, 1])
        self.assertEqual(fx[0]["config"]["FILE0"], "/music/a.wav")
        self.assertEqual(fx[1]["config"]["FILE0"], "/music/b.wav")
        for idx, note in ((0, 36), (1, 37)):
            self.assertAlmostEqual(fx[idx]["params"]["Note range start"], note / 127)
            self.assertAlmostEqual(fx[idx]["params"]["Note range end"], note / 127)
            self.assertEqual(fx[idx]["config"]["DONE"], "")

    def test_trailing_slash_in_folder_is_normalised(self):
        fx, _ = run(["a.wav"], user_dir="C:\\music\\")
        self.assertEqual(fx[0]["config"]["FILE0"], "C:\\music/a.wav")

    def test_loop_switch_is_set_when_present_and_skipped_when_absent(self):
        fx, _ = run(["a.wav"])
        self.assertEqual(fx[0]["params"]["Loop"], 1)
        fx, console = run(["a.wav"], params=["Volume", "Note range start", "Note range end"])
        self.assertNotIn("Loop", fx[0]["params"])
        self.assertTrue(any("skipped" in line for line in console))

    def test_no_selected_track_or_files_does_nothing(self):
        fx, console = run(["a.wav"], no_track=True)
        self.assertEqual(fx, {})
        self.assertTrue(any("Select a track" in line for line in console))
        fx, console = run(["notes.txt"])
        self.assertEqual(fx, {})
        self.assertTrue(any("No audio files" in line for line in console))

    def test_missing_sampler_plugin_is_reported(self):
        fx, console = run(["a.wav"], no_rs5k=True)
        self.assertEqual(fx, {})
        self.assertTrue(any("not found" in line for line in console))

    def test_more_files_than_keys_are_truncated(self):
        files = [f"{i:03d}.wav" for i in range(120)]
        fx, console = run(files)
        self.assertEqual(len(fx), 128 - 36)
        self.assertTrue(any("fit on the keyboard" in line for line in console))


if __name__ == "__main__":
    unittest.main()
