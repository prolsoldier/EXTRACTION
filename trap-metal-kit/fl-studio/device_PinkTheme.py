# name=Pink Theme Painter
"""FL Studio MIDI-controller script: paints every row in a pink / purple / red / black palette, pink dominant.

What it colours (all through documented FL scripting calls):
    channel rack rows      channels.setChannelColor
    mixer inserts          mixer.setTrackColor
    playlist tracks        playlist.setTrackColor
    patterns               patterns.setPatternColor

Every row gets the next colour of a 10-colour cycle (6 pinks, 2 purples, 1 red, 1 near-black), and no two
neighbouring rows share a colour, so the rack reads as different-coloured stripes with pink in charge.
It paints once when the script starts, then again for any channel or pattern you add afterwards. Rows you
already have keep whatever colour you give them by hand until you repaint (see REPAINT_NOTE).

Setup: copy to  Documents/Image-Line/FL Studio/Settings/Hardware/PinkTheme/device_PinkTheme.py , then in
Options > MIDI Settings pick "Pink Theme Painter" as the controller type for any MIDI input (it does not
need a keyboard; assign it to any port). Script output appears in View > Script output.

What this can NOT do: change FL's own UI colours (Hue / Selection / Highlight / Steps / note colours). Those
live in Options > Theme (F10); docs/06-pink-theme.md lists the exact values to enter. I found nothing in
FL's scripting API or manual for recolouring the piano roll's keyboard keys themselves.

Colour format: FL uses 0x--BBGGRR. Tested against stubs of the FL modules, not inside FL Studio.
"""
import channels
import mixer
import patterns
import playlist

# name -> (r, g, b)
COLORS = {
    "hot_pink": (255, 20, 147),
    "neon_pink": (255, 77, 166),
    "magenta_pink": (233, 30, 140),
    "light_pink": (255, 158, 210),
    "purple": (155, 48, 255),
    "deep_purple": (91, 33, 182),
    "red": (224, 30, 75),
    "black": (46, 34, 51),  # dark plum, so the row stays visible on FL's dark UI
}
CYCLE = ["hot_pink", "neon_pink", "purple", "magenta_pink", "red",
         "light_pink", "black", "hot_pink", "deep_purple", "neon_pink"]
PINKS = {"hot_pink", "neon_pink", "magenta_pink", "light_pink"}

MAX_MIXER_INSERTS = 64      # paint at most this many inserts (index 1 upwards)
PLAYLIST_TRACKS = 64        # paint playlist tracks 1..N (FL has 500)
MASTER_COLOR = "hot_pink"   # mixer master track
REPAINT_NOTE = None         # set to a MIDI note number (e.g. 127) to repaint everything when it is pressed
PAINT_ON_START = True       # False: leave existing colours alone at start-up (new channels/patterns still get painted)
IDLE_CHECK_EVERY = 20       # OnIdle calls between "did anything get added?" checks


def rgb_to_fl(r, g, b):
    """FL colour integer (0x--BBGGRR)."""
    return (b << 16) | (g << 8) | r


def color_for(index):
    """FL colour for the row at `index` (0-based) in the repeating cycle."""
    return rgb_to_fl(*COLORS[CYCLE[index % len(CYCLE)]])


def set_channel_color(index, color):
    try:
        channels.setChannelColor(index, color, True)   # useGlobalIndex needs API 33+
    except TypeError:
        channels.setChannelColor(index, color)


def paint_channels(start=0):
    total = channels.channelCount(1)
    for i in range(start, total):
        set_channel_color(i, color_for(i))
    return total


def paint_mixer():
    mixer.setTrackColor(0, rgb_to_fl(*COLORS[MASTER_COLOR]))
    last_insert = max(mixer.trackCount() - 2, 0)   # trackCount includes master (0) and the utility "Current" track
    for i in range(1, min(last_insert, MAX_MIXER_INSERTS) + 1):
        mixer.setTrackColor(i, color_for(i - 1))


def paint_playlist():
    for i in range(1, PLAYLIST_TRACKS + 1):
        playlist.setTrackColor(i, color_for(i - 1))


def paint_patterns(start=1):
    total = patterns.patternCount()
    for i in range(start, total + 1):
        patterns.setPatternColor(i, color_for(i - 1))
    return total


_state = {"channels": 0, "patterns": 0, "idle": 0}


def paint_all():
    _state["channels"] = paint_channels()
    paint_mixer()
    paint_playlist()
    _state["patterns"] = paint_patterns()
    print("Pink Theme Painter: painted %d channels, %d patterns" % (_state["channels"], _state["patterns"]))


def OnInit():
    # FL may call OnInit again on a script it kept in memory (see the callbacks docs), so start from a clean state.
    _state.update(channels=0, patterns=0, idle=0)
    if PAINT_ON_START:
        paint_all()
    else:  # remember what exists now so OnIdle only paints what is added later
        _state["channels"] = channels.channelCount(1)
        _state["patterns"] = patterns.patternCount()


def OnIdle():
    _state["idle"] += 1
    if _state["idle"] % IDLE_CHECK_EVERY:
        return
    channel_total = channels.channelCount(1)
    if channel_total > _state["channels"]:          # only paint what was added; never touch older rows
        paint_channels(_state["channels"])
    _state["channels"] = channel_total
    pattern_total = patterns.patternCount()
    if pattern_total > _state["patterns"]:
        paint_patterns(_state["patterns"] + 1)
    _state["patterns"] = pattern_total


def OnNoteOn(event):
    if REPAINT_NOTE is not None and event.data1 == REPAINT_NOTE and event.data2 > 0:
        paint_all()
        event.handled = True
