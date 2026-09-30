# Instruments that put a different sample on each key so you can DJ

The idea: every key holds a different loop, stem or song section; you hold or tap keys to bring pieces in and out,
quantised to the bar so everything stays on the grid. "Separate packs you can switch around" = the same keys play a
different set of samples depending on a keyswitch or menu.

**Legend** — ✅ verified against the vendor's page this session · 🗣 vendor's own marketing claim · ❓ from your notes / general knowledge, not re-checked.

| Instrument | Per-key samples? | Pack switching? | Tempo sync | Scriptable | Status |
|---|---|---|---|---|---|
| **Kontakt 8 — Leap** | 16 slots on the white keys C3–D5; drag files onto keys; black keys are effects | Load another Leap preset / kit | Warps to project tempo; *Quantize: Bar* starts loops on the next bar; *Tonality* transposes loops into one key; *Trigger style: Hold* plays while the key is held | Not Leap itself | ✅ [NI blog](https://blog.native-instruments.com/leap-kit-with-kontakt/) |
| **Kontakt 8 — custom instrument** | Any number of keys, one zone each | Save one `.nki` per pack | Time Machine Pro with the file's BPM (best effort) | Yes: `kontakt/map_folder_to_keys.lua` (Lua API) | ✅ API names; script tested against a mock only |
| **DecentSampler** (free) | One `<sample>` per key | Dropdown menu **and** keyswitch notes toggle groups | Not tempo-synced by default | Yes: `packs/packs_to_dspreset.py` | ✅ format docs; preset not loaded in the plugin by me |
| **sfizz / Sforzando** (SFZ) | One `<region>` per key | Keyswitches: `sw_last` / `sw_default` | Not tempo-synced | Yes: `packs/packs_to_sfz.py` | ✅ opcodes; not loaded in a player by me |
| **FL Studio Performance Mode** | Each key launches a playlist clip; tracks act as decks | Rows of keys = decks; stop keys per deck | Per-track trigger sync (off, 1/4 beat … 4 beats, auto) quantises when clips start; tempo-matching the audio is up to you | Yes: `fl-studio/device_TrapDJ.py` (also a mod-wheel crossfader) | ✅ API; script tested against stubs only |
| **Serato Sample 2** | Chop a track and map chops across keys; can map one chop chromatically | Load another sample | Pitch shift + time stretch, sync, stem separation | Not scriptable | ✅ [Serato](https://serato.com/sample) |
| **Output Arcade** | Samples/loops on keys | ❓ not checked | "Sync" time/pitch shifting is on by default whenever a sample is loaded onto a key | ❓ not checked | ✅ sync behaviour only: [Output help](https://support.output.com/en/articles/10297643-advanced-panel) |
| **Godlike Chop** | Separates six stems offline, slices, plays across 32 MIDI-mapped pads | Load another source | Detects key and BPM | Not scriptable | 🗣 [vendor page](https://godlikeloops.com/blog/best-vst-plugins-for-hip-hop-and-trap-2026/) |
| **REAPER + ReaSamplOmatic5000** | One sampler instance per key | One track per pack, mute/solo | RS5k does not time-stretch | Yes: `reaper/key_slots.lua` | ❓ tested against a mock only |
| **FL Studio Slicex** | Slices a file across keys | — | — | — | ❓ from your notes |

## Blending tips that work in all of them
- Put every loop in one key and one tempo (or let Leap / Serato / Arcade warp them). Mismatched BPMs are the #1 reason blends sound bad.
- Quantise triggers to a bar so entries land on the beat.
- Use *Hold* for "play while pressed" and *Latch* for "toggle on/off" deck behaviour where the tool offers it.
- Bring a new piece in with a high-pass on the outgoing one (or the crossfader in the FL script), and swap the drums last.
- Keep drums, bass and melody on separate keys/rows so you can swap one layer at a time.

## Key-number conventions differ
The scripts here use MIDI note numbers, because programs disagree on note names. Kontakt calls 60 **C3**, SFZ
(whose names run C-1…G9) calls it **C4**, and FL Studio calls it **C5**. So note `36` is C1 in Kontakt, C2 in SFZ and
C3 in FL Studio. Check your own program's convention before assuming where a key lands.
