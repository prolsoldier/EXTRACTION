#!/usr/bin/env python3
"""Build fl-studio/device_TrapMetalKit.py: the four FL Studio scripts in ONE file, so one MIDI input runs them all.

FL Studio runs a single controller script per MIDI input, and Image-Line's manual does not promise that a script can
import other files from its folder. So the bundle is self-contained: each source script is embedded verbatim and
run in its own module namespace (names like `rgb_to_fl` or `MAX_SLOTS` cannot collide), and a thin dispatcher at
the bottom hands every FL callback to each part.

    python3 tools/build_fl_bundle.py            # rewrite fl-studio/device_TrapMetalKit.py
    python3 tools/build_fl_bundle.py --check    # exit 1 if the committed bundle is out of date (CI / tests use this)

The standalone device_*.py files stay the source of truth. Edit those, then rebuild.
"""
import argparse
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FL_DIR = os.path.join(HERE, "..", "fl-studio")
TEMPLATE = os.path.join(HERE, "fl_bundle_template.txt")
OUTPUT = os.path.join(FL_DIR, "device_TrapMetalKit.py")

SECTIONS = ["TrapDJ", "VocalSetup", "PluginProbe", "PinkTheme"]   # same order as SECTION_ORDER in the template

# FL reads these from the top of a device script. Inside an embedded source they must not look like headers.
_HEADER = re.compile(r"^(#\s*)(name|url|receiveFrom|supportedDevices|supportedHardwareIds)\s*=\s*", re.IGNORECASE)


def neutralise_headers(source):
    """Turn `# name=X` style header lines into `# name: X`, keeping every line number the same."""
    return "\n".join(_HEADER.sub(lambda m: "%s%s: " % (m.group(1), m.group(2)), line) for line in source.split("\n"))


def read_section(name):
    with open(os.path.join(FL_DIR, "device_%s.py" % name), encoding="utf-8") as handle:
        source = handle.read()
    if "'''" in source:
        raise SystemExit("device_%s.py contains ''' which cannot be embedded in a raw string; use \"\"\" instead" % name)
    if not source.endswith("\n"):
        source += "\n"
    return neutralise_headers(source)


def build():
    """Return the full text of the bundle."""
    sources = {name: read_section(name) for name in SECTIONS}
    digest = hashlib.sha1()
    for name in SECTIONS:
        digest.update(name.encode() + b"\0" + sources[name].encode("utf-8"))
    build_id = digest.hexdigest()[:8]
    with open(TEMPLATE, encoding="utf-8") as handle:
        template = handle.read()
    blocks = ['BUILD = "%s"' % build_id, "", "_SOURCES = {"]
    for name in SECTIONS:
        blocks.append("")
        blocks.append("# " + "=" * 8 + " embedded verbatim from fl-studio/device_%s.py " % name + "=" * 8)
        blocks.append("%r: r'''" % name + sources[name] + "''',")
    blocks.append("}")
    text = template.replace("@@BUILD@@", build_id).replace("@@SECTIONS@@", "\n".join(blocks))
    compile(text, "device_TrapMetalKit.py", "exec")   # a bundle that does not parse must never be written
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the one-file FL Studio bundle.")
    parser.add_argument("--check", action="store_true", help="do not write; exit 1 if the bundle is out of date")
    args = parser.parse_args(argv)
    text = build()
    if args.check:
        try:
            with open(OUTPUT, encoding="utf-8") as handle:
                current = handle.read()
        except FileNotFoundError:
            current = None
        if current != text:
            print("device_TrapMetalKit.py is out of date; run: python3 tools/build_fl_bundle.py", file=sys.stderr)
            return 1
        print("device_TrapMetalKit.py is up to date")
        return 0
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("wrote %s (%d lines)" % (os.path.normpath(OUTPUT), text.count("\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
