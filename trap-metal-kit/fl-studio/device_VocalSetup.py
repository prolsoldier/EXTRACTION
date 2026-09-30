# name=Vocal Session Setup
"""FL Studio MIDI-controller script: builds a vocal recording/mixing layout in the Mixer with one key press.

Press SETUP_NOTE (default 126, F#8) on the assigned MIDI input and it will, on mixer inserts FIRST_INSERT and up:

    * name and colour each insert (pink / purple / red palette to match device_PinkTheme.py)
    * route every vocal insert to the VOX BUS insert (and switch off its direct route to Master)
    * add send routes from every vocal insert to REVERB and DELAY at set levels
    * arm the lead vocal insert for recording (only if it is not armed already)

    VOX MAIN, VOX DBL L, VOX DBL R, ADLIBS, SCREAMS  ->  VOX BUS  ->  Master
                        each also sends to  REVERB and DELAY  ->  Master

What FL's scripting API cannot do: load plugins into slots, pick the audio input, or start recording. So after
running this, (1) pick the audio input on VOX MAIN's Input selector, (2) load your saved vocal-chain preset into
the inserts (save one once with a mixer track's preset menu), (3) press record. docs/07 walks through it.

Press AUDIT_NOTE (default 125) any time to CHECK THE CHAIN: it lists the plugin in every slot of the vocal inserts
and the Master, and says whether the ones you expect are there (Nectar 4 on VOX MAIN, Ozone 12 on Master, a
distortion such as Unison Mangler on SCREAMS). It only reads; it never loads or changes a plugin.

Safety: it refuses to touch an insert that you have already renamed to something else, and says so in the
script output (View > Script output). Set FORCE = True to override. Pressing the key again on inserts it named
itself is fine.

API used: mixer.setTrackName / setTrackColor / setRouteTo / setRouteToLevel (FL API 36+) / afterRoutingChanged /
isTrackArmed / armTrack, plus plugins.isValid / getPluginName for the audit. Tested against stubs of the FL modules,
not inside FL Studio.
"""
import re

import mixer

try:
    import plugins
except ImportError:  # only if FL's plugins module is unavailable
    plugins = None

SETUP_NOTE = 126
AUDIT_NOTE = 125
FORCE = False
FIRST_INSERT = 1
MASTER = 0

# (name, (r, g, b), role). Colours match device_PinkTheme.py.
LAYOUT = [
    ("VOX MAIN", (255, 20, 147), "vocal"),
    ("VOX DBL L", (255, 77, 166), "vocal"),
    ("VOX DBL R", (255, 77, 166), "vocal"),
    ("ADLIBS", (155, 48, 255), "vocal"),
    ("SCREAMS", (224, 30, 75), "vocal"),
    ("VOX BUS", (233, 30, 140), "bus"),
    ("REVERB", (91, 33, 182), "fx"),
    ("DELAY", (91, 33, 182), "fx"),
]
SEND_LEVELS = {"REVERB": 0.45, "DELAY": 0.35}   # 0.8 is FL's default (0 dB) send level
ARM_TRACK = "VOX MAIN"

MAX_SLOTS = 10
MASTER_NAME = "MASTER"
# Plugins each insert should carry. Each entry is a group of alternatives (lower-case substrings of the plugin
# name); the group is satisfied if ANY alternative is found in ANY slot of that insert.
EXPECTED = {
    "VOX MAIN": [("nectar",)],                                              # Nectar 4: Vocal Assistant / vocal chain
    "SCREAMS": [("mangler", "trash", "decapitator", "saturn", "nectar")],   # something that distorts
    MASTER_NAME: [("ozone",)],                                              # Ozone 12: Master Assistant / limiter
}
HINTS = [
    "VOX MAIN: load Nectar 4, open Vocal Assistant, pick a target, then set EQ / intensity / width and reverb/delay.",
    "SCREAMS / ADLIBS: add Unison Mangler (or Nectar's Saturation module if you own Nectar Advanced) for the grit.",
    "MASTER: load Ozone 12, open Master Assistant, choose the Trap / Hyperpop / Metal target, loudness target and "
    "Analysis Time on your loudest section, press Analyze while the chorus plays.",
    "Before you export: turn Ozone's Gain Match OFF, then run tools/master_batch.py measure on the file.",
]

_DEFAULT_NAME = re.compile(r"^\s*(insert\s*\d*)?\s*$", re.IGNORECASE)


def rgb_to_fl(r, g, b):
    return (b << 16) | (g << 8) | r


def index_of(name):
    for offset, (layout_name, _, _) in enumerate(LAYOUT):
        if layout_name == name:
            return FIRST_INSERT + offset
    raise KeyError(name)


def blocked_inserts():
    """Inserts in the layout range that carry a name the user chose (not a default, not one of ours)."""
    ours = {name for name, _, _ in LAYOUT}
    blocked = []
    for offset in range(len(LAYOUT)):
        index = FIRST_INSERT + offset
        current = mixer.getTrackName(index)
        if current not in ours and not _DEFAULT_NAME.match(current or ""):
            blocked.append((index, current))
    return blocked


def setup():
    if FIRST_INSERT + len(LAYOUT) > mixer.trackCount() - 1:
        print("Vocal Session Setup: not enough mixer inserts for the layout")
        return False
    blocked = blocked_inserts()
    if blocked and not FORCE:
        print("Vocal Session Setup: NOT run - these inserts already have names of your own: "
              + ", ".join("%d '%s'" % pair for pair in blocked) + ". Rename them or set FORCE = True.")
        return False

    for offset, (name, rgb, _) in enumerate(LAYOUT):
        mixer.setTrackName(FIRST_INSERT + offset, name)
        mixer.setTrackColor(FIRST_INSERT + offset, rgb_to_fl(*rgb))

    bus = index_of("VOX BUS")
    for name, _, role in LAYOUT:
        if role != "vocal":
            continue
        track = index_of(name)
        mixer.setRouteTo(track, bus, True)
        mixer.setRouteTo(track, MASTER, False)   # the bus feeds Master; avoid the vocal being counted twice
        for fx_name, level in SEND_LEVELS.items():
            fx = index_of(fx_name)
            mixer.setRouteTo(track, fx, True)
            try:
                mixer.setRouteToLevel(track, fx, level)
            except AttributeError:
                print("Vocal Session Setup: this FL version cannot set send levels (needs API 36+); "
                      "set the send knobs by hand")
    mixer.afterRoutingChanged()

    arm = index_of(ARM_TRACK)
    if not mixer.isTrackArmed(arm):
        mixer.armTrack(arm)
    print("Vocal Session Setup: done. Now pick the input on '%s', load your vocal chain, and record." % ARM_TRACK)
    for hint in HINTS:
        print("  - " + hint)
    return True


def slot_plugin_names(track_index):
    """Names of the plugins loaded in the slots of one mixer track (empty slots are skipped)."""
    names = []
    for slot in range(MAX_SLOTS):
        if plugins.isValid(track_index, slot):
            names.append(plugins.getPluginName(track_index, slot))
    return names


def audit():
    """Print and return {track name: {"plugins": [...], "missing": [...]}} for the tracks in EXPECTED."""
    if plugins is None:
        print("Vocal Session Setup: this FL version has no plugins module; cannot audit")
        return {}
    report = {}
    for track_name, groups in EXPECTED.items():
        index = MASTER if track_name == MASTER_NAME else index_of(track_name)
        loaded = slot_plugin_names(index)
        lowered = [n.lower() for n in loaded]
        missing = ["/".join(g) for g in groups if not any(alt in n for alt in g for n in lowered)]
        report[track_name] = {"plugins": loaded, "missing": missing}
        status = "OK     " if not missing else "MISSING"
        print("Vocal chain %s %-9s [%s]%s" % (status, track_name, ", ".join(loaded) or "empty",
                                              ("  load: " + ", ".join(missing)) if missing else ""))
    return report


def OnNoteOn(event):
    if event.data2 <= 0:
        return
    if event.data1 == SETUP_NOTE:
        setup()
        event.handled = True
    elif event.data1 == AUDIT_NOTE:
        audit()
        event.handled = True
