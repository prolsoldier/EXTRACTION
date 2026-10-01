# name=Trap DJ Keys
"""FL Studio MIDI-controller script: play your keyboard like a DJ deck.

Every key launches one Performance Mode clip in the Playlist, so each track is a "deck"
and each block on that track is a different song/loop/stem. Pressing another key on the
same row blends the next piece in on the beat. A CC (mod wheel by default) crossfades two
mixer tracks.

Layout (FIRST_NOTE = 36 by default, i.e. C3 in FL's naming, where middle C = 60 = C5):

    keys 36..43   -> playlist track 1, blocks 0..7     (row 1 / deck 1)
    keys 44..51   -> playlist track 2, blocks 0..7     (row 2 / deck 2)
    ...           -> ROWS rows in total
    next ROWS keys-> stop the live clips on track 1..ROWS

Setup:
    1. Copy this file to
         Documents/Image-Line/FL Studio/Settings/Hardware/TrapDJ/device_TrapDJ.py
    2. FL Studio > Options > MIDI Settings: pick your keyboard as an input, set
       Controller type to "Trap DJ Keys", and give it a port number.
    3. Playlist: switch on Performance mode (Playlist menu > Performance mode, or Ctrl+P). Put
       your audio clips on the tracks inside the Performance Zone (left of the Start marker; only
       clips there can be triggered) and add Live block markers. Then right-click each track
       header > Performance settings: set "Trigger sync" to a bar value and "Press" to Latch
       (or Hold & stop). Those settings only appear while Performance mode is on.
    4. Route playlist track 1 -> mixer insert DECK_A_MIXER and track 2 -> DECK_B_MIXER
       if you want the crossfader.

API notes: playlist.triggerLiveClip, the midi.TLC_* flags and the OnNoteOn/OnControlChange
callbacks come from the FL Studio MIDI scripting manual. Block numbers are treated as
0-based and track numbers as 1-based (see TRACK_BASE); if your clips land one off, change
TRACK_BASE. This script has been tested against stubs of the FL modules, not inside FL Studio.
"""
import math

import midi
import mixer
import playlist

FIRST_NOTE = 36     # MIDI note of the first clip slot
COLUMNS = 8         # blocks (songs/loops) per deck row
ROWS = 4            # number of deck rows (playlist tracks)
TRACK_BASE = 1      # playlist track number of row 1

# Trigger-sync source: midi.TLC_TrackSnap uses each track's own "Trigger sync" setting,
# midi.TLC_GlobalSnap uses FL's global snap, midi.TLC_NoSnap fires immediately.
SNAP_FLAG = midi.TLC_TrackSnap

XFADE_CC = 1        # mod wheel. Set to None to disable the crossfader.
DECK_A_MIXER = 1    # mixer insert that carries deck A (left side of the crossfader)
DECK_B_MIXER = 2    # mixer insert that carries deck B (right side)
UNITY_VOLUME = 0.8  # FL's normalised mixer volume for 0 dB


def stop_first_note():
    """MIDI note of the first stop key. Worked out on demand so FIRST_NOTE / ROWS / COLUMNS can be changed later."""
    return FIRST_NOTE + ROWS * COLUMNS


def slot_for_note(note):
    """Return ('play', track, block), ('stop', track) or None for a MIDI note."""
    index = note - FIRST_NOTE
    if 0 <= index < ROWS * COLUMNS:
        return ("play", TRACK_BASE + index // COLUMNS, index % COLUMNS)
    stop_first = stop_first_note()
    if stop_first <= note < stop_first + ROWS:
        return ("stop", TRACK_BASE + (note - stop_first))
    return None


def crossfade_gains(position):
    """Equal-power crossfade. position 0.0 = all deck A, 1.0 = all deck B."""
    position = min(max(position, 0.0), 1.0)
    return math.cos(position * math.pi / 2), math.sin(position * math.pi / 2)


def OnInit():
    stop_first = stop_first_note()
    print("Trap DJ Keys: notes %d-%d launch clips, %d-%d stop decks"
          % (FIRST_NOTE, stop_first - 1, stop_first, stop_first + ROWS - 1))
    try:
        if not playlist.getPerformanceModeState():
            print("Trap DJ Keys: Performance Mode is off - enable it or clips will not launch")
    except AttributeError:
        pass  # getPerformanceModeState needs a recent FL Studio (API 21+)


def OnNoteOn(event):
    if event.data2 == 0:  # some keyboards send note-off as note-on with velocity 0
        return
    action = slot_for_note(event.data1)
    if action is None:
        return  # not one of ours; let FL play the note normally
    if action[0] == "play":
        _, track, block = action
        playlist.triggerLiveClip(track, block, SNAP_FLAG)
    else:
        _, track = action
        playlist.triggerLiveClip(track, -1, midi.TLC_Fill | SNAP_FLAG)
    event.handled = True


def OnNoteOff(event):
    if slot_for_note(event.data1) is not None:
        event.handled = True  # swallow the release so it does not reach the channel rack


def OnControlChange(event):
    if XFADE_CC is None or event.data1 != XFADE_CC:
        return
    gain_a, gain_b = crossfade_gains(event.data2 / 127.0)
    mixer.setTrackVolume(DECK_A_MIXER, UNITY_VOLUME * gain_a)
    mixer.setTrackVolume(DECK_B_MIXER, UNITY_VOLUME * gain_b)
    event.handled = True
