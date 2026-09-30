# Trap Metal Kit

Scripts, generators and notes for building a key-mapped, DJ-style sampling rig and a vocal chain for dark trap metal,
emo trap, hyperpop, rage-pop and rage metal, plus an automated vocal setup / mix-check / master-check workflow built
around FL Studio, Nectar 4, Ozone 12 and the Unison plugins. Most scripts are plain text with no dependencies (the
mastering tool needs numpy, scipy, soundfile and pyloudnorm), and the SFZ and DecentSampler routes run in free players,
so the key-mapped DJ rig doesn't need paid software.

## What's in it

| Path | What it does | Works in |
|---|---|---|
| `kontakt/map_folder_to_keys.lua` | Maps every audio file in a folder to its own key (loops, optional tempo sync from `..._140_BPM.wav` names) | Kontakt 8 (Lua API) |
| `packs/packs_to_sfz.py` | **Multiple packs on the same keys**, chosen by keyswitch | sfizz, Sforzando, other SFZ players |
| `packs/packs_to_dspreset.py` | Same, with a **dropdown menu** + keyswitches; optional Bits/Rate/Fold knobs | DecentSampler (free) |
| `fl-studio/device_TrapDJ.py` | Keys launch Performance Mode clips (decks), stop keys, mod-wheel crossfader | FL Studio (Python MIDI scripting) |
| `fl-studio/device_VocalSetup.py` | One key builds the vocal mixer (names, colours, Vox Bus routing, reverb/delay sends, arms the lead); another key **audits** that Nectar 4 / Ozone 12 / a distortion are on the right inserts | FL Studio |
| `fl-studio/device_PluginProbe.py` | **Read-only**: lists every plugin in your mixer slots and the parameters FL can automate | FL Studio |
| `fl-studio/device_PinkTheme.py` | Paints channel rows, mixer inserts, playlist tracks and patterns in a pink-dominant pink / purple / red / black cycle | FL Studio |
| `tools/master_batch.py` | `prep` raw vocal takes, `measure` an exported master (LUFS, true peak; `--strict` gates scripts), `master` to a loudness target, optional Matchering reference | any WAV/FLAC/AIFF |
| `tools/scan_audio_setup.py` | Inventories your plugins, FL's plugin database, Kontakt libraries and Downloads (names only) and reports vocal-chain roles you can already fill and gaps | run on your own PC |
| `reaper/key_slots.lua` | One ReaSamplOmatic5000 per key from a folder | REAPER (ReaScript) |
| `reaper/jsfx/trapmetal_crunch.jsfx` | Drive / fold / crush distortion that keeps the lows clean (24 dB/oct crossover) | REAPER (JSFX) |
| `reaper/jsfx/trapmetal_vocal_grit.jsfx` | Parallel vocal grit + Haas width | REAPER (JSFX) |
| `tools/gen_808.py` | Distorted 808 one-shots at any MIDI notes | any sampler |
| `tools/gen_wavetables.py` | `rage_fold`, `vowel_morph`, `crushed_lead` wavetables (2048 samples/frame) | Vital, Serum, other wavetable synths |
| `mcp/probe_mcp.py` | Asks a local MCP server (Kontakt 8.13+ on port 3006) what it speaks and prints the `claude mcp add` command | any MCP-over-HTTP server |
| `docs/` | `01` Kontakt MCP · `02` DJ instruments · `03` vocals + artist notes · `04` scriptable plugins · `05` DAW MCP servers · `06` pink theme · `07` **automated vocal/mix/master pipeline (start here for Nectar 4 + Ozone 12)** | — |

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

# 4. Vocals: inventory your plugins, prep raw takes, check an exported master
python3 tools/scan_audio_setup.py --redact-user
python3 tools/master_batch.py prep takes/ -o prepped/
python3 tools/master_batch.py measure exports/ --lufs -9 --ceiling -1 --strict
```
In FL Studio, assign the `fl-studio/device_*.py` scripts to MIDI inputs (see each file's header). With
`device_VocalSetup.py` assigned, note 126 builds the vocal mixer and note 125 audits the chain; with
`device_PluginProbe.py`, note 124 prints every plugin and parameter. Full walk-through: `docs/07`.
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
| FL Studio scripts (DJ, PinkTheme, VocalSetup, PluginProbe) | Run against stubs of the FL modules: note→clip mapping, colour order and cycle, routing/sends/arming, the chain audit, and that the probe never writes. Mutation-checked. |
| REAPER `key_slots.lua` | Run against a mock of the ReaScript API |
| JSFX plugins | Their algorithms re-implemented in Python (`tests/jsfx_model.py`): crossover sums flat, sub survives, DC removed, delay length exact. **The JSFX syntax itself has not been run.** |
| SFZ / DecentSampler generators | Real WAV files in, output files parsed and checked structurally. **Not loaded in a player**; DecentSampler has a built-in *Validate preset file* tool, use it |
| 808 / wavetable generators | Real WAVs measured: pitch, length, peak, DC, morphing, quantisation levels |
| `master_batch.py` | Synthetic stereo mixes measured with an independent pyloudnorm meter: lands on the LUFS target, true peak under the ceiling, limiter never exceeds it, silence handled, `measure` changes nothing |
| `scan_audio_setup.py` | A fake Windows-style tree: plugin/vendor/role classification, FL database, `.nicnt` libraries, Downloads buckets, `--redact-user`, and that file **contents are never read** |
| Nectar 4 / Ozone 12 / Unison / iZotope facts | From the vendors' own pages (iZotope's Nectar 4 and Ozone 12 Master Assistant articles, unison.audio) — **not** tested inside those plugins; edition-dependent modules are marked |
| MCP probe | Against a real local HTTP server speaking JSON and event-stream MCP; **not against Kontakt** |

Lines marked BEST EFFORT in the Kontakt script (loop indexing, Time Machine sync) rely on details the reference manual
doesn't spell out. Expect to adjust them after a first run.

## Running the tests
```bash
pip install lupa                                   # Lua tests
pip install numpy scipy soundfile pyloudnorm       # mastering tool tests (skipped if missing)
python3 -m unittest discover -s tests
```
Python 3.9+ (developed on 3.11). The generators, pack builders, scanner and FL/REAPER scripts use only the standard
library.
