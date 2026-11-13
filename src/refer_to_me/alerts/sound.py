"""Alert sound: stdlib-synthesized default WAV (zero binary assets in the repo)."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from platformdirs import user_cache_dir

APP_DIR_NAME = "ReferToMe"


def default_sound_path() -> Path:
    return Path(user_cache_dir(APP_DIR_NAME, appauthor=False)) / "default_alert.wav"


def ensure_default_sound() -> Path:
    """Synthesize a 0.35s two-tone beep with fade-out on first use."""
    path = default_sound_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 44100
    duration = 0.35
    frames = bytearray()
    for i in range(int(rate * duration)):
        t = i / rate
        env = min(1.0, t / 0.01) * max(0.0, 1.0 - (t / duration) ** 2)
        freq = 880.0 if t < duration / 2 else 1320.0
        sample = int(32767 * 0.6 * env * math.sin(2 * math.pi * freq * t))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def resolve_sound_path(sound_file: str) -> Path:
    if sound_file:
        return Path(sound_file)
    return ensure_default_sound()
