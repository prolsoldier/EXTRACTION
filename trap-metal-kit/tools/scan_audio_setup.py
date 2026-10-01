#!/usr/bin/env python3
"""Inventory the plugins, libraries and downloads on this computer and report which vocal-chain roles you can fill.

Run it ON THE COMPUTER THAT HAS YOUR FL STUDIO / KONTAKT / PLUGINS (it cannot see other machines):

    python3 scan_audio_setup.py                      # writes audio_inventory.md and audio_inventory.json
    python3 scan_audio_setup.py --redact-user        # hides your user name in the paths
    python3 scan_audio_setup.py --extra "D:\\Kontakt Libraries" --extra "E:\\VST"

What it reads: FOLDER AND FILE NAMES (and counts) only. It never opens, uploads or modifies a file. Nothing leaves
your machine unless you choose to share the .md report. Look over the report before you share it.

Where it looks (whatever exists):
    plugin folders   VST3 / VST2 / AU folders, FL Studio's own Plugins folders
    FL database      Documents/Image-Line/FL Studio/Presets/Plugin database (the plugins FL has scanned)
    Native Instr.    Program Files/Native Instruments, Documents/Native Instruments, *.nicnt library files
    Downloads        top-level names only: installers, archives, sample-pack folders (audio file counts)
    Documents        top-level folder names only
"""
import argparse
import json
import os
import platform
import re
import sys
from collections import defaultdict
from pathlib import Path

PLUGIN_SUFFIXES = {".vst3": "VST3", ".dll": "VST2", ".component": "AU", ".vst": "VST2", ".fst": "FL database", ".nfo": None}
INSTALLER_SUFFIXES = {".exe", ".msi", ".dmg", ".pkg"}
ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z", ".tar", ".gz"}
AUDIO_SUFFIXES = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}
SKIP_DLL_WORDS = ("unins", "uninstall", "setup", "vcruntime", "msvcp", "ucrtbase", "api-ms")

# (substring in lower-cased plugin/file name, vendor, role). First match wins; keep specific names first.
KNOWN = [
    # Unison Audio (verified against unison.audio/plugin-pass)
    ("midi wizard", "Unison", "generative MIDI (chords/melodies)"),
    ("chord genie", "Unison", "generative MIDI (chords/melodies)"),
    ("drum monkey", "Unison", "drums (loop generator)"),
    ("bass dragon", "Unison", "bass / 808 patterns"),
    ("808 machine", "Unison", "bass / 808 sounds"),
    ("sound doctor", "Unison", "FX-chain generator"),
    ("unisynth", "Unison", "synth (generative)"),
    ("mangler", "Unison", "distortion"),
    # vocal tuning / effects
    ("auto-tune", "Antares", "vocal tuning"), ("autotune", "Antares", "vocal tuning"),
    ("graillon", "Auburn Sounds", "vocal tuning / effect"), ("melodyne", "Celemony", "vocal tuning"),
    ("waves tune", "Waves", "vocal tuning"), ("mautopitch", "MeldaProduction", "vocal tuning"),
    ("pitcher", "Image-Line", "vocal tuning"), ("newtone", "Image-Line", "vocal tuning"),
    ("alterboy", "Soundtoys", "vocal tuning / formant"), ("vocodex", "Image-Line", "vocal effect (vocoder)"),
    ("vocal doubler", "iZotope", "vocal effect (doubler)"), ("nectar", "iZotope", "vocal chain assistant"),
    ("vocalsynth", "iZotope", "vocal effect"),
    # mixing assistants / mastering
    ("neutron", "iZotope", "mix assistant"), ("ozone imager", "iZotope", "stereo imaging"),
    ("ozone", "iZotope", "mastering assistant"), ("tonal balance", "iZotope", "metering"), ("insight", "iZotope", "metering"),
    ("trash", "iZotope", "saturation / distortion"), ("rx", "iZotope", "audio repair"), ("relay", "iZotope", "utility"),
    ("landr", "LANDR", "mastering"), ("smart:eq", "Sonible", "assistant EQ"), ("smart:comp", "Sonible", "assistant compressor"),
    ("smart:limit", "Sonible", "assistant limiter"), ("gullfoss", "Soundtheory", "automatic EQ"),
    # dynamics / EQ / de-harsh
    ("soothe", "oeksound", "resonance suppressor"), ("pro-q", "FabFilter", "EQ"), ("pro-c", "FabFilter", "compressor"),
    ("pro-l", "FabFilter", "limiter"), ("pro-ds", "FabFilter", "de-esser"), ("pro-mb", "FabFilter", "multiband"),
    ("pro-r", "FabFilter", "reverb"), ("saturn", "FabFilter", "saturation / distortion"), ("timeless", "FabFilter", "delay"),
    ("fruity parametric eq", "Image-Line", "EQ"), ("fruity compressor", "Image-Line", "compressor"),
    ("fruity limiter", "Image-Line", "limiter"), ("maximus", "Image-Line", "multiband / limiter"),
    ("emphasis", "Image-Line", "EQ / mastering tilt"), ("soft clipper", "Image-Line", "saturation / distortion"),
    ("distructor", "Image-Line", "saturation / distortion"), ("blood overdrive", "Image-Line", "saturation / distortion"),
    ("waveshaper", "Image-Line", "saturation / distortion"), ("reeverb", "Image-Line", "reverb"), ("luxeverb", "Image-Line", "reverb"),
    ("fruity delay", "Image-Line", "delay"), ("gross beat", "Image-Line", "creative effect"), ("hyper chorus", "Image-Line", "chorus / width"),
    ("kotelnikov", "Tokyo Dawn Labs", "compressor"), ("tdr nova", "Tokyo Dawn Labs", "dynamic EQ"),
    ("decapitator", "Soundtoys", "saturation / distortion"), ("echoboy", "Soundtoys", "delay"),
    ("devil-loc", "Soundtoys", "saturation / distortion"), ("crystallizer", "Soundtoys", "creative effect"),
    ("rc-20", "XLN Audio", "saturation / lo-fi"), ("decimort", "D16", "bit crusher"), ("shaperbox", "Cableguys", "creative / sidechain"),
    ("kickstart", "Nicky Romero", "sidechain"), ("ott", "Xfer", "multiband compressor"),
    ("texture", "Devious Machines", "saturation / distortion"), ("infiltrator", "Devious Machines", "creative effect"),
    ("valhalla", "Valhalla DSP", "reverb / delay"), ("supermassive", "Valhalla DSP", "reverb / delay"),
    # metering
    ("youlean", "Youlean", "loudness metering"), ("span", "Voxengo", "metering"),
    # instruments
    ("serum", "Xfer", "synth"), ("vital", "Vital Audio", "synth"), ("omnisphere", "Spectrasonics", "synth"),
    ("kontakt", "Native Instruments", "sampler"), ("sublab", "Future Audio Workshop", "bass / 808"),
    ("minibit", "AudioThing", "synth"), ("fpc", "Image-Line", "drums"), ("sytrus", "Image-Line", "synth"),
    ("harmor", "Image-Line", "synth"), ("flex", "Image-Line", "synth"), ("decent", "DecentSampler", "sampler"),
    ("sfizz", "sfztools", "sampler"), ("serato sample", "Serato", "sampler / chops"), ("arcade", "Output", "sampler / loops"),
]

# Suites that bundle several roles. The bundled modules depend on the EDITION you own (e.g. Nectar 4 Auto-Level and its
# 13 component plugins are Advanced-only; Ozone 12 Elements is macro-only), so a role covered only through a suite is
# reported with a trailing '*' meaning "if your edition includes that module". Sources: iZotope's Nectar 4 and Ozone 12
# articles (Nectar: Pitch/Melodyne, Compressor, Saturation, Reverb, Delay, De-esser, Unmask EQ; Ozone: EQ, limiter).
SUITES = {
    "nectar": ["vocal tuning", "EQ", "compressor", "saturation / distortion", "reverb", "delay"],
    "ozone": ["EQ", "limiter", "mastering"],
}

# What a full vocal chain needs. A role is "covered" if any owned plugin's role string contains one of these words.
VOCAL_ROLES = {
    "tuning": ("vocal tuning",),
    "EQ / de-harsh": ("EQ", "resonance"),
    "compression": ("compressor",),
    "saturation / distortion": ("distortion", "saturation"),
    "reverb / delay": ("reverb", "delay"),
    "limiting / mastering": ("limiter", "mastering"),
    "loudness metering": ("metering",),
    "mix / vocal assistant": ("mix assistant", "vocal chain"),
}


def _needle_matches(needle, lowered):
    """Match at a word start (so 'ott' is not found in 'scott'); short needles must also end a word."""
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + (r"(?![a-z0-9])" if len(needle) <= 4 else "")
    return re.search(pattern, lowered) is not None


def classify(name):
    lowered = name.lower()
    for needle, vendor, role in KNOWN:
        if _needle_matches(needle, lowered):
            return vendor, role
    return None, None


def default_roots(system, env, home):
    """Folders to look in, by purpose. Only existing ones get scanned. `env` is os.environ-like."""
    home = Path(home)
    roots = defaultdict(list)
    if system == "Windows":
        pf = Path(env.get("PROGRAMFILES", r"C:\Program Files"))
        pf86 = Path(env.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        common = Path(env.get("COMMONPROGRAMFILES", str(pf / "Common Files")))
        public = Path(env.get("PUBLIC", r"C:\Users\Public"))
        docs = home / "Documents"
        roots["plugins"] += [common / "VST3", pf / "VSTPlugins", pf / "Steinberg" / "VSTPlugins",
                             pf86 / "VSTPlugins", pf / "Common Files" / "VST2", common / "VST2"]
        roots["plugins"] += sorted((pf / "Image-Line").glob("FL Studio*/Plugins")) if (pf / "Image-Line").exists() else []
        roots["plugins"] += sorted((pf86 / "Image-Line").glob("FL Studio*/Plugins")) if (pf86 / "Image-Line").exists() else []
        roots["fl_database"] += [docs / "Image-Line" / "FL Studio" / "Presets" / "Plugin database"]
        roots["native"] += [pf / "Native Instruments", docs / "Native Instruments", public / "Documents" / "Native Instruments"]
        roots["downloads"] += [home / "Downloads"]
        roots["documents"] += [docs]
    elif system == "Darwin":
        for base in (Path("/Library/Audio/Plug-Ins"), home / "Library" / "Audio" / "Plug-Ins"):
            roots["plugins"] += [base / "VST3", base / "VST", base / "Components"]
        roots["fl_database"] += [home / "Documents" / "Image-Line" / "FL Studio" / "Presets" / "Plugin database"]
        roots["native"] += [Path("/Applications/Native Instruments"), home / "Documents" / "Native Instruments"]
        roots["downloads"] += [home / "Downloads"]
        roots["documents"] += [home / "Documents"]
    else:
        roots["plugins"] += [home / ".vst3", home / ".vst", Path("/usr/lib/vst3"), Path("/usr/lib/vst")]
        roots["native"] += [home / "Documents" / "Native Instruments"]
        roots["downloads"] += [home / "Downloads"]
        roots["documents"] += [home / "Documents"]
    return {purpose: [p for p in paths if p.exists()] for purpose, paths in roots.items()}


def scan_plugin_folder(folder, max_depth=4):
    """Plugin entries under `folder`. Plain folders (vendor / category folders) are searched up to `max_depth` deep;
    the first folder below the root is used as the vendor when the name is not a known plugin."""
    found = []

    def walk(directory, depth, vendor_hint):
        try:
            entries = sorted(Path(directory).iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            item = plugin_item(entry, folder, vendor_hint=vendor_hint)
            if item:
                found.append(item)
            elif entry.is_dir() and entry.suffix.lower() not in PLUGIN_SUFFIXES and depth < max_depth:
                walk(entry, depth + 1, vendor_hint or entry.name)

    walk(folder, 1, None)
    return found


def plugin_item(entry, root, vendor_hint=None):
    suffix = entry.suffix.lower()
    if suffix not in PLUGIN_SUFFIXES or PLUGIN_SUFFIXES[suffix] is None:
        return None
    if suffix == ".dll" and any(word in entry.stem.lower() for word in SKIP_DLL_WORDS):
        return None
    vendor, role = classify(entry.stem)
    return {"name": entry.stem, "format": PLUGIN_SUFFIXES[suffix], "folder": str(root),
            "vendor": vendor or vendor_hint or "?", "role": role or ""}


def scan_fl_database(folder):
    """Names of the plugins FL Studio has scanned (its .fst files under 'Plugin database')."""
    seen = {}
    for path in Path(folder).rglob("*.fst"):
        seen.setdefault(path.stem, str(path.parent.relative_to(folder)))
    items = []
    for name, where in sorted(seen.items(), key=lambda kv: kv[0].lower()):
        vendor, role = classify(name)
        items.append({"name": name, "format": "FL database", "folder": where, "vendor": vendor or "?", "role": role or ""})
    return items


def scan_native(folders):
    libraries, top = [], []
    for folder in folders:
        try:
            top += [p.name for p in sorted(Path(folder).iterdir(), key=lambda p: p.name.lower())][:80]
        except OSError:
            continue
        for path in Path(folder).rglob("*.nicnt"):
            libraries.append(path.stem)
    return {"libraries": sorted(set(libraries), key=str.lower), "top_level": top}


def count_audio(folder, depth=3, cap=5000):
    total = 0
    for root, dirs, files in os.walk(folder):
        if len(Path(root).relative_to(folder).parts) >= depth:
            dirs[:] = []
        total += sum(1 for f in files if Path(f).suffix.lower() in AUDIO_SUFFIXES)
        if total >= cap:
            return cap
    return total


def scan_downloads(folder):
    installers, archives, packs, other = [], [], [], 0
    for entry in sorted(Path(folder).iterdir(), key=lambda p: p.name.lower()):
        suffix = entry.suffix.lower()
        if entry.is_file() and suffix in INSTALLER_SUFFIXES:
            installers.append(entry.name)
        elif entry.is_file() and suffix in ARCHIVE_SUFFIXES:
            archives.append(entry.name)
        elif entry.is_dir():
            n = count_audio(entry)
            if n:
                packs.append({"folder": entry.name, "audio_files": n})
            else:
                other += 1
        else:
            other += 1
    return {"installers": installers, "archives": archives, "sample_folders": packs, "other_entries": other}


def scan_documents(folder):
    return [p.name for p in sorted(Path(folder).iterdir(), key=lambda p: p.name.lower()) if p.is_dir()]


def scan(roots):
    plugins, seen = [], set()
    for folder in roots.get("plugins", []):
        for item in scan_plugin_folder(folder):
            key = (item["name"].lower(), item["format"])
            if key not in seen:
                seen.add(key)
                plugins.append(item)
    database = []
    for folder in roots.get("fl_database", []):
        database += scan_fl_database(folder)
    return {
        "roots": {k: [str(p) for p in v] for k, v in roots.items()},
        "plugins": plugins,
        "fl_database": database,
        "native": scan_native(roots.get("native", [])),
        "downloads": [scan_downloads(p) | {"path": str(p)} for p in roots.get("downloads", [])],
        "documents": [{"path": str(p), "folders": scan_documents(p)} for p in roots.get("documents", [])],
    }


def suite_roles(name):
    lowered = name.lower()
    for needle, roles in SUITES.items():
        if _needle_matches(needle, lowered) and "imager" not in lowered and "doubler" not in lowered:
            return roles
    return []


def role_coverage(result):
    """Which VOCAL_ROLES are covered by an owned plugin (plugin folders + FL database), and by what.
    A name ending in '*' covers the role only through a suite's edition-dependent module."""
    direct, via_suite = {}, {}
    for item in result["plugins"] + result["fl_database"]:
        if item["role"]:
            direct.setdefault(item["name"], item["role"])
        for role in suite_roles(item["name"]):
            via_suite.setdefault(item["name"], []).append(role)
    coverage = {}
    for role, words in VOCAL_ROLES.items():
        names = {name for name, r in direct.items() if any(w.lower() in r.lower() for w in words)}
        starred = {name + "*" for name, roles in via_suite.items()
                   if name not in names and any(w.lower() in r.lower() for r in roles for w in words)}
        coverage[role] = sorted(names | starred, key=str.lower)
    return coverage


def redact(text, home):
    user = Path(home).name
    return text.replace(user, "<user>") if user else text


def render_markdown(result, coverage):
    lines = ["# Audio setup inventory", "", "Names and counts only. No file contents were read.", ""]
    lines += ["## Folders scanned"] + [f"- {purpose}: {', '.join(paths) or '(none found)'}"
                                        for purpose, paths in result["roots"].items()] + [""]

    lines += ["## Vocal-chain roles you can already fill",
              "(`*` = provided by a suite you own, if your edition includes that module)"]
    for role, names in coverage.items():
        lines.append(f"- **{role}**: " + (", ".join(names[:12]) + (" ..." if len(names) > 12 else "") if names else "**GAP**"))
    lines.append("")

    by_vendor = defaultdict(list)
    for item in result["plugins"]:
        by_vendor[item["vendor"]].append(item)
    lines += [f"## Installed plugins ({len(result['plugins'])} found in plugin folders)"]
    for vendor in sorted(by_vendor, key=str.lower):
        entries = ", ".join(f"{i['name']} [{i['format']}]" for i in by_vendor[vendor])
        lines.append(f"- **{vendor}**: {entries}")
    lines.append("")

    lines += [f"## FL Studio plugin database ({len(result['fl_database'])} plugins FL has scanned)"]
    lines.append(", ".join(i["name"] for i in result["fl_database"]) or "(not found)")
    lines.append("")

    native = result["native"]
    lines += [f"## Native Instruments ({len(native['libraries'])} Kontakt/NI libraries via .nicnt files)"]
    lines.append(", ".join(native["libraries"]) or "(none found; use --extra for your library drive)")
    lines.append("")

    for dl in result["downloads"]:
        lines += [f"## Downloads ({dl['path']})",
                  f"- installers ({len(dl['installers'])}): " + (", ".join(dl["installers"][:40]) or "-"),
                  f"- archives ({len(dl['archives'])}): " + (", ".join(dl["archives"][:40]) or "-"),
                  f"- sample-pack folders ({len(dl['sample_folders'])}): "
                  + (", ".join(f"{p['folder']} ({p['audio_files']} audio files)" for p in dl["sample_folders"][:40]) or "-"), ""]
    for doc in result["documents"]:
        lines += [f"## Documents folders ({doc['path']})", ", ".join(doc["folders"][:80]) or "-", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default="audio_inventory.md")
    parser.add_argument("--json", default="audio_inventory.json")
    parser.add_argument("--extra", action="append", default=[], help="extra folder to scan for plugins (repeatable)")
    parser.add_argument("--library-root", action="append", default=[], help="folder holding Kontakt libraries (repeatable)")
    parser.add_argument("--redact-user", action="store_true", help="replace your user name in paths with <user>")
    parser.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    roots = default_roots(platform.system(), os.environ, args.home)
    roots["plugins"] = roots.get("plugins", []) + [Path(p) for p in args.extra if Path(p).exists()]
    roots["native"] = roots.get("native", []) + [Path(p) for p in args.library_root if Path(p).exists()]
    for missing in [p for p in args.extra + args.library_root if not Path(p).exists()]:
        print(f"note: {missing} does not exist, skipped", file=sys.stderr)

    result = scan(roots)
    coverage = role_coverage(result)
    markdown = render_markdown(result, coverage)
    payload = json.dumps({**result, "role_coverage": coverage}, indent=2)
    if args.redact_user:
        markdown, payload = redact(markdown, args.home), redact(payload, args.home)
    Path(args.out).write_text(markdown, encoding="utf-8")
    Path(args.json).write_text(payload, encoding="utf-8")
    print(f"Found {len(result['plugins'])} plugins, {len(result['fl_database'])} in FL's database, "
          f"{len(result['native']['libraries'])} NI libraries.")
    print(f"Wrote {args.out} and {args.json}. Open the .md, check nothing private is in it, then share it.")
    gaps = [role for role, names in coverage.items() if not names]
    print("Vocal-chain gaps: " + (", ".join(gaps) if gaps else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
