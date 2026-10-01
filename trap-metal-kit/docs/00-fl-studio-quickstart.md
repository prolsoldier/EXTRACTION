# FL Studio quickstart (about 10 minutes)

One script, **Trap Metal Kit**, on **one MIDI input**, gives you all of this from your keyboard or pads:

- **DJ decks**: every key launches a Performance Mode clip, the mod wheel crossfades two decks.
- **Vocal mixer in one key**: names, colours, routing to a Vox Bus, reverb/delay sends, lead armed.
- **Vocal-chain audit**: are Nectar 4, Ozone 12 and a distortion on the right inserts?
- **Plugin probe**: every plugin in your mixer and every parameter FL can automate.
- **Pink theme**: channels, mixer, playlist tracks and patterns in pink / purple / red / black.

FL Studio runs only one controller script per MIDI input, which is why these four are bundled into one file
(`fl-studio/device_TrapMetalKit.py`). The four standalone scripts are still there if you'd rather have one per input.

## 1. Install

```bash
python3 tools/install_fl_studio.py --dry-run     # see what it will do first
python3 tools/install_fl_studio.py               # install the bundle
```

It finds `Documents/Image-Line/FL Studio/Settings/Hardware` (including OneDrive-redirected Documents), puts the script in
`Hardware/TrapMetalKit/device_TrapMetalKit.py`, and backs up any differing copy it would replace as
`device_TrapMetalKit.py.<timestamp>.bak`. If FL Studio's data folder is somewhere unusual, pass it:
`--dest "<folder>/Settings/Hardware"`. `--standalone` adds the four separate scripts, `--uninstall` removes what it installed.

No Python handy? Copy `fl-studio/device_TrapMetalKit.py` to
`Documents\Image-Line\FL Studio\Settings\Hardware\TrapMetalKit\device_TrapMetalKit.py` yourself. The folder name is
arbitrary but the file must be called `device_<foldername>.py`.

## 2. Assign it to your keyboard

1. FL Studio: **Options > MIDI Settings** (F10).
2. Under **Input**, click your keyboard or pad controller and tick **Enable**.
3. Set **Controller type** to **Trap Metal Kit (user)**. (The "(user)" suffix marks scripts you installed yourself.)
4. Give it a **Port** number (any number not used by another input).

After changing the script later, press **Reload** on that screen: no need to restart FL Studio.

No keyboard? Any virtual MIDI port works (for example loopMIDI on Windows, the IAC driver on macOS) with a virtual
keyboard app sending notes into it; select that port as the input.

## 3. Check it's alive

Open **View > Script output**. You should see:

```
Trap Metal Kit: ready (build 1a2b3c4d). Parts on: TrapDJ, VocalSetup, PluginProbe, PinkTheme
Trap Metal Kit:   notes 36-67 launch clips (4 decks x 8), 68-71 stop decks; CC 1 crossfades mixer inserts 10 and 11
Trap Metal Kit:   note 72 lists every plugin and parameter
Trap Metal Kit:   note 73 audits the vocal chain; note 74 builds the vocal mixer
Trap Metal Kit:   note 75 repaints everything pink
```

(The build id will differ.) If the pink theme is on, your rows are already painted. If you see a `WARNING:` line, two
parts want the same key or mixer insert: see section 7.

## 4. The key map

FL Studio calls MIDI note 60 "C5", so FL's names run two octaves above what some keyboards print on the keys. Count
from the numbers: the lowest key in use is **note 36, two octaves below middle C (60)**, and everything sits in the
four octaves from there, inside a 49-, 61- or 88-key range.

| Note | FL name | Does | Changes your project? |
|---|---|---|---|
| 36 to 67 | C3 to G5 | Launch clip: 4 decks (playlist tracks 1 to 4) x 8 clips; 8 keys per deck | no |
| 68 to 71 | G#5 to B5 | Stop deck 1 to 4 | no |
| 72 | C6 | **Probe**: list every plugin and its parameters in Script output | no (read-only) |
| 73 | C#6 | **Audit**: check Nectar 4 / Ozone 12 / distortion are on the right inserts | no (read-only) |
| 74 | D6 | **Setup**: build the vocal mixer on inserts 1 to 8 | **yes: press twice** |
| 75 | D#6 | **Repaint**: pink / purple / red / black over everything | **yes: press twice** |
| Mod wheel (CC 1) | | Crossfade deck 1 against deck 2 on mixer inserts 10 and 11 | volume of those two inserts |

**Press twice** means: the first press only prints what it would do; press the same key again within 3 seconds to run
it. A stray key while playing can't rewrite your mixer.

## 5. DJ decks: set up Performance Mode

The script can launch clips; it can't create them. Once per project:

1. Switch on **Performance mode**: Playlist menu > Performance mode, or **Ctrl+P**.
2. Put your audio clips on playlist tracks 1 to 4, **inside the Performance Zone** (left of the Start marker; only clips
   there can be triggered), and add Live block markers: they define the blocks (0, 1, 2 ...) that the keys trigger.
3. Right-click each playlist track header > **Performance settings** (only available in Performance mode): set
   **Trigger sync** to a bar value and **Press** to **Latch** (or **Hold & stop**).
4. For the crossfader, send the audio clips on playlist track 1 through mixer insert **10** and track 2 through insert
   **11** (each audio clip's channel has a mixer-track selector).

Key 36 is track 1 block 0, key 37 is track 1 block 1, ... key 44 is track 2 block 0. If the clips come out one off,
change `TRACK_BASE` for TrapDJ in the CONFIG block of the script (section 8).

## 6. Vocals in one press

1. Press **73** (audit) any time. It lists what is on VOX MAIN, SCREAMS and the Master and says what's missing.
2. Press **74** twice. Inserts 1 to 8 become VOX MAIN, VOX DBL L, VOX DBL R, ADLIBS, SCREAMS, VOX BUS, REVERB, DELAY,
   routed to the bus with reverb/delay sends, and VOX MAIN is armed. It refuses to touch inserts you've already
   renamed yourself.
3. FL's scripting can't pick the audio input, load plugins or start recording. Pick the input on VOX MAIN, load Nectar 4
   on it (Vocal Assistant), Unison Mangler or similar on SCREAMS, Ozone 12 on the Master, and record.
4. Press **73** again to confirm the chain is in place. The rest of the vocal / mix / master workflow is in
   [07-vocal-automation-and-plugins.md](07-vocal-automation-and-plugins.md).

## 7. If something's off

| Symptom | Likely cause | Fix |
|---|---|---|
| "Trap Metal Kit (user)" isn't in the Controller type list | Script not where FL looks | Re-run the installer and check the folder it prints; the file must be `Hardware/<folder>/device_<folder>.py`; reopen MIDI Settings or restart FL |
| Nothing in Script output | Input not enabled / wrong port | Tick Enable on the right input; the Debugging log tab in MIDI Settings shows whether MIDI arrives at all |
| Keys play a synth instead of launching clips | Notes not what you think, or Performance mode is off | Check the Script output line for the real note numbers; Ctrl+P |
| Clips start late | **Trigger sync** is set to a long value | Right-click track header > Performance settings |
| Mod wheel changes vocal levels | A deck is on an insert in the vocal layout | The `WARNING: mixer insert N...` line says which; set `DECK_A_MIXER` / `DECK_B_MIXER` (section 8) |
| "press note 74 again within 3 seconds" | By design | Press it again |
| Send levels aren't set by Setup | Older FL Studio without `setRouteToLevel` | Routing still works; set the send knobs by hand |
| One part prints an error | A bug or API difference in that part | It's reported once and the others keep working; send the message |

## 8. Changing keys or turning parts off

Open `device_TrapMetalKit.py` in any text editor and edit the **CONFIG** block at the top (then press **Reload**):

```python
ENABLED = {"TrapDJ": True, "VocalSetup": True, "PluginProbe": True, "PinkTheme": False}   # theme off

OVERRIDES = {
    "TrapDJ": {"DECK_A_MIXER": 10, "DECK_B_MIXER": 11, "FIRST_NOTE": 48},                # decks start at 48
    "PinkTheme": {"REPAINT_NOTE": 75, "PAINT_ON_START": False},                           # don't repaint at launch
}
CONFIRM_SECONDS = 3.0
```

Every setting name comes from the top of that part's source script (`fl-studio/device_TrapDJ.py` etc.). A typo is
reported in Script output instead of silently ignored, and overlapping keys or mixer inserts print a `WARNING`.
Reinstalling replaces your edits (the old file is kept as a `.bak`). Anything deeper: change the source script and run
`python3 tools/build_fl_bundle.py`.

## 9. What has and hasn't been checked

- **Checked against Image-Line's published API** (`pip install fl-studio-api-stubs`, then
  `python3 tools/check_fl_api.py`): every FL function the scripts call exists and takes the arguments given.
- **Tested against stand-ins for FL's modules**: key mapping, the press-twice guard, conflict warnings, one part
  failing without stopping the others, install / backup / uninstall.
- **Not yet run inside FL Studio.** Nothing here has been loaded into a real FL Studio session. In particular, how FL
  numbers Live blocks (and so which clip a key launches) is taken from the API's description and has not been
  confirmed in a real project. If something behaves differently from this page, the Script output is the first place to
  look, and sending it back is the fastest fix.
