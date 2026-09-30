"""Loads fl-studio/device_TrapDJ.py against stub FL modules and drives its callbacks.

This proves the note->clip mapping and crossfade maths; it cannot prove FL Studio's behaviour.
"""
import importlib.util
import math
import pathlib
import sys
import types
import unittest

SCRIPT = pathlib.Path(__file__).parent.parent / "fl-studio" / "device_TrapDJ.py"


class Event:
    def __init__(self, data1, data2=100):
        self.data1, self.data2, self.handled = data1, data2, False


def load_script():
    midi = types.SimpleNamespace(TLC_TrackSnap=0, TLC_GlobalSnap=8, TLC_NoSnap=16, TLC_Fill=2, TLC_MuteOthers=1)
    triggers, volumes = [], []
    playlist = types.SimpleNamespace(
        triggerLiveClip=lambda *a: triggers.append(a),
        getPerformanceModeState=lambda: True,
    )
    mixer = types.SimpleNamespace(setTrackVolume=lambda *a: volumes.append(a))
    for name, mod in (("midi", midi), ("playlist", playlist), ("mixer", mixer)):
        sys.modules[name] = mod
    spec = importlib.util.spec_from_file_location("device_TrapDJ", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, triggers, volumes


class TrapDJTest(unittest.TestCase):
    def setUp(self):
        self.m, self.triggers, self.volumes = load_script()

    def test_first_key_launches_track1_block0(self):
        e = Event(36)
        self.m.OnNoteOn(e)
        self.assertEqual(self.triggers, [(1, 0, 0)])
        self.assertTrue(e.handled)

    def test_keys_wrap_to_next_deck_row(self):
        self.m.OnNoteOn(Event(36 + 8))      # first key of row 2
        self.m.OnNoteOn(Event(36 + 8 + 3))  # fourth key of row 2
        self.assertEqual(self.triggers, [(2, 0, 0), (2, 3, 0)])

    def test_stop_keys_send_minus_one_with_fill_flag(self):
        self.m.OnNoteOn(Event(36 + 4 * 8 + 1))  # stop deck 2
        self.assertEqual(self.triggers, [(2, -1, 2)])

    def test_notes_outside_the_layout_pass_through(self):
        e = Event(90)
        self.m.OnNoteOn(e)
        self.assertEqual(self.triggers, [])
        self.assertFalse(e.handled)

    def test_velocity_zero_note_on_is_ignored(self):
        e = Event(36, 0)
        self.m.OnNoteOn(e)
        self.assertEqual(self.triggers, [])
        self.assertFalse(e.handled)

    def test_note_off_is_swallowed_only_for_mapped_keys(self):
        mapped, unmapped = Event(36), Event(90)
        self.m.OnNoteOff(mapped)
        self.m.OnNoteOff(unmapped)
        self.assertTrue(mapped.handled)
        self.assertFalse(unmapped.handled)

    def test_crossfader_endpoints_and_centre_are_equal_power(self):
        self.m.OnControlChange(Event(1, 0))
        self.m.OnControlChange(Event(1, 127))
        self.m.OnControlChange(Event(1, 64))
        (a0, b0), (a1, b1), (a2, b2) = [(self.volumes[i][1], self.volumes[i + 1][1]) for i in (0, 2, 4)]
        self.assertAlmostEqual(a0, 0.8)
        self.assertAlmostEqual(b0, 0.0)
        self.assertAlmostEqual(a1, 0.0)
        self.assertAlmostEqual(b1, 0.8)
        # equal power: a^2 + b^2 stays constant across the fade
        self.assertAlmostEqual(a2 ** 2 + b2 ** 2, 0.8 ** 2, places=3)
        self.assertEqual([v[0] for v in self.volumes[:2]], [1, 2])

    def test_other_ccs_are_left_alone(self):
        e = Event(7, 100)
        self.m.OnControlChange(e)
        self.assertEqual(self.volumes, [])
        self.assertFalse(e.handled)

    def test_layout_has_no_overlap_between_play_and_stop_ranges(self):
        seen = {}
        for note in range(128):
            slot = self.m.slot_for_note(note)
            if slot:
                self.assertNotIn(slot, seen.values())
                seen[note] = slot
        self.assertEqual(len(seen), 8 * 4 + 4)

    def test_crossfade_gains_clamp(self):
        self.assertEqual(self.m.crossfade_gains(-3), (1.0, 0.0))
        a, b = self.m.crossfade_gains(9)
        self.assertAlmostEqual(a, math.cos(math.pi / 2), places=9)
        self.assertEqual(b, 1.0)


if __name__ == "__main__":
    unittest.main()
