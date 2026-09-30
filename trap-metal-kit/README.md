# Trap Metal Kit

Scripts, generators and notes for building a key-mapped, DJ-style sampling rig and a vocal chain for dark trap metal,
emo trap, hyperpop, rage-pop and rage metal. The scripts and generators are plain text and dependency-free, and the
SFZ and DecentSampler routes run in free players, so the key-mapped DJ rig doesn't need paid software. (Kontakt, FL
Studio and REAPER scripts are here for if you already use them.)

## What's in it

| Path | What it does | Works in |
|---|---|---|
| `kontakt/map_folder_to_keys.lua` | Maps every audio file in a folder to its own key (loops, optional tempo sync from `..._140_BPM.wav` names) | Kontakt 8 (Lua API) |
| `packs/packs_to_sfz.py` | **Multiple packs on the same keys**, chosen by keyswitch | sfizz, Sforzando, other SFZ players |
| `packs/packs_to_dspreset.py` | Same, with a **dropdown menu** + keyswitches; optional Bits/Rate/Fold knobs | DecentSampler (free) |
| `fl-studio/device_TrapDJ.py` | Keys launch Performance Mode clips (decks), stop keys, mod-wheel crossfader | FL Studio (Python MIDI scripting) |
| `reaper/key_slots.lua` | One ReaSamplOmatic5000 per key from a folder | REAPER (ReaScript) |
| `reaper/jsfx/trapmetal_crunch.jsfx` | Drive / fold / crush distortion that keeps the lows clean (24 dB/oct crossover) | REAPER (JSFX) |
| `reaper/jsfx/trapmetal_vocal_grit.jsfx` | Parallel vocal grit + Haas width | REAPER (JSFX) |
| `tools/gen_808.py` | Distorted 808 one-shots at any MIDI notes | any sampler |
| `tools/gen_wavetables.py` | `rage_fold`, `vowel_morph`, `crushed_lead` wavetables (2048 samples/frame) | Vital, Serum, other wavetable synths |
| `mcp/probe_mcp.py` | Asks a local MCP server (Kontakt 8.13+ on port 3006) what it speaks and prints the `claude mcp add` command | any MCP-over-HTTP server |
| `docs/` | Kontakt MCP guide, DJ-instrument comparison, vocal setup + artist notes, scriptable-plugin list, DAW MCP servers | — |

## Quick start
```bash
# 1. Make some 808s in two flavours and turn them into a two-pack instrument
python3 tools/gen_808.py --note 24 28 31 33 --drive 3  -d packs_demo/packs/808s_clean
python3 tools/gen_808.py --note 24 28 31 33 --drive 24 -d packs_demo/packs/808s_rage --pitch-drop 12
python3 packs/packs_to_sfz.py       packs_demo/packs packs_demo/dj_keys.sfz      --first-key 36
python3 packs/packs_to_dspreset.py  packs_demo/packs packs_demo/dj_keys.dspreset --first-key 36 --crush --fold

# 2. Wavetables for Vital/Serum
python3 tools/gen_wavetables.py --preset all -d wavetables/

# 3. Check what Kontakt's MCP server exposes (run on the machine running Kontakt)
python3 mcp/probe_mcp.py
```
Load `dj_keys.sfz` in sfizz/Sforzando (keyswitches 34/35 pick the pack) or `dj_keys.dspreset` in DecentSampler (menu or
keyswitch). For Kontakt, see the header of `kontakt/map_folder_to_keys.lua`; for FL Studio, the header of
`fl-studio/device_TrapDJ.py`.

## Corrections to the notes this came from
- The **Kontakt 8.13 MCP server** is an AI *debugging* interface for instrument builders, not a host for sound generators.
  Its URL path and tool list aren't published, so use `mcp/probe_mcp.py` instead of guessing. → `docs/01-kontakt-mcp.md`
- **Komplete Script (`.kscript`) is a GUI language, not Lua.** The Lua you run with F11 is the *Kontakt Lua API*.
- Claude Code must run on the same computer as Kontakt to reach `localhost:3006`.

## What has and hasn't been tested
There is no Kontakt, FL Studio, REAPER, sfizz or DecentSampler in the environment this was written in, so **nothing has
been loaded into a real host**. What was tested:

| Piece | How |
|---|---|
| Kontakt Lua script | Run against a mock of the Kontakt Lua API (sorting, key assignment, overrides, error handling) |
| FL Studio script | Run against stubs of the FL modules (note→clip mapping, stop keys, crossfade maths) |
| REAPER `key_slots.lua` | Run against a mock of the ReaScript API |
| JSFX plugins | Their algorithms re-implemented in Python (`tests/jsfx_model.py`): crossover sums flat, sub survives, DC removed, delay length exact. **The JSFX syntax itself has not been run.** |
| SFZ / DecentSampler generators | Real WAV files in, output files parsed and checked structurally. **Not loaded in a player**; DecentSampler has a built-in *Validate preset file* tool, use it |
| 808 / wavetable generators | Real WAVs measured: pitch, length, peak, DC, morphing, quantisation levels |
| MCP probe | Against a real local HTTP server speaking JSON and event-stream MCP; **not against Kontakt** |

Lines marked BEST EFFORT in the Kontakt script (loop indexing, Time Machine sync) rely on details the reference manual
doesn't spell out. Expect to adjust them after a first run.

## Running the tests
```bash
pip install lupa        # only needed for the Lua tests
python3 -m unittest discover -s tests
```
Python 3.9+ (developed on 3.11). Everything else is standard library.
