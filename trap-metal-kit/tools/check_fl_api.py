#!/usr/bin/env python3
"""Check FL Studio scripts against Image-Line's real API stubs (the `fl-studio-api-stubs` package).

The kit's own tests run the scripts against small stand-ins for FL's modules, which can only prove the scripts do
what their author *thinks* the API does. This checks the other half: that every `mixer.x(...)`, `playlist.y(...)`,
`midi.Z` and so on actually exists in FL's API, that each call's arguments fit the real signature, and that the
callbacks you define (OnNoteOn, OnIdle, ...) are names FL will call.

    pip install fl-studio-api-stubs
    python3 tools/check_fl_api.py                       # every fl-studio/device_*.py
    python3 tools/check_fl_api.py fl-studio/device_TrapMetalKit.py

Exit status 0 = clean, 1 = problems found, 2 = the stubs package is not installed.
It only reads the scripts; it never imports them.
"""
import argparse
import ast
import glob
import importlib
import inspect
import os
import sys

FL_MODULES = ("arrangement", "channels", "device", "general", "midi", "mixer", "patterns", "playlist",
              "plugins", "screen", "transport", "ui", "utils")

# Callbacks FL looks for in device_*.py (from the stubs' `callbacks` page).
FL_CALLBACKS = {
    "OnInit", "OnDeInit", "OnMidiIn", "OnMidiMsg", "OnNoteOn", "OnNoteOff", "OnControlChange", "OnProgramChange",
    "OnPitchBend", "OnKeyPressure", "OnChannelPressure", "OnSysEx", "OnMidiOutMsg", "OnIdle", "OnRefresh",
    "OnDoFullRefresh", "OnUpdateBeatIndicator", "OnDisplayZone", "OnUpdateLiveMode", "OnDirtyMixerTrack",
    "OnDirtyChannel", "OnFirstConnect", "OnProjectLoad", "OnUpdateMeters", "OnWaitingForInput", "OnSendTempMsg",
}


def load_stubs():
    """Import the real stub modules, or return None when the package is not installed."""
    loaded = {}
    for name in FL_MODULES:
        try:
            loaded[name] = importlib.import_module(name)
        except ImportError:
            return None
    return loaded


def _placeholder_args(call):
    """Positional / keyword placeholders for a call; None when it uses *args or **kwargs (cannot be bound)."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return None
    return [0] * len(call.args), {k.arg: 0 for k in call.keywords}


def check_source(source, filename, stubs):
    """Return a list of 'file:line: message' problems for one script's source."""
    tree = ast.parse(source, filename)
    problems = []
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    local_mods = {m for m in imported if m in FL_MODULES}

    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in local_mods:
                called.add(id(func))
                mod, attr = func.value.id, func.attr
                target = getattr(stubs[mod], attr, None)
                where = "%s:%d" % (filename, node.lineno)
                if target is None:
                    problems.append("%s: %s.%s does not exist in the FL API" % (where, mod, attr))
                    continue
                if not callable(target):
                    problems.append("%s: %s.%s is not callable" % (where, mod, attr))
                    continue
                args = _placeholder_args(node)
                if args is None:
                    continue
                try:
                    inspect.signature(target).bind(*args[0], **args[1])
                except TypeError as exc:
                    problems.append("%s: %s.%s called wrongly: %s" % (where, mod, attr, exc))
        elif isinstance(node, ast.Attribute):
            pass
    # constants and other attribute reads: midi.TLC_Fill, ...
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and id(node) not in called and isinstance(node.value, ast.Name)
                and node.value.id in local_mods and not hasattr(stubs[node.value.id], node.attr)):
            problems.append("%s:%d: %s.%s does not exist in the FL API" % (filename, node.lineno, node.value.id, node.attr))

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("On") and node.name[2:3].isupper():
            if node.name not in FL_CALLBACKS:
                problems.append("%s:%d: %s() is not a callback FL calls" % (filename, node.lineno, node.name))
    return problems


def check_file(path, stubs):
    with open(path, encoding="utf-8") as handle:
        return check_source(handle.read(), os.path.basename(path), stubs)


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Check FL Studio scripts against FL's real API stubs.")
    parser.add_argument("scripts", nargs="*", help="scripts to check (default: fl-studio/device_*.py)")
    args = parser.parse_args(argv)
    paths = args.scripts or sorted(glob.glob(os.path.join(here, "..", "fl-studio", "device_*.py")))
    stubs = load_stubs()
    if stubs is None:
        print("The FL API stubs are not installed. Run:  pip install fl-studio-api-stubs", file=sys.stderr)
        return 2
    bad = 0
    for path in paths:
        problems = check_file(path, stubs)
        print("%-34s %s" % (os.path.basename(path), "OK" if not problems else "%d problem(s)" % len(problems)))
        for problem in problems:
            print("    " + problem)
        bad += len(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
