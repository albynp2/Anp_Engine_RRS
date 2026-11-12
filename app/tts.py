"""TTS gratis lokal via edge-tts. Prosodi (tempo/nada/volume) disesuaikan dengan emosi segmen."""
import asyncio
import hashlib
import time
from pathlib import Path

from . import config

VOICES = [
    {"id": "id-ID-ArdiNeural", "label": "Ardi (pria, Indonesia)"},
    {"id": "id-ID-GadisNeural", "label": "Gadis (wanita, Indonesia)"},
]

# emosi -> (rate, pitch, volume)
PROSODY = {
    "neutral": ("+0%", "+0Hz", "+0%"),
    "serious": ("-6%", "-2Hz", "+0%"),
    "sad": ("-14%", "-5Hz", "-6%"),
    "angry": ("+8%", "+2Hz", "+15%"),
    "scared": ("+6%", "+3Hz", "-4%"),
    "surprised": ("+6%", "+6Hz", "+8%"),
    "happy": ("+6%", "+4Hz", "+8%"),
}


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False


async def _save(text, voice, rate, pitch, volume, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume).save(str(path))


def synth(text: str, voice: str, emotion: str = "neutral", retries: int = 3) -> Path:
    """Hasilkan mp3 untuk satu segmen. Hasil di-cache menurut (teks, suara, emosi)."""
    rate, pitch, volume = PROSODY.get(emotion, PROSODY["neutral"])
    cache = config.MEDIA_DIR / "tts_cache"
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{volume}|{text}".encode()).hexdigest()[:20]
    out = cache / f"{key}.mp3"
    if out.exists() and out.stat().st_size > 1000:
        return out
    if not available():
        raise RuntimeError("Paket edge-tts belum terpasang di container.")
    last = None
    for i in range(retries):
        try:
            asyncio.run(_save(text, voice, rate, pitch, volume, out))
            if out.exists() and out.stat().st_size > 1000:
                return out
        except Exception as e:  # jaringan putus, dll
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"edge-tts gagal (butuh internet): {last}")
