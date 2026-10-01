"""Tests for tools/scan_audio_setup.py against a fake Windows-style tree in a temp folder."""
import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

import scan_audio_setup as scan  # noqa: E402

SECRET = "SECRET-FILE-CONTENT"


def touch(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class FakePc(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "Users" / "beatmaker"
        pf = self.tmp / "Program Files"
        self.env = {"PROGRAMFILES": str(pf), "PROGRAMFILES(X86)": str(self.tmp / "pf86"),
                    "COMMONPROGRAMFILES": str(pf / "Common Files"), "PUBLIC": str(self.tmp / "Public")}
        vst3 = pf / "Common Files" / "VST3"
        (vst3 / "Unison" / "Mangler.vst3").mkdir(parents=True)
        (vst3 / "Unison" / "Drum Monkey.vst3").mkdir(parents=True)
        (vst3 / "FabFilter" / "FabFilter Pro-Q 4.vst3").mkdir(parents=True)
        (vst3 / "Some Vendor" / "Odd Tool.vst3").mkdir(parents=True)
        touch(vst3 / "Serum.vst3")
        touch(pf / "VSTPlugins" / "OTT.dll")
        touch(pf / "VSTPlugins" / "unins000.dll")                                 # should be ignored
        touch(pf / "Image-Line" / "FL Studio 2025" / "Plugins" / "Fruity" / "Effects" / "Fruity Limiter" / "Fruity Limiter.dll")
        db = self.home / "Documents" / "Image-Line" / "FL Studio" / "Presets" / "Plugin database" / "Installed" / "Effects" / "VST3"
        touch(db / "Pitcher.fst")
        touch(db / "Pitcher.nfo")
        touch(db / "FabFilter Pro-Q 4.fst")
        touch(self.home / "Documents" / "Native Instruments" / "User Content" / "readme.txt")
        touch(pf / "Native Instruments" / "Kontakt 8" / "Kontakt 8.exe")
        touch(self.tmp / "KontaktLibs" / "Rage Drums" / "Rage Drums.nicnt")
        dl = self.home / "Downloads"
        touch(dl / "Ozone_Installer.exe")
        touch(dl / "808 pack.zip")
        touch(dl / "notes.txt", SECRET)
        for i in range(3):
            touch(dl / "Rage Kit" / "drums" / f"kick{i}.wav")
        touch(dl / "Empty Folder" / "readme.md")
        touch(self.home / "Documents" / "Beats" / "song.flp")

    def roots(self):
        return scan.default_roots("Windows", self.env, self.home)


class ScanTest(FakePc):
    def test_default_roots_keeps_only_existing_folders(self):
        roots = self.roots()
        self.assertTrue(any(str(p).endswith("VST3") for p in roots["plugins"]))
        self.assertTrue(any("FL Studio 2025" in str(p) for p in roots["plugins"]))
        self.assertNotIn(str(self.tmp / "pf86" / "VSTPlugins"), [str(p) for p in roots["plugins"]])
        self.assertEqual([p.name for p in roots["downloads"]], ["Downloads"])

    def test_plugins_are_classified_with_vendor_and_role(self):
        result = scan.scan(self.roots())
        by_name = {p["name"]: p for p in result["plugins"]}
        self.assertEqual((by_name["Mangler"]["vendor"], by_name["Mangler"]["role"]), ("Unison", "distortion"))
        self.assertEqual(by_name["Drum Monkey"]["role"], "drums (loop generator)")
        self.assertEqual(by_name["FabFilter Pro-Q 4"]["role"], "EQ")
        self.assertEqual(by_name["Serum"]["role"], "synth")
        self.assertEqual(by_name["OTT"]["role"], "multiband compressor")
        self.assertEqual(by_name["Fruity Limiter"]["vendor"], "Image-Line")
        self.assertEqual(by_name["Odd Tool"]["vendor"], "Some Vendor")            # unknown plugin: vendor from its folder
        self.assertEqual(by_name["Odd Tool"]["role"], "")
        self.assertNotIn("unins000", by_name)

    def test_fl_database_lists_scanned_plugins_once(self):
        result = scan.scan(self.roots())
        names = [p["name"] for p in result["fl_database"]]
        self.assertEqual(sorted(names), ["FabFilter Pro-Q 4", "Pitcher"])
        pitcher = next(p for p in result["fl_database"] if p["name"] == "Pitcher")
        self.assertEqual(pitcher["role"], "vocal tuning")

    def test_native_instruments_libraries_found_with_library_root(self):
        roots = self.roots()
        roots["native"] = roots["native"] + [self.tmp / "KontaktLibs"]
        native = scan.scan(roots)["native"]
        self.assertEqual(native["libraries"], ["Rage Drums"])
        self.assertIn("Kontakt 8", native["top_level"])

    def test_downloads_are_bucketed_by_name_and_audio_count(self):
        dl = scan.scan(self.roots())["downloads"][0]
        self.assertEqual(dl["installers"], ["Ozone_Installer.exe"])
        self.assertEqual(dl["archives"], ["808 pack.zip"])
        self.assertEqual(dl["sample_folders"], [{"folder": "Rage Kit", "audio_files": 3}])
        self.assertEqual(dl["other_entries"], 2)                                    # notes.txt + Empty Folder

    def test_documents_lists_top_level_folders_only(self):
        docs = scan.scan(self.roots())["documents"][0]["folders"]
        self.assertEqual(docs, ["Beats", "Image-Line", "Native Instruments"])

    def test_role_coverage_reports_gaps(self):
        coverage = scan.role_coverage(scan.scan(self.roots()))
        self.assertEqual(coverage["tuning"], ["Pitcher"])                            # from the FL database
        self.assertIn("Mangler", coverage["saturation / distortion"])
        self.assertIn("FabFilter Pro-Q 4", coverage["EQ / de-harsh"])
        self.assertIn("Fruity Limiter", coverage["limiting / mastering"])
        self.assertEqual(coverage["loudness metering"], [])                          # nothing owned -> a gap
        self.assertEqual(coverage["mix / vocal assistant"], [])

    def add_izotope(self):
        vst3 = pathlib.Path(self.env["COMMONPROGRAMFILES"]) / "VST3"
        for name in ("iZotope Nectar 4.vst3", "iZotope Ozone 12.vst3", "Ozone Imager.vst3", "Vocal Doubler.vst3", "Youlean Loudness Meter 2.vst3"):
            (vst3 / name).mkdir(parents=True, exist_ok=True)

    def test_owning_nectar_and_ozone_fills_assistant_roles_directly_and_the_rest_with_a_star(self):
        self.add_izotope()
        coverage = scan.role_coverage(scan.scan(self.roots()))
        self.assertEqual(coverage["mix / vocal assistant"], ["iZotope Nectar 4"])          # its own role: no star
        self.assertIn("iZotope Ozone 12", coverage["limiting / mastering"])                # 'mastering assistant' matches directly
        self.assertIn("Fruity Limiter", coverage["limiting / mastering"])
        self.assertIn("iZotope Nectar 4*", coverage["tuning"])                             # via the suite -> starred
        self.assertIn("Pitcher", coverage["tuning"])                                       # direct, unstarred
        self.assertIn("iZotope Nectar 4*", coverage["saturation / distortion"])
        self.assertIn("Mangler", coverage["saturation / distortion"])
        self.assertIn("iZotope Nectar 4*", coverage["reverb / delay"])
        self.assertEqual(coverage["loudness metering"], ["Youlean Loudness Meter 2"])      # a real meter, direct

    def test_imager_and_doubler_are_not_treated_as_the_full_suites(self):
        self.add_izotope()
        by_name = {p["name"]: p for p in scan.scan(self.roots())["plugins"]}
        self.assertEqual(by_name["Ozone Imager"]["role"], "stereo imaging")
        self.assertEqual(by_name["Vocal Doubler"]["role"], "vocal effect (doubler)")
        self.assertEqual(scan.suite_roles("Ozone Imager"), [])
        self.assertEqual(scan.suite_roles("Vocal Doubler"), [])
        coverage = scan.role_coverage(scan.scan(self.roots()))
        self.assertNotIn("Ozone Imager*", sum(coverage.values(), []))

    def test_report_explains_the_star(self):
        self.add_izotope()
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(scan.platform, "system", return_value="Windows"), \
                contextlib.redirect_stdout(out):
            scan.main(["--home", str(self.home), "--out", str(self.tmp / "inv.md"), "--json", str(self.tmp / "inv.json")])
        md = (self.tmp / "inv.md").read_text()
        self.assertIn("`*` = provided by a suite you own", md)
        self.assertIn("iZotope Nectar 4*", md)

    def test_classify_examples(self):
        self.assertEqual(scan.classify("Soundtoys Little AlterBoy"), ("Soundtoys", "vocal tuning / formant"))
        self.assertEqual(scan.classify("iZotope Nectar 4"), ("iZotope", "vocal chain assistant"))
        self.assertEqual(scan.classify("Youlean Loudness Meter 2"), ("Youlean", "loudness metering"))
        self.assertEqual(scan.classify("Totally Unknown"), (None, None))

    def test_short_names_need_word_boundaries(self):
        self.assertEqual(scan.classify("OTT"), ("Xfer", "multiband compressor"))
        self.assertEqual(scan.classify("Xfer OTT x64"), ("Xfer", "multiband compressor"))
        self.assertEqual(scan.classify("SPAN Plus"), ("Voxengo", "metering"))
        self.assertEqual(scan.classify("Scott Bottle Tool"), (None, None))       # 'ott' inside words
        self.assertEqual(scan.classify("Spanner"), (None, None))
        self.assertEqual(scan.classify("Reflex Machine"), (None, None))         # 'flex' inside a word
        self.assertEqual(scan.classify("Soothe2")[1], "resonance suppressor")    # long needles may prefix-match


class CliTest(FakePc):
    def run_cli(self, *extra):
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(scan.platform, "system", return_value="Windows"), \
                contextlib.redirect_stdout(out):
            code = scan.main(["--home", str(self.home), "--out", str(self.tmp / "inv.md"),
                              "--json", str(self.tmp / "inv.json"), *extra])
        return code, out.getvalue()

    def test_writes_report_that_names_files_but_never_reads_them(self):
        code, text = self.run_cli()
        self.assertEqual(code, 0)
        md = (self.tmp / "inv.md").read_text()
        js = (self.tmp / "inv.json").read_text()
        for needle in ("Mangler", "Drum Monkey", "Pitcher", "Ozone_Installer.exe", "Rage Kit (3 audio files)", "**GAP**"):
            self.assertIn(needle, md)
        self.assertNotIn(SECRET, md + js)                                          # file contents are never read
        self.assertEqual(json.loads(js)["role_coverage"]["tuning"], ["Pitcher"])
        self.assertIn("Vocal-chain gaps:", text)

    def test_redact_user_hides_the_user_name(self):
        self.run_cli("--redact-user")
        md = (self.tmp / "inv.md").read_text()
        self.assertNotIn("beatmaker", md)
        self.assertIn("<user>", md)

    def test_extra_and_library_root_are_scanned_and_missing_ones_are_reported(self):
        (self.tmp / "ExtraVst").mkdir()
        touch(self.tmp / "ExtraVst" / "Decapitator.vst3")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _ = self.run_cli("--extra", str(self.tmp / "ExtraVst"), "--extra", str(self.tmp / "nope"),
                                   "--library-root", str(self.tmp / "KontaktLibs"))
        self.assertEqual(code, 0)
        md = (self.tmp / "inv.md").read_text()
        self.assertIn("Decapitator", md)
        self.assertIn("Rage Drums", md)
        self.assertIn("nope does not exist", err.getvalue())

    def test_empty_machine_still_produces_a_report(self):
        empty_home = self.tmp / "empty_home"
        empty_home.mkdir()
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"PROGRAMFILES": str(self.tmp / "none")}), \
                mock.patch.object(scan.platform, "system", return_value="Windows"), contextlib.redirect_stdout(out):
            code = scan.main(["--home", str(empty_home), "--out", str(self.tmp / "e.md"), "--json", str(self.tmp / "e.json")])
        self.assertEqual(code, 0)
        self.assertIn("0 plugins", out.getvalue())
        self.assertIn("GAP", (self.tmp / "e.md").read_text())


if __name__ == "__main__":
    unittest.main()
