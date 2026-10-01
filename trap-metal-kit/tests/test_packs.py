"""Tests for packs/packlib.py, packs_to_sfz.py and packs_to_dspreset.py using real (tiny) wav files."""
import contextlib
import io
import pathlib
import shutil
import sys
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "packs"))

import packlib  # noqa: E402
import packs_to_dspreset  # noqa: E402
import packs_to_sfz  # noqa: E402


def write_wav(path, frames=100):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00" * frames)


class PackTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "packs"
        write_wav(self.root / "songA" / "1_kick.wav", 100)
        write_wav(self.root / "songA" / "2_loop.wav", 250)
        write_wav(self.root / "songA" / "3_vox.wav", 400)
        write_wav(self.root / "songB" / "a.wav", 300)
        write_wav(self.root / "songB" / "b.wav", 300)
        (self.root / "empty").mkdir()
        (self.root / "songA" / "notes.txt").write_text("not audio")


class PacklibTest(PackTestCase):
    def test_list_packs_skips_folders_without_audio(self):
        self.assertEqual([p.name for p in packlib.list_packs(self.root)], ["songA", "songB"])

    def test_single_folder_is_its_own_pack_and_empty_root_errors(self):
        self.assertEqual([p.name for p in packlib.list_packs(self.root / "songB")], ["songB"])
        with self.assertRaises(ValueError):
            packlib.list_packs(self.root / "empty")
        with self.assertRaises(FileNotFoundError):
            packlib.list_packs(self.tmp / "missing")

    def test_list_samples_is_sorted_and_audio_only(self):
        names = [p.name for p in packlib.list_samples(self.root / "songA")]
        self.assertEqual(names, ["1_kick.wav", "2_loop.wav", "3_vox.wav"])

    def test_playable_keys(self):
        self.assertEqual(packlib.playable_keys(36, 3), [36, 37, 38])
        self.assertEqual(packlib.playable_keys(36, 5, white_keys_only=True), [36, 38, 40, 41, 43])
        with self.assertRaises(ValueError):
            packlib.playable_keys(126, 5)

    def test_switch_keys(self):
        keys = packlib.playable_keys(36, 3)
        self.assertEqual(packlib.switch_keys(None, 36, keys, 2), [34, 35])
        self.assertEqual(packlib.switch_keys(60, 36, keys, 2), [60, 61])
        with self.assertRaises(ValueError):
            packlib.switch_keys(37, 36, keys, 2)   # collides with sample keys
        with self.assertRaises(ValueError):
            packlib.switch_keys(None, 1, packlib.playable_keys(1, 3), 3)  # would start below note 0

    def test_wav_frames(self):
        self.assertEqual(packlib.wav_frames(self.root / "songA" / "2_loop.wav"), 250)
        self.assertIsNone(packlib.wav_frames(self.root / "songA" / "notes.txt"))
        (self.tmp / "bad.wav").write_bytes(b"garbage")
        self.assertIsNone(packlib.wav_frames(self.tmp / "bad.wav"))


def parse_sfz(text):
    """Tiny SFZ reader: returns (header opcodes per section, list of (group opcodes, region opcodes))."""
    section, current_group, groups, globals_ = None, None, [], {}
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if not line:
            continue
        tokens = line.split()
        header = tokens[0] if tokens[0].startswith("<") else None
        if header:
            section = header
            if header == "<group>":
                current_group = ({}, [])
                groups.append(current_group)
        opcodes = dict(t.split("=", 1) for t in tokens[1 if header else 0:] if "=" in t)
        if section == "<global>":
            globals_.update(opcodes)
        elif section == "<group>" and header != "<region>":
            current_group[0].update(opcodes)
        if header == "<region>":
            current_group[1].append(opcodes)
    return globals_, groups


class SfzTest(PackTestCase):
    def build(self, **kwargs):
        out = self.tmp / "dj.sfz"
        info = packs_to_sfz.build_sfz(self.root, out, **kwargs)
        return out, info, parse_sfz(out.read_text())

    def test_each_pack_gets_a_group_selected_by_its_keyswitch(self):
        out, info, (glob, groups) = self.build()
        self.assertEqual(info["switches"], [34, 35])
        self.assertEqual((glob["sw_lokey"], glob["sw_hikey"], glob["sw_default"]), ("34", "35", "34"))
        self.assertEqual([g[0]["sw_last"] for g in groups], ["34", "35"])
        self.assertEqual([g[0]["sw_label"] for g in groups], ["songA", "songB"])
        self.assertEqual([len(g[1]) for g in groups], [3, 2])

    def test_same_keys_are_reused_across_packs(self):
        _, _, (_, groups) = self.build()
        self.assertEqual([r["key"] for r in groups[0][1]], ["36", "37", "38"])
        self.assertEqual([r["key"] for r in groups[1][1]], ["36", "37"])

    def test_sample_paths_are_relative_posix_and_exist(self):
        out, _, (_, groups) = self.build()
        for _, regions in groups:
            for region in regions:
                self.assertNotIn("\\", region["sample"])
                self.assertTrue((out.parent / region["sample"]).is_file(), region["sample"])

    def test_loop_mode_sets_whole_file_loop_points(self):
        _, _, (_, groups) = self.build(mode="loop")
        region = groups[0][1][1]  # 2_loop.wav, 250 frames
        self.assertEqual((region["loop_mode"], region["loop_start"], region["loop_end"]), ("loop_continuous", "0", "249"))

    def test_hold_and_oneshot_modes(self):
        _, _, (_, groups) = self.build(mode="hold")
        self.assertEqual(groups[0][1][0]["loop_mode"], "no_loop")
        self.assertNotIn("loop_start", groups[0][1][0])
        _, _, (_, groups) = self.build(mode="oneshot")
        self.assertEqual(groups[0][1][0]["loop_mode"], "one_shot")

    def test_white_keys_only_and_custom_switch_keys(self):
        _, info, (_, groups) = self.build(white_keys_only=True, first_key=37, switch_first_key=100)
        self.assertEqual([r["key"] for r in groups[0][1]], ["38", "40", "41"])  # 37 is a black key
        self.assertEqual(info["switches"], [100, 101])

    def test_cli_reports_errors_with_exit_code_1(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = packs_to_sfz.main([str(self.root), str(self.tmp / "x.sfz"), "--first-key", "1"])
        self.assertEqual(code, 1)
        self.assertIn("error:", err.getvalue())

    def test_cli_success(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = packs_to_sfz.main([str(self.root), str(self.tmp / "ok.sfz")])
        self.assertEqual(code, 0)
        self.assertIn("keyswitch  34 -> songA", out.getvalue())


class DecentSamplerTest(PackTestCase):
    def build(self, **kwargs):
        out = self.tmp / "dj.dspreset"
        info = packs_to_dspreset.build_dspreset(self.root, out, **kwargs)
        return out, info, ET.parse(out).getroot()

    def test_structure_menu_groups_and_keyswitches(self):
        out, info, root = self.build()
        self.assertEqual(root.tag, "DecentSampler")
        groups = root.findall("./groups/group")
        self.assertEqual([(g.get("name"), g.get("enabled")) for g in groups], [("songA", "true"), ("songB", "false")])
        options = root.findall("./ui/tab/menu/option")
        self.assertEqual([o.get("name") for o in options], ["songA", "songB"])
        self.assertEqual(root.find("./ui/tab/menu").get("value"), "1")
        for index, option in enumerate(options):
            bindings = option.findall("binding")
            self.assertEqual([b.get("position") for b in bindings], ["0", "1"])
            self.assertEqual([b.get("translationValue") for b in bindings],
                             ["true" if i == index else "false" for i in range(2)])
            self.assertTrue(all(b.get("parameter") == "ENABLED" and b.get("translation") == "fixed_value" for b in bindings))
        notes = root.findall("./midi/note")
        self.assertEqual([n.get("note") for n in notes], ["34", "35"])
        self.assertEqual([b.get("translationValue") for b in notes[1].findall("binding")], ["false", "true"])

    def test_samples_one_per_key_looping_and_paths_exist(self):
        out, _, root = self.build()
        samples = root.findall("./groups/group[1]/sample")
        self.assertEqual([(s.get("rootNote"), s.get("loNote"), s.get("hiNote")) for s in samples],
                         [("36", "36", "36"), ("37", "37", "37"), ("38", "38", "38")])
        for group in root.findall("./groups/group"):
            for sample in group.findall("sample"):
                self.assertEqual(sample.get("loopEnabled"), "true")
                self.assertTrue((out.parent / sample.get("path")).is_file())

    def test_modes(self):
        _, _, root = self.build(mode="oneshot")
        self.assertTrue(all(g.get("ampEnvEnabled") == "false" for g in root.findall("./groups/group")))
        self.assertIsNone(root.find(".//sample[@loopEnabled]"))
        _, _, root = self.build(mode="hold")
        self.assertIsNone(root.find(".//sample[@loopEnabled]"))
        self.assertIsNone(root.find("./groups/group").get("ampEnvEnabled"))

    def test_crush_adds_knobs_and_global_bit_crusher(self):
        _, _, root = self.build(crush=True)
        self.assertEqual([k.get("label") for k in root.findall("./ui/tab/labeled-knob")], ["Bits", "Rate Div"])
        effects = root.findall("./effects/effect")
        self.assertEqual([e.get("type") for e in effects], ["bit_crusher"])
        self.assertEqual(effects[0].get("bitDepth"), "24")  # clean by default
        self.assertEqual(root.find("./ui/tab/labeled-knob/binding").get("parameter"), "FX_BIT_DEPTH")

    def test_fold_adds_per_group_wave_folder_and_matching_bindings(self):
        _, _, root = self.build(fold=True)
        for group in root.findall("./groups/group"):
            self.assertEqual(group.find("./effects/effect").get("type"), "wave_folder")
            self.assertEqual(group.find("./effects/effect").get("threshold"), "1")  # no folding at unity drive
        bindings = root.findall("./ui/tab/labeled-knob[@label='Fold']/binding")
        self.assertEqual([b.get("groupIndex") for b in bindings], ["0", "1"])
        self.assertTrue(all(b.get("parameter") == "FX_DRIVE" and b.get("level") == "group" for b in bindings))

    def test_keyboard_colours_cover_switch_and_sample_ranges(self):
        _, _, root = self.build()
        colours = [(c.get("loNote"), c.get("hiNote")) for c in root.findall("./ui/keyboard/color")]
        self.assertEqual(colours, [("34", "35"), ("36", "38")])

    def test_xml_special_characters_in_pack_names_are_escaped(self):
        write_wav(self.root / "R&B <night>" / "x.wav")
        _, info, root = self.build()
        self.assertIn("R&B <night>", [g.get("name") for g in root.findall("./groups/group")])

    def test_cli_errors(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = packs_to_dspreset.main([str(self.tmp / "nope"), str(self.tmp / "x.dspreset")])
        self.assertEqual(code, 1)
        self.assertIn("not found", err.getvalue())


if __name__ == "__main__":
    unittest.main()
