#!/usr/bin/env python3
"""Batch vocal-prep and loudness-mastering for a folder of audio files.

    # 1. Gain-stage raw vocal takes before they hit your plugin chain
    python3 master_batch.py prep takes/ -o prepped/

    # 2. Bring finished mixes to a loudness target with a true-peak ceiling
    python3 master_batch.py master mixes/ -o masters/ --preset loud

    # 3. Reference-based mastering with Matchering (pip install matchering)
    python3 master_batch.py master mixes/ -o masters/ --reference favourite_song.wav

    # 4. Check files you already exported (e.g. from Ozone 12) WITHOUT changing them
    python3 master_batch.py measure exports/ --lufs -9 --ceiling -1 --strict

prep    trims leading/trailing silence (keeping a short pad), high-passes at 60 Hz, peak-normalises to -6 dBFS.
measure reports integrated loudness, true peak and sample peak for each file and warns if the true peak is over
        the ceiling or the loudness is more than --tolerance LU from --lufs / --preset. Changes nothing. With
        --strict the exit code is 2 when anything warns, so a script can gate on it.
master  measures integrated loudness (ITU-R BS.1770 via pyloudnorm), applies gain, runs a look-ahead peak
        limiter, and repeats until the result lands on the LUFS target with the true peak under the ceiling.

Presets (my starting points, not standards): streaming -14 LUFS, loud -9 LUFS, both with a -1 dBTP ceiling.
Set --lufs / --ceiling to override. If a target can't be reached without breaking the ceiling, the report says so.

Needs: pip install numpy scipy soundfile pyloudnorm     (matchering optional).  Reads wav/flac/aiff; writes 24-bit wav.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal
from scipy.ndimage import minimum_filter1d, uniform_filter1d

PRESETS = {"streaming": -14.0, "loud": -9.0}
AUDIO_SUFFIXES = {".wav", ".flac", ".aif", ".aiff"}


def read_audio(path):
    data, rate = sf.read(str(path), always_2d=True, dtype="float64")
    return data, rate


def write_audio(path, data, rate):
    sf.write(str(path), data, rate, subtype="PCM_24")


def db(value):
    return 20 * np.log10(max(float(value), 1e-12))


def loudness(data, rate):
    """Integrated loudness in LUFS, or -inf for silence / too-short audio."""
    if data.shape[0] < int(0.4 * rate) or float(np.max(np.abs(data))) < 1e-9:
        return float("-inf")
    return float(pyln.Meter(rate).integrated_loudness(data))


def true_peak_db(data, rate, oversample=4):
    """Estimated inter-sample (true) peak in dBTP using 4x oversampling."""
    peak = 0.0
    for ch in range(data.shape[1]):
        peak = max(peak, float(np.max(np.abs(signal.resample_poly(data[:, ch], oversample, 1)))))
    return db(peak)


def limit(data, rate, ceiling_db, lookahead_ms=5.0, hold_ms=25.0):
    """Look-ahead peak limiter (stereo-linked). Guarantees sample peaks <= ceiling.

    The gain needed at each sample is spread with a sliding minimum (hold) and a box-car smoother
    (attack ramp). The smoother is never wider than the hold window, so the result cannot exceed the ceiling.
    """
    ceiling = 10 ** (ceiling_db / 20)
    peak = np.max(np.abs(data), axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-12))
    ramp = max(2, int(rate * lookahead_ms / 1000))
    hold = max(ramp + 1, int(rate * hold_ms / 1000))
    held = minimum_filter1d(need, size=2 * hold - 1, mode="nearest")
    gain = uniform_filter1d(held, size=ramp, mode="nearest")
    gain = np.minimum(gain, need)  # belt and braces against rounding
    return data * gain[:, None]


def master(data, rate, target_lufs, ceiling_dbtp=-1.0, max_iterations=10, tolerance=0.1):
    """Return (mastered, info). info: input_lufs, output_lufs, true_peak, gain_db, reached."""
    input_lufs = loudness(data, rate)
    if not np.isfinite(input_lufs):
        return data, dict(input_lufs=input_lufs, output_lufs=input_lufs, true_peak=true_peak_db(data, rate),
                          gain_db=0.0, reached=False, note="silent or too short")
    gain_db = target_lufs - input_lufs
    sample_ceiling = ceiling_dbtp
    best = data
    for _ in range(max_iterations):
        candidate = limit(data * 10 ** (gain_db / 20), rate, sample_ceiling)
        for _ in range(4):  # pull the ceiling down until the *true* peak fits
            excess = true_peak_db(candidate, rate) - ceiling_dbtp
            if excess <= 0.02:
                break
            sample_ceiling -= excess + 0.05
            candidate = limit(data * 10 ** (gain_db / 20), rate, sample_ceiling)
        best = candidate
        error = target_lufs - loudness(best, rate)
        if abs(error) <= tolerance or gain_db > 30:
            break
        gain_db += error
    output_lufs = loudness(best, rate)
    return best, dict(input_lufs=input_lufs, output_lufs=output_lufs, true_peak=true_peak_db(best, rate),
                      gain_db=gain_db, reached=abs(target_lufs - output_lufs) <= tolerance * 2)


def prep_vocal(data, rate, silence_db=-50.0, pad_ms=50.0, peak_db=-6.0, highpass_hz=60.0):
    """Trim silence, high-pass, and peak-normalise a raw take. Returns (audio, info)."""
    sos = signal.butter(2, highpass_hz, btype="highpass", fs=rate, output="sos")
    filtered = signal.sosfilt(sos, data, axis=0)
    level = np.max(np.abs(filtered), axis=1)
    active = np.flatnonzero(level > 10 ** (silence_db / 20))
    if active.size == 0:
        return filtered, dict(trimmed_s=0.0, peak_db=db(np.max(np.abs(filtered))), note="silent")
    pad = int(rate * pad_ms / 1000)
    start, end = max(0, active[0] - pad), min(len(filtered), active[-1] + pad + 1)
    trimmed = filtered[start:end]
    scale = 10 ** (peak_db / 20) / max(float(np.max(np.abs(trimmed))), 1e-12)
    return trimmed * scale, dict(trimmed_s=(len(filtered) - len(trimmed)) / rate, peak_db=peak_db)


def measure_file(path, target, ceiling, tolerance):
    """Return (report line, list of warnings). `target` may be None (no loudness check)."""
    data, rate = read_audio(path)
    lufs = loudness(data, rate)
    tp = true_peak_db(data, rate)
    sample_peak = db(np.max(np.abs(data)))
    warnings = []
    if tp > ceiling + 0.05:
        warnings.append(f"true peak {tp:.2f} dBTP is over the {ceiling:.1f} ceiling")
    if target is not None and np.isfinite(lufs) and abs(lufs - target) > tolerance:
        warnings.append(f"loudness {lufs:.1f} LUFS is {lufs - target:+.1f} LU from the {target:.1f} target")
    if not np.isfinite(lufs):
        warnings.append("silent or too short to measure")
    shown = f"{lufs:.1f} LUFS" if np.isfinite(lufs) else "-inf LUFS"
    line = f"{Path(path).name}: {shown}, {tp:.2f} dBTP, sample peak {sample_peak:.2f} dBFS"
    if warnings:
        line += "   [WARN: " + "; ".join(warnings) + "]"
    return line, warnings


def find_inputs(paths):
    files = []
    for entry in map(Path, paths):
        if entry.is_dir():
            files += sorted(p for p in entry.iterdir() if p.suffix.lower() in AUDIO_SUFFIXES)
        elif entry.is_file():
            files.append(entry)
        else:
            raise FileNotFoundError(f"not found: {entry}")
    if not files:
        raise FileNotFoundError("no audio files (.wav/.flac/.aif/.aiff) found")
    return files


def run(args):
    files = find_inputs(args.inputs)
    if args.mode == "measure":
        target = args.lufs if args.lufs is not None else (PRESETS[args.preset] if args.preset else None)
        all_warnings, lines = [], []
        for path in files:
            line, warnings = measure_file(path, target, args.ceiling, args.tolerance)
            lines.append(line)
            all_warnings += warnings
        print("\n".join(lines))
        print(f"{len(files)} file(s) checked, {len(all_warnings)} warning(s).")
        return 2 if (args.strict and all_warnings) else 0
    if not args.output:
        raise FileNotFoundError("-o/--output is required for prep and master")
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    target = args.lufs if args.lufs is not None else PRESETS[args.preset or "streaming"]
    rows = []
    for path in files:
        if args.mode == "prep":
            data, rate = read_audio(path)
            out, info = prep_vocal(data, rate)
            dest = outdir / f"{path.stem}_prep.wav"
            write_audio(dest, out, rate)
            rows.append(f"{path.name}: trimmed {info['trimmed_s']:.2f}s, peak {info['peak_db']:.1f} dBFS -> {dest.name}")
        elif args.reference:
            try:
                import matchering as mg
            except ImportError:
                raise SystemExit("error: --reference needs matchering (pip install matchering)")
            dest = outdir / f"{path.stem}_matched.wav"
            mg.process(target=str(path), reference=str(args.reference), results=[mg.pcm24(str(dest))])
            rows.append(f"{path.name}: matched to {Path(args.reference).name} -> {dest.name}")
        else:
            data, rate = read_audio(path)
            out, info = master(data, rate, target, args.ceiling)
            dest = outdir / f"{path.stem}_master.wav"
            write_audio(dest, out, rate)
            flag = "" if info["reached"] else "   [target NOT reached: " + info.get("note", "ceiling limits loudness") + "]"
            rows.append(f"{path.name}: {info['input_lufs']:.1f} -> {info['output_lufs']:.1f} LUFS "
                        f"(target {target:.1f}), {info['true_peak']:.2f} dBTP, gain {info['gain_db']:+.1f} dB{flag}")
    print("\n".join(rows))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=["prep", "master", "measure"])
    parser.add_argument("inputs", nargs="+", help="audio files and/or folders")
    parser.add_argument("-o", "--output", help="folder for the results (prep and master)")
    parser.add_argument("--preset", choices=sorted(PRESETS), default=None, help="loudness preset (master default: streaming)")
    parser.add_argument("--lufs", type=float, default=None, help="integrated loudness target (overrides preset)")
    parser.add_argument("--ceiling", type=float, default=-1.0, help="true-peak ceiling in dBTP (default -1.0)")
    parser.add_argument("--reference", help="reference track for Matchering (master mode)")
    parser.add_argument("--tolerance", type=float, default=1.0, help="measure: allowed distance from the LUFS target (default 1.0 LU)")
    parser.add_argument("--strict", action="store_true", help="measure: exit with code 2 if any file warns")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except FileNotFoundError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
