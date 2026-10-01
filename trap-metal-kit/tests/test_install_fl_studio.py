"""tools/install_fl_studio.py: finds FL Studio's Hardware folder, installs / backs up / uninstalls, never touches
anything outside its own script folders. Everything runs in temp directories."""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = pathlib.Path(__file__).parent.parent / "tools"
FL_DIR = pathlib.Path(__file__).parent.parent / "fl-studio"
sys.path.insert(0, str(TOOLS))
import install_fl_studio as inst  # noqa: E402


class InstallerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.hw = self.root / "Hardware"
        self.lines = []

    def run_main(self, *argv):
        self.lines.clear()
        return inst.main(list(argv), env={}, home=str(self.root), platform="win32", out=self.lines.append)

    def text(self):
        return "\n".join(self.lines)

    def installed(self, name):
        return self.hw / name / ("device_%s.py" % name)


class FindFolderTest(InstallerCase):
    def make_root(self, *parts):
        path = self.root.joinpath(*parts, "Image-Line", "FL Studio")
        path.mkdir(parents=True)
        return path

    def test_finds_documents_folder_and_points_at_settings_hardware(self):
        root = self.make_root("Documents")
        self.assertEqual(inst.find_hardware_dir(env={}, home=str(self.root), platform="win32"),
                         str(root / "Settings" / "Hardware"))

    def test_none_when_fl_studio_has_never_run(self):
        self.assertIsNone(inst.find_hardware_dir(env={}, home=str(self.root), platform="win32"))

    def test_onedrive_documents_win_over_plain_documents(self):
        self.make_root("Documents")
        onedrive = self.make_root("OneDrive", "Documents")
        found = inst.find_hardware_dir(env={"OneDrive": str(self.root / "OneDrive")}, home=str(self.root), platform="win32")
        self.assertEqual(found, str(onedrive / "Settings" / "Hardware"))

    def test_environment_variable_overrides_everything(self):
        self.make_root("Documents")
        found = inst.find_hardware_dir(env={"FL_STUDIO_HARDWARE": "/x/y"}, home=str(self.root), platform="win32")
        self.assertEqual(found, "/x/y")

    def test_wine_prefix_is_searched_on_linux_only(self):
        wine = self.root / ".wine" / "drive_c" / "users" / "me" / "Documents" / "Image-Line" / "FL Studio"
        wine.mkdir(parents=True)
        self.assertEqual(inst.find_hardware_dir(env={}, home=str(self.root), platform="linux"),
                         str(wine / "Settings" / "Hardware"))
        self.assertIsNone(inst.find_hardware_dir(env={}, home=str(self.root), platform="darwin"))

    def test_no_folder_gives_a_helpful_message_and_nonzero_exit(self):
        self.assertEqual(self.run_main(), 1)
        self.assertIn("--dest", self.text())


class InstallTest(InstallerCase):
    def test_default_installs_only_the_bundle_in_its_own_folder(self):
        self.assertEqual(self.run_main("--dest", str(self.hw)), 0)
        self.assertEqual(sorted(p.name for p in self.hw.iterdir()), ["TrapMetalKit"])
        self.assertEqual(self.installed("TrapMetalKit").read_bytes(), (FL_DIR / "device_TrapMetalKit.py").read_bytes())
        self.assertIn('"Trap Metal Kit (user)"', self.text())
        self.assertIn("Reload", self.text())

    def test_standalone_adds_the_four_separate_scripts(self):
        self.run_main("--dest", str(self.hw), "--standalone")
        self.assertEqual(sorted(p.name for p in self.hw.iterdir()),
                         ["PinkTheme", "PluginProbe", "TrapDJ", "TrapMetalKit", "VocalSetup"])
        for name in inst.STANDALONE:
            self.assertEqual(self.installed(name).read_bytes(), (FL_DIR / ("device_%s.py" % name)).read_bytes())

    def test_standalone_without_bundle(self):
        self.run_main("--dest", str(self.hw), "--standalone", "--no-bundle")
        self.assertFalse(self.installed("TrapMetalKit").exists())
        self.assertTrue(self.installed("TrapDJ").exists())

    def test_no_bundle_alone_is_an_error(self):
        self.assertEqual(self.run_main("--dest", str(self.hw), "--no-bundle"), 1)

    def test_second_run_changes_nothing(self):
        self.run_main("--dest", str(self.hw))
        before = self.installed("TrapMetalKit").stat().st_mtime_ns
        self.run_main("--dest", str(self.hw))
        self.assertIn("unchanged", self.text())
        self.assertEqual(self.installed("TrapMetalKit").stat().st_mtime_ns, before)
        self.assertEqual([p for p in (self.hw / "TrapMetalKit").iterdir() if p.suffix == ".bak"], [])

    def test_an_edited_installed_copy_is_backed_up_before_being_replaced(self):
        self.run_main("--dest", str(self.hw))
        target = self.installed("TrapMetalKit")
        target.write_text("# my own edits\n", encoding="utf-8")
        self.run_main("--dest", str(self.hw))
        backups = [p for p in target.parent.iterdir() if p.name.endswith(".bak")]
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "# my own edits\n")
        self.assertEqual(target.read_bytes(), (FL_DIR / "device_TrapMetalKit.py").read_bytes())

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self.run_main("--dest", str(self.hw), "--standalone", "--dry-run"), 0)
        self.assertFalse(self.hw.exists())
        self.assertIn("would install", self.text())

    def test_other_files_in_the_hardware_folder_are_never_touched(self):
        other = self.hw / "Some Other Controller"
        other.mkdir(parents=True)
        (other / "device_Other.py").write_text("# name=Other\n", encoding="utf-8")
        self.run_main("--dest", str(self.hw), "--standalone")
        self.run_main("--dest", str(self.hw), "--uninstall")
        self.assertEqual((other / "device_Other.py").read_text(encoding="utf-8"), "# name=Other\n")

    def test_a_stale_bundle_is_refused(self):
        with mock.patch.object(inst, "bundle_is_stale", return_value=True):
            self.assertEqual(self.run_main("--dest", str(self.hw)), 1)
        self.assertIn("build_fl_bundle.py", self.text())
        self.assertFalse(self.hw.exists())

    def test_the_committed_bundle_is_not_stale(self):
        self.assertFalse(inst.bundle_is_stale())

    def test_a_script_that_does_not_parse_is_never_copied(self):
        bad = self.root / "device_Bad.py"
        bad.write_text("def (:\n", encoding="utf-8")
        steps = [("TrapDJ", str(bad), str(self.hw / "TrapDJ" / "device_TrapDJ.py"), "new")]
        with self.assertRaises(SyntaxError):
            inst.install(steps, dry_run=False, out=lambda m: None)
        self.assertFalse(self.hw.exists())


class UninstallTest(InstallerCase):
    def test_removes_scripts_and_empty_folders(self):
        self.run_main("--dest", str(self.hw), "--standalone")
        self.assertEqual(self.run_main("--dest", str(self.hw), "--uninstall"), 0)
        self.assertEqual(list(self.hw.iterdir()), [])

    def test_keeps_a_folder_that_still_holds_a_backup(self):
        self.run_main("--dest", str(self.hw))
        self.installed("TrapMetalKit").write_text("# edited\n", encoding="utf-8")
        self.run_main("--dest", str(self.hw))                    # leaves a .bak behind
        self.run_main("--dest", str(self.hw), "--uninstall")
        folder = self.hw / "TrapMetalKit"
        self.assertTrue(folder.exists())
        self.assertEqual([p.name.endswith(".bak") for p in folder.iterdir()], [True])
        self.assertIn("left", self.text())

    def test_uninstall_dry_run_and_empty_folder(self):
        self.run_main("--dest", str(self.hw))
        self.run_main("--dest", str(self.hw), "--uninstall", "--dry-run")
        self.assertTrue(self.installed("TrapMetalKit").exists())
        self.hw_empty = self.root / "Empty"
        self.hw_empty.mkdir()
        self.run_main("--dest", str(self.hw_empty), "--uninstall")
        self.assertIn("nothing to remove", self.text())


if __name__ == "__main__":
    unittest.main()
