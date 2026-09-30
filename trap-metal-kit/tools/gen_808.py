#!/usr/bin/env python3
"""Generate distorted 808 one-shots: a sine with a fast pitch drop, a long decay and a tanh saturator
that bites hardest on the attack and cleans up as the note dies away (like an overdriven amp stage).

    python3 gen_808.py --note 33 -d 808s/                 # one A1 (55 Hz) 808
    python3 gen_808.py --note 24 28 33 36 --drive 18 -d 808s/

Each note is written to <outdir>/808_<midi note>.wav (mono, 16-bit, 44.1 kHz). Drop the folder into a
pack for packs_to_sfz.py / packs_to_dspreset.py, a Kontakt Leap slot, or any sampler. The file's root
pitch is the MIDI note you asked for. Standard library only.
"""
import argparse
import math
import random
import struct
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 44100
PEAK = 0.95


def make_808(note=33, seconds=1.6, drive_db=12.0, pitch_drop=7.0, pitch_time=0.045,
             decay=0.9, click=0.15, seed=1, sample_rate=SAMPLE_RATE):
    """Return the 808 as a list of floats in [-0.95, 0.95].

    note        MIDI note of the resting pitch (33 = A1 = 55 Hz)
    drive_db    saturation amount; 0 is almost a clean sine
    pitch_drop  semitones the pitch starts above the note, falling with time constant pitch_time (s)
    decay       amplitude decay time constant in seconds
    click       level of a 4 ms noise transient at the start (0 = none)
    """
    rng = random.Random(seed)
    base = 440.0 * 2 ** ((note - 69) / 12)
    drive = 10 ** (drive_db / 20)
    total = int(seconds * sample_rate)
    fade = int(0.03 * sample_rate)
    phase, out = 0.0, []
    for i in range(total):
        t = i / sample_rate
        phase += 2 * math.pi * base * 2 ** (pitch_drop * math.exp(-t / pitch_time) / 12) / sample_rate
        env = min(1.0, t / 0.002) * math.exp(-t / decay)
        sample = math.tanh(drive * env * math.sin(phase))
        if click:
            sample += click * rng.uniform(-1, 1) * math.exp(-t / 0.004)
        if i >= total - fade:
            sample *= (total - i) / fade
        out.append(sample)
    peak = max(abs(s) for s in out) or 1.0
    return [s * PEAK / peak for s in out]


def write_wav(path, samples, sample_rate=SAMPLE_RATE):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *(round(s * 32767) for s in samples)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--note", type=int, nargs="+", required=True, help="MIDI note(s), e.g. 33 for A1")
    parser.add_argument("-d", "--outdir", required=True, help="folder to write 808_<note>.wav files into")
    parser.add_argument("--seconds", type=float, default=1.6)
    parser.add_argument("--drive", type=float, default=12.0, help="saturation in dB (default 12)")
    parser.add_argument("--pitch-drop", type=float, default=7.0, help="starting pitch offset in semitones")
    parser.add_argument("--decay", type=float, default=0.9, help="decay time constant in seconds")
    parser.add_argument("--click", type=float, default=0.15, help="attack click level (0 disables)")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    if not all(0 <= n <= 127 for n in args.note):
        print("error: notes must be between 0 and 127", file=sys.stderr)
        return 1
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for note in args.note:
        samples = make_808(note, args.seconds, args.drive, args.pitch_drop, decay=args.decay,
                           click=args.click, seed=args.seed)
        path = outdir / f"808_{note}.wav"
        write_wav(path, samples)
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
