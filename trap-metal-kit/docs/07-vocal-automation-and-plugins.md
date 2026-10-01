# Automated vocal setup → mix → master, built around what you own

You said you have (almost) every **Unison** plugin, plus **Nectar 4** and **Ozone 12**. This is the pipeline that uses
them, with the boring parts scripted. I can't see your PC, so what I know about your setup comes from what you told me
and from the vendors' own pages; `tools/scan_audio_setup.py` will show me the rest (see the end).

> **Using the one-file bundle** (`device_TrapMetalKit.py`, see [00-fl-studio-quickstart.md](00-fl-studio-quickstart.md))? The keys are **72** (probe), **73** (audit) and **74** (vocal setup, press twice) instead of 124 / 125 / 126 below, and the pink repaint is **75**. Everything else in this document is the same.

## What is automated, what is assisted, what is still you

| Step | Who does it | Tool |
|---|---|---|
| Colour every row pink / purple / red | **Script** | `fl-studio/device_PinkTheme.py` |
| Build the vocal mixer: names, colours, routing to a Vox Bus, reverb/delay sends, arm the lead | **Script** (one key press) | `fl-studio/device_VocalSetup.py`, note 126 |
| Check that Nectar / Ozone / a distortion are on the right inserts | **Script** (read-only) | same script, note 125 |
| List every parameter of Nectar / Ozone / Mangler that FL can automate | **Script** (read-only) | `fl-studio/device_PluginProbe.py`, note 124 |
| Pick the audio input, load plugins, press record | **You** — FL's scripting API can't do these | — |
| Vocal chain: levels, EQ, intensity, width, reverb, delay | **Nectar 4 Vocal Assistant** (assistant you steer) | Nectar 4 |
| Distortion / grit | **You**, with Unison Mangler | Mangler |
| Drums, 808s, chords | **Unison plugins** generate; you edit | Drum Monkey, Bass Dragon, 808 Machine, Unisynth, MIDI Wizard |
| Master: tone, dynamics, width, loudness | **Ozone 12 Master Assistant** (assistant you steer) | Ozone 12 |
| Trim, high-pass, gain-stage raw takes | **Script** | `tools/master_batch.py prep` |
| Check the exported master (loudness, true peak) | **Script** (changes nothing) | `tools/master_batch.py measure` |
| Batch-normalise or match-to-reference for other versions | **Script** | `master_batch.py master`, or `--reference` (Matchering) |

Nothing in FL's API can load a plugin into a slot, so "fully automatic" isn't possible inside FL. What you get is
the layout, colours, routing, arming, a chain check and the QA, with the plugins' own assistants doing the tone work.

## Step by step

### 0. Once
1. Copy `device_PinkTheme.py`, `device_VocalSetup.py`, `device_PluginProbe.py` into
   `Documents\Image-Line\FL Studio\Settings\Hardware\<folder>\` and, in Options ▸ MIDI Settings, assign each to a MIDI
   input (any port; see each file's header).
2. Load your vocal chain once and **save it as a mixer-track preset** (mixer track menu) so you never rebuild it.
3. Run `python tools/scan_audio_setup.py --redact-user` and send me `audio_inventory.md`.

### 1. Start a session
- Press **126** → VOX MAIN, VOX DBL L/R, ADLIBS, SCREAMS → VOX BUS, sends to REVERB and DELAY, lead armed.
- Load: **Nectar 4** on VOX MAIN, a distortion on SCREAMS/ADLIBS, **Ozone 12** on the Master.
- Press **125** → the script lists what is in each slot and what is missing.

### 2. Record
Pick the input on VOX MAIN's Input selector. Peak around −12 to −6 dBFS (`docs/03`). Record main, doubles, ad-libs and
harsh layers on separate inserts.

### 3. Vocals (Nectar 4)
From iZotope's own description of Nectar 4:
- **Vocal Assistant** (in every edition) — choose a target from your library, decide EQ, intensity and width, and blend
  reverb and delay. Start here, then refine by ear.
- **Auto-Level module** (Advanced only) sits first in the chain and evens out levels, so you need less manual volume
  automation. Its Tame Noise option distinguishes sung from unsung content.
- **Backer** generates synthetic background singers from your lead (eight styles; iZotope notes it was trained only on
  English-speaking voices) and **Voices** builds layered stacks — useful for ad-libs and hooks.
- **Audiolens**, the free-with-Nectar desktop app, captures the tonal profile of any vocal playing on your computer, so
  you can use a reference vocal as a *target* instead of guessing.
- Pitch correction comes from the bundled **Melodyne 5 essential**; **Unmask** and Follow EQ (Standard and up) carve room
  for the vocal in the beat.
- Which of these you have depends on your edition: Elements, Standard or Advanced.

Grit: put **Unison Mangler** (Mangle / Saturate / Punch / Width; Unison says it works on vocals) on SCREAMS and ADLIBS,
after Nectar so the assistant tunes and levels first. For harsher tones try Nectar's own Saturation (Advanced).

### 4. Beat (Unison)
Unison Link lets Bass Dragon follow your chords note-for-note, and Drum Monkey follows the genre you pick. 808 Machine
generates 808s in five styles with attack, tone, sidechain and glide. Put Mangler on a *send* that is high-passed
around 120 Hz so the 808's sub stays clean while its harmonics get crushed (Mangler's listed controls are Mangle,
Saturate, Punch and Width; none is a crossover).

### 5. Master (Ozone 12)
From iZotope's Master Assistant guide:
1. Open Ozone 12 on the Master, click the **Master Assistant** button (top of the plugin).
2. Choose **Custom**. Genre targets include **Trap, Hyperpop, Metal, Hip-Hop and Classic Hip-Hop**; you can also add
   your own reference file (the + in Targets), or a target made with Audiolens.
3. Set the loudness target and **Analysis Time** to the length of your loudest section (usually the chorus, in
   seconds or bars). Play it and run the assistant.
4. Macro sliders: Tonal Balance, Loudness, Dynamic Match, Width Match, Clarity, Stabilizer (an "unwanted resonance"
   control), Vocal Balance (ties to a lead-vocal Master Rebalance).
5. Use **Gain Match** while comparing, and **turn it off before you export**.
6. If Ozone's EQ has to fight hard to reach the target, that's iZotope's own warning that the mix has a problem;
   fix it in the mix, not the master.
Ozone 12 Elements is macro-only; the modules in the Assistant view depend on your edition.

### 6. Check the export (script)
```
python tools/master_batch.py measure exports/ --lufs -9 --ceiling -1 --strict
```
Prints integrated loudness (LUFS), true peak (dBTP) and sample peak for each file, warns if the true peak is over the
ceiling or the loudness is more than 1 LU from your target, and exits with 2 under `--strict` so a script can stop.
`-9 LUFS` and `-1 dBTP` are my starting points, not a standard; many streaming services normalise playback loudness,
so a very loud master may be turned down there. Don't run `master_batch.py master` on Ozone's output unless you mean
to limit twice. Use it on mixes that haven't been through Ozone.

### 7. Raw takes (script)
```
python tools/master_batch.py prep takes/ -o prepped/
```
Trims silence, 60 Hz high-pass, peaks at −6 dBFS. Handy before dropping takes into Nectar's Auto-Level.

## Gaps in what you own, and what fills them
Unison's eight plugins (MIDI Wizard, Chord Genie, Drum Monkey, Bass Dragon, 808 Machine, Unisynth, Sound Doctor,
Mangler) cover generation, drums, 808s, FX chains and distortion. They don't tune vocals, tame harsh resonances or meter
loudness. Nectar and Ozone cover most of that; what is left, and which purchases would matter:

| Gap | Options | Notes |
|---|---|---|
| Harsh screams / sibilance | **oeksound soothe2** (paid) | A dynamic resonance suppressor for harshness and sibilance; several 2026 roundups pair it with Pro-Q 4 |
| Hard tuning as an effect (hyperpop/rage) | **Auto-Tune** (paid), **Little AlterBoy**, FL's **Pitcher** (if your FL edition includes it) | Auto-Tune is described as an "instrument" in rage/hyperpop; Nectar's Pitch/Melodyne is more transparent |
| Distortion character | **iZotope Trash** (listed at $99), Decapitator | You already have Mangler and Nectar's Saturation; add only if you want other flavours |
| Loudness meter in FL | a free LUFS meter (Youlean's is a common one — not checked here) or `master_batch.py measure` | Ozone has its own metering |

## Gashum, and "sounds like"
What the sources say: Genius calls Gashum a "multi-faceted music artist known for his unique sound that features bass
heavy beats, with dark lyrics and vocals". His SoundCloud lists GUTTER (prod. DINCA), GOTH GIRLS (prod. KASUMI) and 0837
(feat. Depth Strida, prod. MUTRICK); an Instagram post dates the four-song EP IRREPAIRABLE DAMAGE to 7/8/22; Apple Music
lists "Gutter" (2022) and "Gas Chamber" (2024). A third-party post describes another artist as "dollbreaker met Gashum"
with "distorted production and aggressive delivery". That is all I found — **no published vocal chain.**

To get in that territory without guessing: capture a reference vocal with **Audiolens** and use it as a Nectar target;
pick Ozone's **Trap / Hyperpop / Metal** target as the Master Assistant starting point; push **Mangler** on the harsh
layers and 808s. Treat all of it as a starting point to steer by ear.

## What I need from you
1. Your **Nectar 4** and **Ozone 12** edition (Elements / Standard / Advanced) — it decides which modules exist.
2. `audio_inventory.md` from the scanner (Windows: `python tools\scan_audio_setup.py --redact-user`). It reads names
   only. Add `--library-root "D:\\Your Kontakt Libraries"` if your libraries are on another drive.
3. The output of **note 124** (Plugin Probe) with your chain loaded. Then I can wire real parameter names into
   automation instead of guessing which ones iZotope and Unison expose.
