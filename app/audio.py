"""Utilitas audio: decode via ffmpeg, envelope amplitudo (untuk gerak mulut), penyelarasan segmen."""
import subprocess
import wave
from pathlib import Path
from typing import List, Tuple

import numpy as np

SR = 24000  # sample rate kerja (mono)


def decode(path, sr: int = SR) -> np.ndarray:
    """File audio apa pun -> float32 mono [-1,1]."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1",
                        "-ar", str(sr), "-"], capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("Gagal membaca audio: " + p.stderr.decode("utf8", "ignore")[-300:])
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def write_wav(path, arr: np.ndarray, sr: int = SR):
    pcm = (np.clip(arr, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def concat(chunks: List[np.ndarray], sr: int = SR, lead: float = 0.35, gap: float = 0.25,
           tail: float = 0.9) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    """Gabung potongan narasi dengan jeda. Return (audio, [(start,end) detik per potongan])."""
    parts, times, pos = [np.zeros(int(lead * sr), np.float32)], [], lead
    for i, c in enumerate(chunks):
        times.append((pos, pos + len(c) / sr))
        parts.append(c.astype(np.float32))
        pos += len(c) / sr
        if i < len(chunks) - 1:
            parts.append(np.zeros(int(gap * sr), np.float32))
            pos += gap
    parts.append(np.zeros(int(tail * sr), np.float32))
    return np.concatenate(parts), times


def _smooth(x: np.ndarray, n: int) -> np.ndarray:
    if n <= 1 or len(x) < n:
        return x
    return np.convolve(x, np.ones(n, np.float32) / n, mode="same")


def envelope(arr: np.ndarray, sr: int, fps: int, n_frames: int) -> np.ndarray:
    """Level 'seberapa terbuka mulut' 0..1 per frame video, dari amplitudo suara."""
    hop = sr / fps
    out = np.zeros(n_frames, np.float32)
    win = int(hop * 1.5)
    for i in range(n_frames):
        a = int(i * hop)
        seg = arr[a:a + win]
        out[i] = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
    if not out.any():
        return out
    ref = float(np.percentile(out[out > out.max() * 0.05], 90)) if (out > out.max() * 0.05).any() else out.max()
    lvl = np.clip(out / max(ref, 1e-6), 0, 1.2).clip(0, 1) ** 0.85
    lvl[out < out.max() * 0.04] = 0.0  # senyap = mulut tertutup
    return _smooth(lvl, 3)


def snap_to_silence(arr: np.ndarray, sr: int, times: List[float], window: float = 1.0) -> List[float]:
    """Geser tiap batas ke titik paling sepi di sekitarnya (untuk audio hasil upload)."""
    step = int(0.02 * sr)
    n = len(arr) // step
    if n < 3:
        return list(times)
    e = np.sqrt(np.mean(arr[: n * step].reshape(n, step) ** 2, axis=1))
    e = _smooth(e, 5)
    out = []
    for t in times:
        c = int(t / 0.02)
        lo, hi = max(0, c - int(window / 0.02)), min(n, c + int(window / 0.02) + 1)
        if hi - lo < 3:
            out.append(t)
            continue
        seg = e[lo:hi]
        # pilih minimum; bila beberapa sama-sama sepi, ambil yang paling dekat target
        thr = seg.min() + 0.15 * (seg.max() - seg.min() + 1e-9)
        cands = np.where(seg <= thr)[0]
        best = lo + int(cands[np.argmin(np.abs((lo + cands) - c))])
        out.append(best * 0.02)
    return out


def proportional_bounds(texts: List[str], total: float, lead: float = 0.3, tail: float = 0.6) -> List[float]:
    """Batas awal tiap segmen (n+1 titik) menurut panjang teks, di dalam [lead, total-tail]."""
    w = np.array([max(1, len(t)) for t in texts], np.float64)
    span = max(0.5, total - lead - tail)
    cum = np.concatenate([[0], np.cumsum(w)]) / w.sum()
    return [lead + float(x) * span for x in cum]


def mouth_signals(arr: np.ndarray, sr: int, fps: int, n_frames: int, sub: int = 4):
    """Sinyal gerak mulut yang halus.

    Return (open, wide), keduanya 0..1 per frame:
    - open: seberapa terbuka mulut. Dianalisis 4x lebih rapat dari fps (agar suku kata cepat tertangkap),
      lalu diperhalus dengan attack cepat (~20 ms) & release lebih lambat (~90 ms) seperti gerak bibir asli.
    - wide: bentuk mulut dari 'warna' suara (spectral centroid): vokal i/e -> lebar & tipis,
      vokal o/u -> bulat & lebih tinggi.
    """
    rate = fps * sub
    n = n_frames * sub
    hop = sr / rate
    win = int(hop * 2)
    rms = np.zeros(n, np.float32)
    for i in range(n):
        seg = arr[int(i * hop): int(i * hop) + win]
        if len(seg):
            rms[i] = float(np.sqrt(np.mean(seg * seg)))
    if rms.max() < 1e-5:
        return np.zeros(n_frames, np.float32), np.full(n_frames, 0.5, np.float32)
    loud = rms[rms > rms.max() * 0.05]
    peak = float(np.percentile(loud, 90)) if len(loud) else float(rms.max())
    x = np.clip(rms / max(peak, 1e-6), 0, 1.3)
    x[x < 0.07] = 0.0                       # gerbang: senyap = mulut menutup
    x = np.minimum(x, 1.0) ** 0.6           # kompres dinamik supaya level tengah ikut terlihat
    a_att = 1 - np.exp(-1.0 / (rate * 0.020))
    a_rel = 1 - np.exp(-1.0 / (rate * 0.090))
    y = np.zeros(n, np.float32)
    s = 0.0
    for i in range(n):
        s += (a_att if x[i] > s else a_rel) * (x[i] - s)
        y[i] = s
    open_ = y.reshape(n_frames, sub).max(axis=1)
    open_ = np.convolve(np.pad(open_, 1, mode="edge"), [0.2, 0.6, 0.2], mode="valid").astype(np.float32)

    wide = np.full(n_frames, 0.5, np.float32)
    hann = np.hanning(1024).astype(np.float32)
    freqs = np.fft.rfftfreq(1024, 1.0 / sr)
    for i in range(n_frames):
        if open_[i] < 0.06:
            continue
        c = int((i + 0.5) / fps * sr)
        seg = arr[c - 512: c + 512]
        if len(seg) < 1024:
            continue
        mag = np.abs(np.fft.rfft(seg * hann))
        cen = float((freqs * mag).sum() / (mag.sum() + 1e-9))
        wide[i] = float(np.clip((cen - 500.0) / 2200.0, 0, 1))
    for _ in range(2):
        wide = np.convolve(np.pad(wide, 1, mode="edge"), [0.25, 0.5, 0.25], mode="valid").astype(np.float32)
    return np.clip(open_, 0, 1), wide
