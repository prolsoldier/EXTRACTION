"""Runs kontakt/map_folder_to_keys.lua against a mock of the Kontakt Lua API.

Needs `pip install lupa`. This proves the script's own logic (sorting, key assignment,
overrides, error handling); it cannot prove Kontakt's runtime behaviour.
"""
import pathlib
import unittest

from lupa import LuaRuntime

SCRIPT = pathlib.Path(__file__).parent.parent / "kontakt" / "map_folder_to_keys.lua"

MOCK = r"""
calls, printed = {}, {}
function print(...)
  local parts = {}
  for i = 1, select('#', ...) do parts[i] = tostring((select(i, ...))) end
  printed[#printed + 1] = table.concat(parts, " ")
end

local function rec(name, ret)
  return function(...)
    local args = { ... }
    calls[#calls + 1] = { name = name, args = args }
    if type(ret) == "function" then return ret(...) end
    return ret
  end
end

local next_group, next_zone = 0, 0
Kontakt = {
  script_path = "/proj",
  reset_multi = rec("reset_multi"),
  add_instrument = rec("add_instrument", 0),
  set_instrument_name = rec("set_instrument_name"),
  add_group = rec("add_group", function() next_group = next_group + 1; return next_group end),
  set_group_name = rec("set_group_name"),
  add_zone = rec("add_zone", function() next_zone = next_zone + 1; return next_zone end),
  set_zone_geometry = rec("set_zone_geometry"),
  get_zone_sample_frames = rec("get_zone_sample_frames", 44100),
  set_sample_loop_mode = rec("set_sample_loop_mode", function(_, _, slot) if ZERO_BASED_LOOPS == false and slot == 0 then error("bad loop idx") end end),
  set_sample_loop_start = rec("set_sample_loop_start"),
  set_sample_loop_length = rec("set_sample_loop_length"),
  set_sample_loop_count = rec("set_sample_loop_count"),
  set_group_playback_mode = rec("set_group_playback_mode"),
  set_zone_grid = rec("set_zone_grid"),
  save_instrument = rec("save_instrument"),
  get_num_groups = function() return next_group end,
  get_num_zones = function() return next_zone end,
}

Filesystem = {
  join = function(...) return table.concat({ ... }, "/") end,
  exists = function(p) return p == "/proj/samples" and not NO_FOLDER end,
  extension = function(p) return p:match("(%.[^./]+)$") or "" end,
  filename = function(p) return p:match("([^/]+)$") end,
  stem = function(p) return (p:match("([^/]+)$"):gsub("%.[^.]+$", "")) end,
  directory = function(path)
    local i = 0
    return function()
      i = i + 1
      local f = FILES[i]
      if f then return i, path .. "/" .. f end
    end
  end,
}
"""


def run(files, config=None, zero_based_loops=True, no_folder=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    g.FILES = lua.table_from(files)
    g.ZERO_BASED_LOOPS = zero_based_loops
    g.NO_FOLDER = no_folder
    lua.execute(MOCK)
    if config:
        g.MAPPER_CONFIG = lua.table_from({k: (lua.table_from(v) if isinstance(v, dict) else v) for k, v in config.items()})
    lua.execute(SCRIPT.read_text())
    calls = [(c["name"], [c["args"][i] for i in range(1, len(c["args"]) + 1)]) for c in g.calls.values()]
    printed = list(g.printed.values())
    return calls, printed


def geometries(calls):
    return [(a[2]["root_key"], a[2]["low_key"], a[2]["high_key"]) for n, a in calls if n == "set_zone_geometry"]


class KontaktMapperTest(unittest.TestCase):
    def test_sorted_files_map_to_consecutive_keys_one_zone_each(self):
        calls, _ = run(["b.wav", "a.wav", "c.aiff"])
        self.assertEqual(geometries(calls), [(36, 36, 36), (37, 37, 37), (38, 38, 38)])
        added = [a[2] for n, a in calls if n == "add_zone"]
        self.assertEqual(added, ["/proj/samples/a.wav", "/proj/samples/b.wav", "/proj/samples/c.aiff"])

    def test_non_audio_files_are_ignored(self):
        calls, _ = run(["notes.txt", "a.wav", "cover.png"])
        self.assertEqual(len(geometries(calls)), 1)

    def test_white_keys_only_skips_black_keys(self):
        calls, _ = run(["1.wav", "2.wav", "3.wav", "4.wav", "5.wav"], {"white_keys_only": True})
        self.assertEqual([g[0] for g in geometries(calls)], [36, 38, 40, 41, 43])

    def test_override_pins_a_file_and_others_flow_around_it(self):
        calls, _ = run(["a.wav", "b.wav", "c.wav"], {"overrides": {37: "c.wav"}})
        zones = [a[2] for n, a in calls if n == "add_zone"]
        geoms = [g[0] for g in geometries(calls)]
        by_key = dict(zip(geoms, zones))
        self.assertEqual(by_key[37], "/proj/samples/c.wav")
        self.assertEqual(by_key[36], "/proj/samples/a.wav")
        self.assertEqual(by_key[38], "/proj/samples/b.wav")

    def test_bpm_in_filename_sets_fixed_grid_tempo(self):
        calls, _ = run(["Drum_Beat_130_BPM.wav", "plain.wav"])
        grids = [a for n, a in calls if n == "set_zone_grid"]
        self.assertEqual(len(grids), 1)
        self.assertEqual((grids[0][2], grids[0][3]), ("fixed", 130))
        modes = [a[2] for n, a in calls if n == "set_group_playback_mode"]
        self.assertEqual(modes, ["time_machine_pro"])

    def test_loop_covers_whole_sample_and_survives_one_based_api(self):
        calls, printed = run(["a.wav"], zero_based_loops=False)
        starts = [a for n, a in calls if n == "set_sample_loop_start"]
        self.assertTrue(starts, "loop was never applied on the slot that works")
        self.assertEqual(starts[0][3], 0)
        lengths = [a for n, a in calls if n == "set_sample_loop_length"]
        self.assertEqual(lengths[0][3], 44100)
        self.assertTrue(any("[loop" in line for line in printed))

    def test_loop_and_sync_can_be_disabled(self):
        calls, _ = run(["a_140_BPM.wav"], {"loop": False, "tempo_sync": False})
        names = {n for n, _ in calls}
        self.assertNotIn("set_sample_loop_mode", names)
        self.assertNotIn("set_zone_grid", names)

    def test_missing_folder_reports_error_and_adds_nothing(self):
        calls, printed = run(["a.wav"], no_folder=True)
        self.assertNotIn("add_instrument", {n for n, _ in calls})
        self.assertTrue(any("failed" in line and "not found" in line for line in printed))

    def test_running_out_of_keys_warns_instead_of_erroring(self):
        calls, printed = run(["1.wav", "2.wav", "3.wav", "4.wav"], {"first_key": 126})
        self.assertEqual([g[0] for g in geometries(calls)], [126, 127])
        self.assertTrue(any("WARNING" in line for line in printed))

    def test_reset_multi_is_opt_in(self):
        calls, _ = run(["a.wav"])
        self.assertNotIn("reset_multi", {n for n, _ in calls})
        calls, _ = run(["a.wav"], {"reset_multi": True})
        self.assertIn("reset_multi", {n for n, _ in calls})


if __name__ == "__main__":
    unittest.main()
