#!/usr/bin/env python3
"""Install the Trap Metal Kit scripts into FL Studio's user Hardware folder (standard library only).

    python3 tools/install_fl_studio.py                  # installs the one-file bundle ("Trap Metal Kit")
    python3 tools/install_fl_studio.py --dry-run        # show what it would do, change nothing
    python3 tools/install_fl_studio.py --standalone     # also install the four separate scripts
    python3 tools/install_fl_studio.py --dest "D:/FL/Settings/Hardware"    # FL's user data is somewhere unusual
    python3 tools/install_fl_studio.py --uninstall      # remove what this script installed

FL Studio loads user scripts from  <Documents>/Image-Line/FL Studio/Settings/Hardware/<name>/device_<name>.py
(Image-Line's MIDI scripting manual). This puts each script in its own <name> folder there. A file that is already
there and differs is kept as <file>.<timestamp>.bak before it is replaced, so edits you made to the installed
copy are never lost. Nothing outside those folders is touched.
"""
import argparse
import datetime
import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FL_DIR = os.path.join(HERE, "..", "fl-studio")

BUNDLE = ["TrapMetalKit"]
STANDALONE = ["TrapDJ", "VocalSetup", "PluginProbe", "PinkTheme"]
ALL_NAMES = BUNDLE + STANDALONE
DISPLAY_NAMES = {"TrapMetalKit": "Trap Metal Kit", "TrapDJ": "Trap DJ Keys", "VocalSetup": "Vocal Session Setup",
                 "PluginProbe": "Plugin Probe", "PinkTheme": "Pink Theme Painter"}


def candidate_roots(env, home, platform):
    """Possible '<Documents>/Image-Line/FL Studio' folders, best guess first."""
    roots = []
    tail = os.path.join("Image-Line", "FL Studio")
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):   # Windows often redirects Documents here
        if env.get(var):
            roots.append(os.path.join(env[var], "Documents", tail))
    roots.append(os.path.join(home, "Documents", tail))
    if platform.startswith("linux"):                                       # FL under Wine
        roots.extend(sorted(glob.glob(os.path.join(home, ".wine", "drive_c", "users", "*", "Documents", tail))))
    return roots


def find_hardware_dir(env=None, home=None, platform=None):
    """The Hardware folder of the first FL Studio user-data folder that exists, or None."""
    env = os.environ if env is None else env
    home = os.path.expanduser("~") if home is None else home
    platform = sys.platform if platform is None else platform
    if env.get("FL_STUDIO_HARDWARE"):
        return env["FL_STUDIO_HARDWARE"]
    for root in candidate_roots(env, home, platform):
        if os.path.isdir(root):
            return os.path.join(root, "Settings", "Hardware")
    return None


def _read(path):
    with open(path, "rb") as handle:
        return handle.read()


def plan(hardware_dir, names):
    """[(name, source, destination, status)]; status is 'new', 'update' (differs) or 'unchanged'."""
    steps = []
    for name in names:
        source = os.path.join(FL_DIR, "device_%s.py" % name)
        destination = os.path.join(hardware_dir, name, "device_%s.py" % name)
        if not os.path.isfile(destination):
            status = "new"
        elif _read(source) == _read(destination):
            status = "unchanged"
        else:
            status = "update"
        steps.append((name, source, destination, status))
    return steps


def bundle_is_stale():
    """True when device_TrapMetalKit.py no longer matches the four scripts it is built from."""
    sys.path.insert(0, HERE)
    try:
        import build_fl_bundle
        return build_fl_bundle.build() != _read(build_fl_bundle.OUTPUT).decode("utf-8")
    except FileNotFoundError:
        return True
    finally:
        sys.path.remove(HERE)


def install(steps, dry_run, out=print):
    for name, source, destination, status in steps:
        compile(_read(source), source, "exec")   # never copy a script that does not even parse
        label = "%-18s %s" % (DISPLAY_NAMES[name], destination)
        if status == "unchanged":
            out("  unchanged  " + label)
            continue
        if dry_run:
            out("  would %s  %s" % ("install" if status == "new" else "replace", label))
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if status == "update":
            backup = "%s.%s.bak" % (destination, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
            shutil.copy2(destination, backup)
            out("  backed up  %s" % backup)
        shutil.copyfile(source, destination)
        out("  installed  " + label)


def uninstall(hardware_dir, dry_run, out=print):
    removed = 0
    for name in ALL_NAMES:
        folder = os.path.join(hardware_dir, name)
        target = os.path.join(folder, "device_%s.py" % name)
        if not os.path.isfile(target):
            continue
        removed += 1
        if dry_run:
            out("  would remove  " + target)
            continue
        os.remove(target)
        out("  removed  " + target)
        if not os.listdir(folder):
            os.rmdir(folder)
        else:
            out("  (left %s: it still holds other files, e.g. your .bak copies)" % folder)
    if not removed:
        out("  nothing to remove in " + hardware_dir)
    return removed


NEXT_STEPS = """
Next, in FL Studio:
  1. Options > MIDI Settings (F10).
  2. Under Input, click your keyboard / pad controller and tick Enable.
  3. Set Controller type to %s and give it a Port number.
       (Already open? Use the Reload button there instead of restarting FL Studio.)
  4. Open View > Script output: you should see a "Trap Metal Kit: ready" line and the key map.
Full walk-through: docs/00-fl-studio-quickstart.md
"""


def main(argv=None, env=None, home=None, platform=None, out=print):
    parser = argparse.ArgumentParser(description="Install the Trap Metal Kit scripts into FL Studio.")
    parser.add_argument("--dest", help="FL Studio's user Hardware folder (default: auto-detected)")
    parser.add_argument("--standalone", action="store_true", help="also install the four separate scripts")
    parser.add_argument("--no-bundle", action="store_true", help="skip the one-file bundle (use with --standalone)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen; change nothing")
    parser.add_argument("--uninstall", action="store_true", help="remove the scripts this tool installed")
    args = parser.parse_args(argv)

    hardware = args.dest or find_hardware_dir(env, home, platform)
    if hardware is None:
        out("Could not find FL Studio's user data folder (looked for Documents/Image-Line/FL Studio).\n"
            "Run FL Studio once so it creates it, or pass the Hardware folder yourself:\n"
            "  python3 tools/install_fl_studio.py --dest \"<Documents>/Image-Line/FL Studio/Settings/Hardware\"")
        return 1
    out("Using FL Studio Hardware folder: " + hardware)

    if args.uninstall:
        uninstall(hardware, args.dry_run, out)
        return 0

    names = ([] if args.no_bundle else BUNDLE) + (STANDALONE if args.standalone else [])
    if not names:
        out("Nothing selected: --no-bundle needs --standalone.")
        return 1
    if "TrapMetalKit" in names and bundle_is_stale():
        out("fl-studio/device_TrapMetalKit.py is out of date. Run  python3 tools/build_fl_bundle.py  first.")
        return 1
    install(plan(hardware, names), args.dry_run, out)
    if not args.dry_run:
        shown = BUNDLE if "TrapMetalKit" in names else names   # the bundle covers everything, so name only it
        out(NEXT_STEPS % " or ".join('"%s (user)"' % DISPLAY_NAMES[n] for n in shown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
