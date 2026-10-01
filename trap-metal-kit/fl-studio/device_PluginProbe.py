# name=Plugin Probe
"""FL Studio MIDI-controller script: READ-ONLY. Lists every plugin loaded in your mixer slots and the parameters
FL can see on each, so you know exactly what can be automated (Nectar 4, Ozone 12, Unison Mangler, ...).

Press PROBE_NOTE (default 124 = E10 in FL's note names) on the assigned MIDI input. Output goes to View > Script output:

    track 0 (Master) slot 0: Ozone 12   (57 params)
        [0] Bypass = 0.0
        [1] Output Gain = 0.5
        ...

Why: FL's scripting API can read and set the *normalised* value of any parameter a plugin exposes to the host, but
each plugin decides which parameters it exposes and what they are called. iZotope plugins, Unison plugins and
others differ, and I could not find those lists published. Run this once with your chain loaded, send me the output,
and specific parameters can be wired into automation from real names instead of guesses.

Nothing is written to FL: no parameter, preset or routing is changed. (API: plugins.isValid / getPluginName /
getParamCount / getParamName / getParamValue / getParamValueString, mixer.trackCount / getTrackName.)
Tested against stubs of the FL modules, not inside FL Studio.
"""
import mixer
import plugins

PROBE_NOTE = 124
MAX_SLOTS = 10
FIRST_TRACK = 0            # 0 is the Master
LAST_TRACK = 32            # probe tracks FIRST_TRACK..LAST_TRACK
MAX_PARAMS_PRINTED = 80    # per plugin (many plugins expose hundreds of unnamed parameters)


def describe_param(track, slot, param):
    name = plugins.getParamName(param, track, slot)
    value = plugins.getParamValue(param, track, slot)
    try:
        shown = plugins.getParamValueString(param, track, slot)
    except Exception:  # only some plugins support value strings
        shown = ""
    return name, value, shown


def probe():
    """Return [(track, slot, plugin name, [(param index, name, value, value string), ...]), ...] and print it."""
    results = []
    last = min(LAST_TRACK, mixer.trackCount() - 1)
    for track in range(FIRST_TRACK, last + 1):
        for slot in range(MAX_SLOTS):
            if not plugins.isValid(track, slot):
                continue
            count = plugins.getParamCount(track, slot)
            params = []
            for param in range(min(count, MAX_PARAMS_PRINTED)):
                name, value, shown = describe_param(track, slot, param)
                if name:
                    params.append((param, name, value, shown))
            title = plugins.getPluginName(track, slot)
            results.append((track, slot, title, params))
            print("track %d (%s) slot %d: %s   (%d params exposed)" % (track, mixer.getTrackName(track), slot, title, count))
            for param, name, value, shown in params:
                print("    [%d] %s = %.3f%s" % (param, name, value, ("  (" + shown + ")") if shown else ""))
            if count > MAX_PARAMS_PRINTED:
                print("    ... %d more" % (count - MAX_PARAMS_PRINTED))
    if not results:
        print("Plugin Probe: no plugins found in mixer slots %d-%d" % (FIRST_TRACK, last))
    return results


def OnNoteOn(event):
    if event.data1 == PROBE_NOTE and event.data2 > 0:
        probe()
        event.handled = True
