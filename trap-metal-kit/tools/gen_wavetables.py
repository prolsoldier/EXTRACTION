#!/usr/bin/env python3
"""Generate 2048-samples-per-frame wavetable .wav files for wavetable synths (Vital, Serum, ...).

    python3 gen_wavetables.py --preset rage_fold -o rage_fold.wav
    python3 gen_wavetables.py --preset all -d wavetables/ --frames 64

Presets
    rage_fold      saw wave pushed through a growing wave-folder: clean -> harsh, for rage / trap-metal leads
    vowel_morph    additive harmonics shaped by moving vowel formants (A -> E -> I -> O -> U): vocal-ish leads
    crushed_lead   sine that is increasingly clipped and bit-quantised: 8-bit hyperpop leads

Import the file as a wavetable with 2048 samples per frame (Serum's default; in Vital's import dialog
choose the 2048-sample option). Output is 16-bit mono PCM; every frame is DC-removed and peak-normalised
so the morph does not jump in loudness. Standard library only.
"""
import argparse
import math
import struct
import sys
import wave
from pathlib import Path

FRAME = 2048
PEAK = 0.95
VOWELS = [(8, 13), (4, 24), (3, 28), (6, 10), (3, 8)]  # (F1, F2) as harmonic numbers: A E I O U


def fold(x):
    """Reflect x back into [-1, 1] (triangle wavefolder)."""
    return (2 / math.pi) * math.asin(math.sin(math.pi * x / 2))


def rage_fold_frame(position):
    gain = 1 + 9 * position
    return [fold((2 * n / FRAME - 1) * gain) for n in range(FRAME)]


def vowel_morph_frame(position, harmonics=48):
    segment = position * (len(VOWELS) - 1)
    a = min(int(segment), len(VOWELS) - 2)
    blend = segment - a
    f1 = VOWELS[a][0] + (VOWELS[a + 1][0] - VOWELS[a][0]) * blend
    f2 = VOWELS[a][1] + (VOWELS[a + 1][1] - VOWELS[a][1]) * blend
    amps = []
    for k in range(1, harmonics + 1):
        formant = math.exp(-((k - f1) / 1.8) ** 2) + 0.7 * math.exp(-((k - f2) / 2.5) ** 2)
        amps.append((0.05 + formant) / k ** 0.5)
    table = [math.sin(2 * math.pi * i / FRAME) for i in range(FRAME)]
    return [sum(amp * table[(k * n) % FRAME] for k, amp in enumerate(amps, start=1)) for n in range(FRAME)]


def crushed_lead_frame(position):
    drive = 1 + 5 * position
    bits = round(8 - 6 * position)  # 8 bits -> 2 bits
    levels = 2 ** (bits - 1)
    frame = []
    for n in range(FRAME):
        x = max(-1.0, min(1.0, drive * math.sin(2 * math.pi * n / FRAME)))
        frame.append(round(x * levels) / levels)
    return frame


PRESETS = {"rage_fold": rage_fold_frame, "vowel_morph": vowel_morph_frame, "crushed_lead": crushed_lead_frame}


def finish(frame):
    mean = sum(frame) / len(frame)
    frame = [s - mean for s in frame]
    peak = max(abs(s) for s in frame) or 1.0
    return [s * PEAK / peak for s in frame]


def generate(preset, frames=64):
    """Return `frames * 2048` samples for the named preset."""
    if frames < 2:
        raise ValueError("need at least 2 frames to morph between")
    build = PRESETS[preset]
    samples = []
    for i in range(frames):
        samples.extend(finish(build(i / (frames - 1))))
    return samples


def write_wav(path, samples, sample_rate=44100):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *(round(s * 32767) for s in samples)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--preset", choices=sorted(PRESETS) + ["all"], required=True)
    parser.add_argument("--frames", type=int, default=64, help="frames in the table (default 64; Serum allows up to 256)")
    parser.add_argument("-o", "--output", help="output .wav (single preset)")
    parser.add_argument("-d", "--outdir", help="output folder (use with --preset all, or instead of -o)")
    args = parser.parse_args(argv)

    names = sorted(PRESETS) if args.preset == "all" else [args.preset]
    if len(names) > 1 and not args.outdir:
        parser.error("--preset all needs -d/--outdir")
    if len(names) == 1 and not (args.output or args.outdir):
        parser.error("give -o FILE or -d DIR")
    try:
        for name in names:
            path = Path(args.output) if args.output and len(names) == 1 else Path(args.outdir) / f"{name}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            write_wav(path, generate(name, args.frames))
            print(f"Wrote {path} ({args.frames} frames x {FRAME} samples)")
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
