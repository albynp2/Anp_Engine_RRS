"""Library musik latar. Bawaan = disintesis sendiri (bebas hak cipta). Upload = tanggung jawab lisensi user."""
from pathlib import Path
from typing import List, Optional

import numpy as np

from . import audio, config, db

SR = 32000
DUR = 48  # detik, durasi kelipatan periode sehingga loop mulus


def _norm(x: np.ndarray, peak: float = 0.5) -> np.ndarray:
    return (x / (np.abs(x).max() + 1e-9) * peak).astype(np.float32)


def _loop_fix(x: np.ndarray, fade: float = 2.0) -> np.ndarray:
    n = int(fade * SR)
    head, tail = x[:n].copy(), x[-n:].copy()
    w = np.linspace(0, 1, n, dtype=np.float32)
    y = x[:-n].copy()
    y[:n] = head * w + tail * (1 - w)
    return y


def _t():
    return np.arange(DUR * SR) / SR


def dark_drone():
    t = _t()
    x = sum(a * np.sin(2 * np.pi * f * t + p) for f, a, p in
            [(55, 1.0, 0), (82.5, 0.6, 1), (110, 0.5, 2), (165, 0.25, 3)])
    return _norm(x * (0.75 + 0.25 * np.sin(2 * np.pi * 0.125 * t)))


def tense_pulse():
    t = _t()
    base = np.sin(2 * np.pi * 55 * t) * 0.5 + np.sin(2 * np.pi * 82.5 * t) * 0.25
    beat = np.zeros_like(t)
    for s in range(DUR):  # detak jantung lub-dub tiap detik
        for off, amp in ((0.0, 1.0), (0.32, 0.7)):
            a = int((s + off) * SR)
            n = int(0.22 * SR)
            k = np.arange(n) / SR
            beat[a:a + n] += amp * np.sin(2 * np.pi * 52 * k) * np.exp(-k * 18)
    return _norm(base * 0.6 + beat)


def cold_wind():
    rng = np.random.default_rng(7)
    n = DUR * SR
    noise = rng.normal(0, 1, n).astype(np.float32)
    low = np.convolve(noise, np.ones(180, np.float32) / 180, mode="same")
    t = _t()
    x = low * (0.6 + 0.4 * np.sin(2 * np.pi * 0.0625 * t)) + 0.05 * np.sin(2 * np.pi * 220 * t)
    return _norm(x)


def sad_pad():
    t = _t()
    trem = 0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * t)
    x = sum(a * np.sin(2 * np.pi * f * t) for f, a in [(110, 1.0), (130.5, 0.7), (164.5, 0.6), (220, 0.3)])
    return _norm(x * trem)


BUILTIN = [
    ("Dark Drone (bawaan)", "builtin_dark_drone.wav", dark_drone, "Dengung gelap, cocok horor/misteri"),
    ("Tense Pulse (bawaan)", "builtin_tense_pulse.wav", tense_pulse, "Detak jantung tegang, cocok kriminal"),
    ("Cold Wind (bawaan)", "builtin_cold_wind.wav", cold_wind, "Angin dingin, atmosfer sepi"),
    ("Sad Pad (bawaan)", "builtin_sad_pad.wav", sad_pad, "Pad lembut sedih, cocok kisah pilu"),
]


def ensure_builtin():
    for name, fn, gen, note in BUILTIN:
        p = config.MUSIC_DIR / fn
        if not p.exists():
            audio.write_wav(p, _loop_fix(gen()), SR)
        if not db.q_one("SELECT id FROM music_tracks WHERE filename=?", (fn,)):
            db.execute("INSERT INTO music_tracks (name, filename, source, license_note, builtin) "
                       "VALUES (?,?,?,?,1)", (name, fn, "Disintesis oleh aplikasi", "Bebas hak cipta. " + note))


def list_all() -> List[dict]:
    return db.q_all("SELECT * FROM music_tracks ORDER BY builtin DESC, id")


def get_path(mid) -> Optional[Path]:
    if not mid:
        return None
    r = db.q_one("SELECT filename FROM music_tracks WHERE id=?", (int(mid),))
    p = config.MUSIC_DIR / r["filename"] if r else None
    return p if p and p.exists() else None


def add_upload(name: str, filename: str, data: bytes, source: str, license_note: str) -> int:
    ext = Path(filename).suffix.lower()
    if ext not in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"):
        raise ValueError("Format musik harus mp3/wav/m4a/ogg/flac")
    if len(data) > 60 * 1024 * 1024:
        raise ValueError("File musik terlalu besar (maks 60 MB)")
    safe = f"user_{int(__import__('time').time())}{ext}"
    (config.MUSIC_DIR / safe).write_bytes(data)
    return db.execute("INSERT INTO music_tracks (name, filename, source, license_note, builtin) VALUES (?,?,?,?,0)",
                      (name or Path(filename).stem, safe, source, license_note))


def delete(mid: int) -> bool:
    r = db.q_one("SELECT filename, builtin FROM music_tracks WHERE id=?", (mid,))
    if not r or r["builtin"]:
        return False
    (config.MUSIC_DIR / r["filename"]).unlink(missing_ok=True)
    db.execute("DELETE FROM music_tracks WHERE id=?", (mid,))
    return True
