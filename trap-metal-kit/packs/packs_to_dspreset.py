#!/usr/bin/env python3
"""Build a DecentSampler preset (.dspreset) where a dropdown menu -- or a keyswitch -- swaps which
sample pack the same keys play.

    python3 packs_to_dspreset.py packs/ dj_keys.dspreset --first-key 36 --crush --fold

DecentSampler is a free sampler plugin (decentsamples.com). Keep the .dspreset next to the packs
folder: sample paths in the file are relative to it. After loading, run DecentSampler's built-in
"Validate preset file" tool if anything looks wrong.

Format details (menu/option bindings with fixed_value, <midi><note> keyswitches, <keyboard><color>,
group `enabled`, loopEnabled, and the bit_crusher / wave_folder effects) follow the DecentSampler
developer guide.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import packlib

SAMPLE_KEY_COLOR = "FF2C365E"
SWITCH_KEY_COLOR = "FFE8DA9B"


def _enable_bindings(active_index, group_count):
    """One ENABLED binding per group: true for `active_index`, false for the rest."""
    return [
        ET.Element("binding", {
            "type": "general", "level": "group", "position": str(i), "parameter": "ENABLED",
            "translation": "fixed_value", "translationValue": "true" if i == active_index else "false",
        })
        for i in range(group_count)
    ]


def _knob(parent, x, label, minimum, maximum, value, binding_attrs_list):
    knob = ET.SubElement(parent, "labeled-knob", {
        "x": str(x), "y": "60", "width": "90", "textSize": "16", "textColor": "FFFFFFFF",
        "trackForegroundColor": "CCFFFFFF", "trackBackgroundColor": "66999999",
        "label": label, "valueType": "float",
        "minValue": str(minimum), "maxValue": str(maximum), "value": str(value),
    })
    for attrs in binding_attrs_list:
        ET.SubElement(knob, "binding", {**attrs, "translation": "linear",
                                        "translationOutputMin": str(minimum), "translationOutputMax": str(maximum)})


def build_dspreset(root, out_path, first_key=36, white_keys_only=False, mode="loop",
                   switch_first_key=None, release=0.05, crush=False, fold=False):
    packs = packlib.list_packs(root)
    slots = max(len(packlib.list_samples(p)) for p in packs)
    keys = packlib.playable_keys(first_key, slots, white_keys_only)
    switches = packlib.switch_keys(switch_first_key, first_key, keys, len(packs))
    out_dir = Path(out_path).resolve().parent

    top = ET.Element("DecentSampler", {"minVersion": "1.7.2"})

    ui = ET.SubElement(top, "ui", {"width": "812", "height": "375"})
    tab = ET.SubElement(ui, "tab", {"name": "main"})
    menu = ET.SubElement(tab, "menu", {"x": "10", "y": "10", "width": "260", "height": "30", "value": "1"})
    for index, pack in enumerate(packs):
        option = ET.SubElement(menu, "option", {"name": pack.name})
        option.extend(_enable_bindings(index, len(packs)))

    knob_x = 10
    if crush:
        _knob(tab, knob_x, "Bits", 4, 24, 24, [{"type": "effect", "level": "instrument", "effectIndex": "0",
                                                  "parameter": "FX_BIT_DEPTH"}])
        _knob(tab, knob_x + 100, "Rate Div", 1, 32, 1, [{"type": "effect", "level": "instrument", "effectIndex": "0",
                                                          "parameter": "FX_SAMPLE_RATE_REDUCTION"}])
        knob_x += 200
    if fold:
        _knob(tab, knob_x, "Fold", 1, 40, 1, [
            {"type": "effect", "level": "group", "groupIndex": str(i), "effectIndex": "0", "parameter": "FX_DRIVE"}
            for i in range(len(packs))])

    keyboard = ET.SubElement(ui, "keyboard")
    ET.SubElement(keyboard, "color", {"loNote": str(switches[0]), "hiNote": str(switches[-1]), "color": SWITCH_KEY_COLOR})
    ET.SubElement(keyboard, "color", {"loNote": str(keys[0]), "hiNote": str(keys[-1]), "color": SAMPLE_KEY_COLOR})

    groups = ET.SubElement(top, "groups", {"attack": "0.001", "decay": "25", "sustain": "1.0", "release": str(release)})
    for index, pack in enumerate(packs):
        group_attrs = {"name": pack.name, "enabled": "true" if index == 0 else "false"}
        if mode == "oneshot":
            group_attrs["ampEnvEnabled"] = "false"
        group = ET.SubElement(groups, "group", group_attrs)
        for key, sample in zip(keys, packlib.list_samples(pack)):
            attrs = {"path": packlib.relative_posix(sample, out_dir), "rootNote": str(key),
                     "loNote": str(key), "hiNote": str(key)}
            if mode == "loop":
                attrs["loopEnabled"] = "true"  # loopStart/loopEnd default to the whole file
            ET.SubElement(group, "sample", attrs)
        if fold:
            effects = ET.SubElement(group, "effects")
            ET.SubElement(effects, "effect", {"type": "wave_folder", "drive": "1", "threshold": "1"})

    if crush:
        effects = ET.SubElement(top, "effects")
        ET.SubElement(effects, "effect", {"type": "bit_crusher", "bitDepth": "24", "sampleRateReduction": "1", "mix": "1.0"})

    midi = ET.SubElement(top, "midi")
    for index, switch_key in enumerate(switches):
        note = ET.SubElement(midi, "note", {"note": str(switch_key)})
        note.extend(_enable_bindings(index, len(packs)))

    ET.indent(top)
    Path(out_path).write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(top, encoding="unicode") + "\n",
                              encoding="utf-8")
    return {"packs": [p.name for p in packs], "keys": keys, "switches": switches}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("packs_dir", help="folder whose sub-folders are the packs")
    parser.add_argument("output", help="the .dspreset file to write (keep it next to the packs folder)")
    parser.add_argument("--first-key", type=int, default=36, help="MIDI note of the first sample (default 36)")
    parser.add_argument("--switch-first-key", type=int, default=None,
                        help="MIDI note of the first pack keyswitch (default: just below --first-key)")
    parser.add_argument("--white-keys-only", action="store_true", help="skip black keys for samples")
    parser.add_argument("--mode", choices=["loop", "hold", "oneshot"], default="loop",
                        help="loop = repeat while held (default), hold = play once and stop on release, "
                             "oneshot = always play to the end")
    parser.add_argument("--release", type=float, default=0.05, help="release time in seconds (default 0.05)")
    parser.add_argument("--crush", action="store_true", help="add Bits / Rate Div knobs (bit crusher effect)")
    parser.add_argument("--fold", action="store_true", help="add a per-voice Fold knob (wave folder effect)")
    args = parser.parse_args(argv)

    try:
        info = build_dspreset(args.packs_dir, args.output, args.first_key, args.white_keys_only, args.mode,
                              args.switch_first_key, args.release, args.crush, args.fold)
    except (ValueError, FileNotFoundError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}: {len(info['packs'])} packs, keys {info['keys'][0]}..{info['keys'][-1]}")
    for key, name in zip(info["switches"], info["packs"]):
        print(f"  keyswitch {key:3d} -> {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
