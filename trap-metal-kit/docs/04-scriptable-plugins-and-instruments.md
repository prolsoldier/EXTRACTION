# Scriptable plugins & instruments for dark trap metal, emo trap, hyperpop, rage-pop and rage metal

You asked for "v2 or v3" tools. I read that as the current second/third-generation releases (Serum 2, Omnisphere 3,
Kontakt 8, Serato Sample 2, ShaperBox 3, Decimort 2) plus anything scriptable. If you meant something else, say so.

**Legend** — ✅ checked against the vendor's docs or release notes this session · 📰 taken from a review/blog article
(source named; some are vendor or affiliate sites) · ❓ lead I did not verify.

> **You already own** the Unison plugins (MIDI Wizard, Chord Genie, Drum Monkey, Bass Dragon, 808 Machine, Unisynth,
> Sound Doctor, Mangler), Nectar 4 and Ozone 12 — so section B below leaves out overlapping recommendations. See
> `docs/07-vocal-automation-and-plugins.md` for how they fit the automated pipeline and what gaps remain.

## A. Things you can actually script

| Tool | How it's scripted | What's in this kit | Status |
|---|---|---|---|
| **Kontakt 8** | Kontakt Lua API: build instruments, groups, zones, loops from code (`Run Lua script…`, F11). Kontakt 8.13.0 added an MCP server for debugging scripts. | `kontakt/map_folder_to_keys.lua` | ✅ API names from NI's reference manual; MCP server confirmed in the 8.13.0 release notes ([Toolfarm](https://www.toolfarm.com/news/kontakt-8-13/), [Rekkerd](https://rekkerd.org/native-instruments-updates-kontakt-to-v8-13-0/)) |
| **DecentSampler** (free) | Plain-text `.dspreset` XML: menus, keyswitches, effects (wave folder, wave shaper, bit crusher, stutter, pitch shifter, stereo simulator, compressor) | `packs/packs_to_dspreset.py` | ✅ [developer guide](https://decentsampler-developers-guide.readthedocs.io/) |
| **sfizz / Sforzando** (SFZ players) | Plain-text `.sfz`: keyswitches (`sw_last`, `sw_default`), loop modes | `packs/packs_to_sfz.py` | ✅ opcodes from [sfzformat.com](https://sfzformat.com/) |
| **REAPER** | JSFX (EEL2 effects that live as text files) and ReaScript (Lua/Python/EEL2) | `reaper/jsfx/trapmetal_crunch.jsfx`, `reaper/jsfx/trapmetal_vocal_grit.jsfx`, `reaper/key_slots.lua` | JSFX/ReaScript run inside REAPER; not run there by me (see README) |
| **FL Studio** | Python MIDI-controller scripts (`playlist.triggerLiveClip`, Performance Mode) | `fl-studio/device_TrapDJ.py` | ✅ API from the [FL manual](https://www.image-line.com/fl-studio-learning/fl-studio-beta-online-manual/html/midi_scripting.htm) and [API stubs](https://il-group.github.io/FL-Studio-API-Stubs/) |
| **Vital** (free) / **Serum 2** / other wavetable synths | Import `.wav` wavetables (2048 samples per frame) that you generate | `tools/gen_wavetables.py` (rage fold, vowel morph, crushed lead) | Serum/Vital import of generated files not tested by me |
| **Any sampler** | Generate the samples themselves | `tools/gen_808.py` (distorted 808 one-shots) | ✅ tested (pitch, decay, drive) |
| Surge XT | Lua wavetable scripting | — | ❓ I recall it exists; not checked |
| FL Studio VFX Script | Python inside an FL plugin | — | ❓ appeared in one video title; not checked |
| Reaper / FL / Ableton **MCP servers** | Community servers that let Claude drive the DAW | see `docs/05-more-mcp-servers.md` | ❓ search-result excerpts only; not audited |

## B. Genre tools people recommend (not scriptable unless noted)

Sources: 📰 [Internet Tattoo — hyperpop/rage plugins](https://www.internettattoo.com/blog/best-synth-plugins-vst-to-make-hyperpop-rage-trap)
(contains affiliate links), 📰 [Godlike Loops — 15 best VSTs 2026](https://godlikeloops.com/blog/best-vst-plugins-for-hip-hop-and-trap-2026/)
(a plugin vendor — it markets its own products), 📰 [AirGigs vocal plugins](https://blog.airgigs.com/2026/06/7-best-plugins-for-vocal-production-in-2026/).

**Synths (rage / hyperpop leads, dark pads)**
- **Serum 2** — recommended by both articles for rage, trap and hyperpop; wavetable, multisample, granular and spectral oscillators. 📰
- **Vital** — free wavetable synth; both articles recommend it for rage leads. 📰 Pairs with `tools/gen_wavetables.py`.
- **miniBit** (AudioThing) — chiptune-style synth; pitched as the "8-bit" sound behind rage/hyperpop leads. 📰
- **Omnisphere 3** — big preset library, suited to dark trap. 📰

**808s / low end**
- **SubLab XL** — deep 808 design (sampler + synth + sub engines). 📰
- `tools/gen_808.py` + `reaper/jsfx/trapmetal_crunch.jsfx` ("Keep Lows Clean") — crush an 808's harmonics without losing the sub.

**Distortion / character / movement**
- **OTT** (Xfer, free) — the "over the top" multiband compression behind the hyperpop/rage sheen. 📰
- **ShaperBox 3** — gating, sidechain shapes, movement for rage loops. 📰
- **RC-20 Retro Color**, **Decimort 2** — lo-fi / sampler-grit; the article files them under boom-bap/old-school (my take: the bit-reduction also suits emo trap). 📰
- **Decapitator** — widely used saturation for vocals. 📰
- **Vybz** (Thenatan) — multi-effect whose presets the reviewer calls darker and weirder. 📰
- Built into DecentSampler: wave folder, wave shaper, bit crusher, stutter (see the generator's `--crush` / `--fold`). ✅

**Vocals**
- **Auto-Tune** (used as an instrument in hyperpop/rage), **Soundtoys Little AlterBoy** (tuning + formant/pitch effects), **United Plugins TrapTune** (free). 📰
- Godlike **Submerge** (free vocal formant effect) and **Bend** (pitch/formant curves). 📰 vendor claims.
- `reaper/jsfx/trapmetal_vocal_grit.jsfx` — parallel grit + Haas width, the scriptable stand-in.

**Sample-chop / loop-DJ instruments** (details in `docs/02-key-mapped-dj-instruments.md`)
- **Kontakt Leap**, **Serato Sample 2**, **Output Arcade**, **Godlike Chop**, DecentSampler and SFZ via `packs/`.

## C. Which combination fits which sound (my suggestions, not measurements)

| Sound | Start with |
|---|---|
| **Rage / rage-pop** | Vital or Serum 2 lead → `gen_wavetables.py --preset rage_fold` → OTT → ShaperBox for movement; 808 through `trapmetal_crunch` with Keep Lows ≈ 100–150 Hz |
| **Hyperpop** | `crushed_lead` wavetable, Auto-Tune/AlterBoy on the vocal, OTT on the bus, `trapmetal_vocal_grit` with Width 8–15 ms |
| **Dark trap metal / rage metal** | Distorted guitar loops in a pack, `gen_808.py --drive 24`, `trapmetal_crunch` with Fold + Asymmetry up, vocals through the grit chain in `docs/03` |
| **Emo trap** | `gen_808.py` with lower drive, `crushed_lead`/`vowel_morph` for melody, Decimort/RC-20 style crush, lighter vocal grit |

Whatever you sample: check the licence. Royalty-free loop packs are made to be played like this; ripping commercial
tracks is a different matter and needs clearance.
