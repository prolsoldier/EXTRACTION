"""Loads fl-studio/device_PinkTheme.py against stub FL modules and checks what it paints."""
import importlib.util
import pathlib
import sys
import types
import unittest

SCRIPT = pathlib.Path(__file__).parent.parent / "fl-studio" / "device_PinkTheme.py"


class Event:
    def __init__(self, data1, data2=100):
        self.data1, self.data2, self.handled = data1, data2, False


def load(channel_count=6, mixer_tracks=127, pattern_count=4, channel_accepts_global=True):
    calls = {"channel": [], "mixer": [], "playlist": [], "pattern": []}
    state = {"channels": channel_count, "patterns": pattern_count}

    def set_channel_color(*args):
        if not channel_accepts_global and len(args) == 3:
            raise TypeError("old API")
        calls["channel"].append(args)

    stubs = {
        "channels": types.SimpleNamespace(channelCount=lambda g=0: state["channels"], setChannelColor=set_channel_color),
        "mixer": types.SimpleNamespace(trackCount=lambda: mixer_tracks,
                                       setTrackColor=lambda i, c: calls["mixer"].append((i, c))),
        "playlist": types.SimpleNamespace(setTrackColor=lambda i, c: calls["playlist"].append((i, c))),
        "patterns": types.SimpleNamespace(patternCount=lambda: state["patterns"],
                                          setPatternColor=lambda i, c: calls["pattern"].append((i, c))),
    }
    sys.modules.update(stubs)
    spec = importlib.util.spec_from_file_location("device_PinkTheme", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls, state


class PinkThemeTest(unittest.TestCase):
    def test_colour_is_bgr_ordered(self):
        m, _, _ = load()
        self.assertEqual(m.rgb_to_fl(255, 20, 147), 0x9314FF)  # hot pink: blue 0x93 is the top byte, red 0xFF the bottom
        self.assertEqual(m.rgb_to_fl(1, 2, 3), 0x030201)

    def test_palette_is_pink_dominant_and_never_repeats_on_neighbours(self):
        m, _, _ = load()
        names = [m.CYCLE[i % len(m.CYCLE)] for i in range(300)]
        pink_share = sum(n in m.PINKS for n in names) / len(names)
        self.assertGreaterEqual(pink_share, 0.5)
        self.assertTrue(all(a != b for a, b in zip(names, names[1:])))
        self.assertTrue({"purple", "deep_purple", "red", "black"} <= set(m.CYCLE))
        for rgb in m.COLORS.values():
            self.assertTrue(all(0 <= v <= 255 for v in rgb))

    def test_init_paints_channels_mixer_playlist_and_patterns(self):
        m, calls, _ = load(channel_count=6, mixer_tracks=127, pattern_count=4)
        m.OnInit()
        self.assertEqual([c[0] for c in calls["channel"]], list(range(6)))
        self.assertTrue(all(c[2] is True for c in calls["channel"]))            # global index
        self.assertEqual([c[1] for c in calls["channel"]], [m.color_for(i) for i in range(6)])
        self.assertEqual(calls["mixer"][0], (0, m.rgb_to_fl(*m.COLORS[m.MASTER_COLOR])))
        mixer_indices = [i for i, _ in calls["mixer"][1:]]
        self.assertEqual(mixer_indices, list(range(1, m.MAX_MIXER_INSERTS + 1)))
        self.assertNotIn(126, mixer_indices)                                     # the utility "Current" track
        self.assertEqual([i for i, _ in calls["playlist"]], list(range(1, m.PLAYLIST_TRACKS + 1)))
        self.assertEqual([i for i, _ in calls["pattern"]], [1, 2, 3, 4])

    def test_small_mixer_is_not_overpainted(self):
        m, calls, _ = load(mixer_tracks=10)  # master + 8 inserts + Current
        m.OnInit()
        self.assertEqual([i for i, _ in calls["mixer"]], list(range(0, 9)))

    def test_falls_back_when_api_lacks_the_global_index_argument(self):
        m, calls, _ = load(channel_count=3, channel_accepts_global=False)
        m.OnInit()
        self.assertEqual([len(c) for c in calls["channel"]], [2, 2, 2])

    def test_idle_paints_only_new_channels_and_patterns(self):
        m, calls, state = load(channel_count=3, pattern_count=2)
        m.OnInit()
        calls["channel"].clear(); calls["pattern"].clear()
        for _ in range(m.IDLE_CHECK_EVERY * 2):
            m.OnIdle()
        self.assertEqual(calls["channel"], [])                                   # nothing added: nothing touched
        state["channels"], state["patterns"] = 5, 3
        for _ in range(m.IDLE_CHECK_EVERY):
            m.OnIdle()
        self.assertEqual([c[0] for c in calls["channel"]], [3, 4])
        self.assertEqual([i for i, _ in calls["pattern"]], [3])

    def test_repaint_note_is_off_by_default_and_works_when_enabled(self):
        m, calls, _ = load()
        e = Event(127)
        m.OnNoteOn(e)
        self.assertFalse(e.handled)
        self.assertEqual(calls["channel"], [])
        m.REPAINT_NOTE = 127
        m.OnNoteOn(e)
        self.assertTrue(e.handled)
        self.assertTrue(calls["channel"])
        other = Event(60)
        m.OnNoteOn(other)
        self.assertFalse(other.handled)


class DocsMatchScriptTest(unittest.TestCase):
    """docs/06-pink-theme.md quotes the palette; make sure it cannot drift from the script."""

    DOC = pathlib.Path(__file__).parent.parent / "docs" / "06-pink-theme.md"

    def test_palette_table_matches_colors_and_cycle_shares(self):
        import re
        m, _, _ = load()
        rows = re.findall(r"^\| (\w+) \| #([0-9A-F]{6}) \| (\d+), (\d+), (\d+) \| (\d+) of 10", self.DOC.read_text(), re.M)
        self.assertEqual({r[0] for r in rows}, set(m.COLORS))
        for name, hex_code, r, g, b, share in rows:
            self.assertEqual(m.COLORS[name], (int(r), int(g), int(b)), name)
            self.assertEqual(hex_code, "%02X%02X%02X" % m.COLORS[name], name)
            self.assertEqual(int(share), m.CYCLE.count(name), name)
        self.assertEqual(sum(int(r[5]) for r in rows), len(m.CYCLE))

    def test_doc_says_pinks_are_six_of_ten(self):
        m, _, _ = load()
        self.assertEqual(sum(1 for n in m.CYCLE if n in m.PINKS), 6)
        self.assertIn("Pinks are 6 of every 10 rows", self.DOC.read_text())


if __name__ == "__main__":
    unittest.main()
