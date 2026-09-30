# Pink / black / purple / red FL Studio theme (pink dominant)

Two parts: a script that colours your **rows** automatically, and the **Theme editor** values for everything a
script can't reach.

## Part 1 — automatic row colours: `fl-studio/device_PinkTheme.py`

Every channel-rack row, mixer insert, playlist track and pattern gets the next colour of a 10-step cycle, so the rack
reads as stripes of different colours with pink in charge. Two neighbouring rows never share a colour.

| Name | Hex | RGB | Share of the cycle |
|---|---|---|---|
| hot_pink | #FF1493 | 255, 20, 147 | 2 of 10 |
| neon_pink | #FF4DA6 | 255, 77, 166 | 2 of 10 |
| magenta_pink | #E91E8C | 233, 30, 140 | 1 of 10 |
| light_pink | #FF9ED2 | 255, 158, 210 | 1 of 10 |
| purple | #9B30FF | 155, 48, 255 | 1 of 10 |
| deep_purple | #5B21B6 | 91, 33, 182 | 1 of 10 |
| red | #E01E4B | 224, 30, 75 | 1 of 10 |
| black | #2E2233 | 46, 34, 51 | 1 of 10 (dark plum, so it stays visible on FL's dark UI) |

Pinks are 6 of every 10 rows. Change the palette by editing `COLORS` and `CYCLE` at the top of the script.

**Install:** copy it to `Documents\Image-Line\FL Studio\Settings\Hardware\PinkTheme\device_PinkTheme.py`, then
Options ▸ MIDI Settings ▸ pick **Pink Theme Painter** as the controller type on any MIDI input (no keyboard needed).
It paints when it starts and again for any channel or pattern you add later. It does not repaint rows you coloured by
hand until you ask: set `REPAINT_NOTE = 127` in the script and press that key.

**Checked against the FL scripting manual:** `channels.setChannelColor`, `mixer.setTrackColor`,
`playlist.setTrackColor`, `patterns.setPatternColor`; colours are `0x--BBGGRR`. Tested against stubs of those modules,
not inside FL Studio. One thing to watch: on the FL forum, colouring a mixer insert that is linked to an instrument
was reported to colour that channel and playlist track too, so linked rows may take the mixer's colour.

## Part 2 — what only the Theme editor can do (Options ▸ Theme, or F10)

FL's manual lists these controls. A script can't reach them; enter the values by hand, then **Save preset** (user
themes save to `Documents\Image-Line\FL Studio\Settings\Themes`).

| Control | Suggested value | What it colours |
|---|---|---|
| Hue / Saturation / Brightness / Contrast | Turn **Hue** until the UI is magenta-pink, keep **Brightness** low so the base stays near-black | Overall UI tint (move the knobs slowly — FL warns they are laggy) |
| Selection | #FF1493 | "Selected" markers (mixer and playlist tracks) |
| Highlight | #FF4DA6 | Highlights such as toolbar buttons |
| Mute | #E01E4B (red) | Mute LEDs |
| Option | #9B30FF (purple) | Option LEDs |
| **Steps** | odd #FF1493, even #9B30FF | **Step-sequencer buttons — alternating pink / purple down the rack** |
| Meters | low #FF4DA6 → mid #9B30FF → top #E01E4B | Mixer meters (set each dB band's end-point colour) |
| Waves | low #E01E4B, mid #FF1493, high #9B30FF | Waveform colours by frequency. Needs *General settings ▸ Colorful waveforms* on |
| Text | near-white with a pink tint | Text |
| "Audio and automation clips use note colors" | tick it | Clips follow the note-colour palette below |

**Note colours (piano roll):** right-click the *Note Color selector* in the piano roll to change the 16 colours. FL
saves note colours with the theme. A pink-led set: `#FF1493 #FF4DA6 #E91E8C #FF9ED2 #9B30FF #5B21B6 #E01E4B #2E2233
#FF69B4 #FF007F #C71585 #D946EF #FF3D71 #F472B6 #7C3AED #BE123C`.

## What I could not do
- **The piano roll's own keyboard keys ("different colour keys all down").** Neither the theme controls in FL's manual
  nor the scripting API mention recolouring the piano roll's key strip. What you *can* colour: the notes (note colours),
  the step buttons (Steps odd/even), and every row (the script). If you meant something else by "keys", tell me which
  screen you're looking at.
- **Generate a theme file for you.** FL's manual documents the editor and where themes are saved, but not the file
  format, so I didn't fabricate one.
