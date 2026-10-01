"""Shared helpers for the sample-pack switcher generators (packs_to_sfz.py, packs_to_dspreset.py).

A "pack" is a folder of audio files. The same keys play a different pack depending on which
keyswitch (or menu entry) is active, so one keyboard range can DJ between songs, kits or stems.
"""
import os
import wave
from pathlib import Path

AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac"}
BLACK_PITCH_CLASSES = {1, 3, 6, 8, 10}


def list_samples(folder):
    """Audio files directly inside `folder`, sorted case-insensitively by name."""
    files = [p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS]
    return sorted(files, key=lambda p: p.name.lower())


def list_packs(root):
    """Sub-folders of `root` that contain audio, sorted by name. If `root` itself holds audio
    and has no audio sub-folders, it is treated as a single pack."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"pack folder not found: {root}")
    packs = [p for p in sorted(root.iterdir(), key=lambda p: p.name.lower()) if p.is_dir() and list_samples(p)]
    if not packs and list_samples(root):
        packs = [root]
    if not packs:
        raise ValueError(f"no audio files (.wav/.aif/.aiff/.flac) found under {root}")
    return packs


def playable_keys(first_key, count, white_keys_only=False):
    """The next `count` MIDI notes from `first_key`, optionally skipping black keys."""
    keys, note = [], first_key
    while len(keys) < count:
        if note > 127:
            raise ValueError(f"{count} samples do not fit on the keyboard starting at note {first_key}"
                             + (" (white keys only)" if white_keys_only else ""))
        if not (white_keys_only and note % 12 in BLACK_PITCH_CLASSES):
            keys.append(note)
        note += 1
    return keys


def switch_keys(switch_first_key, first_key, playable, pack_count):
    """MIDI notes that select each pack. Defaults to the block just below the playable keys.
    Raises if the block would run off the keyboard or collide with a playable key."""
    start = first_key - pack_count if switch_first_key is None else switch_first_key
    keys = list(range(start, start + pack_count))
    if start < 0 or keys[-1] > 127:
        raise ValueError(f"the {pack_count} keyswitch keys starting at {start} do not fit on the keyboard; "
                         "pass --switch-first-key or a higher --first-key")
    clash = sorted(set(keys) & set(playable))
    if clash:
        raise ValueError(f"keyswitch keys {clash} overlap sample keys; move them with --switch-first-key")
    return keys


def wav_frames(path):
    """Length in sample frames of a PCM .wav, or None if it isn't a readable PCM wav."""
    if Path(path).suffix.lower() != ".wav":
        return None
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes()
    except (wave.Error, EOFError, OSError):
        return None


def relative_posix(path, start):
    """`path` relative to the folder `start`, using forward slashes (what SFZ and DecentSampler expect)."""
    return Path(os.path.relpath(path, start)).as_posix()
