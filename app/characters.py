"""Karakter avatar: gambar per emosi (mulut tertutup/terbuka), posisi mulut, suara default."""
import io
import shutil
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from . import config, db
from .writer import EMOTIONS

MOUTHS = ("closed", "open")
FALLBACK = {"serious": ["neutral"], "scared": ["surprised", "neutral"], "surprised": ["scared", "neutral"],
            "happy": ["neutral"], "sad": ["neutral"], "angry": ["serious", "neutral"], "neutral": []}

# Prompt siap pakai untuk membuat gambar karakter di AI generator gambar favorit
PROMPT_TIPS = {
    "base": ("Ubah foto ini menjadi avatar ilustrasi pembawa berita, setengah badan, menghadap kamera, "
             "latar polos/transparan, ekspresi netral, mulut tertutup, gaya konsisten."),
    "variant": ("Karakter yang SAMA persis (wajah, pakaian, gaya, posisi, latar), hanya ganti ekspresi: "
                "{emosi}, {mulut}."),
    "emotions": {"neutral": "ekspresi netral", "serious": "ekspresi serius, alis sedikit turun",
                 "sad": "ekspresi sedih, alis naik di tengah, mata sayu",
                 "angry": "ekspresi marah, alis turun menyatu", "scared": "ekspresi takut, mata melebar, alis naik",
                 "surprised": "ekspresi kaget, alis tinggi, mata lebar", "happy": "ekspresi senang, tersenyum"},
    "mouths": {"closed": "mulut tertutup", "open": "mulut terbuka sedang seperti sedang berbicara"},
}


def _dir(cid: int) -> Path:
    return config.CHAR_DIR / str(cid)


def image_path(cid: int, emotion: str, mouth: str) -> Optional[Path]:
    p = _dir(cid) / f"{emotion}_{mouth}.png"
    return p if p.exists() else None


def _with_images(row: dict) -> dict:
    cid = row["id"]
    imgs: Dict[str, Dict[str, bool]] = {}
    for e in EMOTIONS:
        imgs[e] = {m: image_path(cid, e, m) is not None for m in MOUTHS}
    row["images"] = imgs
    row["has_avatar"] = imgs["neutral"]["closed"]
    row["image_url"] = f"/media/characters/{cid}/neutral_closed.png" if row["has_avatar"] else None
    return row


def list_all() -> List[dict]:
    return [_with_images(r) for r in db.q_all("SELECT * FROM characters ORDER BY id")]


def get(cid: int) -> Optional[dict]:
    r = db.q_one("SELECT * FROM characters WHERE id=?", (cid,))
    return _with_images(r) if r else None


ALLOWED = {"name", "voice", "height_pct", "mouth_x", "mouth_y", "mouth_w", "frame_style", "notes"}


def create(data: dict) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Nama karakter wajib diisi")
    cid = db.execute("INSERT INTO characters (name, voice) VALUES (?,?)",
                     (name, data.get("voice") or "id-ID-ArdiNeural"))
    update(cid, {k: v for k, v in data.items() if k != "name"})
    return cid


def update(cid: int, data: dict):
    sets, vals = [], []
    for k, v in data.items():
        if k not in ALLOWED or v is None:
            continue
        if k in ("height_pct", "mouth_x", "mouth_y", "mouth_w"):
            v = float(v)
        if k == "height_pct":
            v = max(0.2, min(0.6, v))
        if k in ("mouth_x", "mouth_y", "mouth_w"):
            v = max(0.0, min(1.0, v))
        if k == "frame_style" and v not in ("none", "rounded", "circle"):
            v = "none"
        sets.append(f"{k}=?")
        vals.append(v)
    if sets:
        db.execute(f"UPDATE characters SET {', '.join(sets)} WHERE id=?", vals + [cid])


def delete(cid: int):
    db.execute("DELETE FROM characters WHERE id=?", (cid,))
    shutil.rmtree(_dir(cid), ignore_errors=True)


def _remove_flat_background(img: Image.Image) -> Image.Image:
    """Make an edge-connected near-white/neutral background fully transparent.
    Keeps interior white details because only pixels connected to the image border are removed.
    """
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    visited = bytearray(w * h)
    q = deque()
    tol = 42
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(1, h - 1):
        q.append((0, y)); q.append((w - 1, y))
    def bg_like(r, g, b, a):
        if a < 20:
            return True
        mx, mn = max(r, g, b), min(r, g, b)
        return mx >= 225 and (mx - mn) <= 28
    while q:
        x, y = q.popleft()
        i = y * w + x
        if visited[i]:
            continue
        visited[i] = 1
        r, g, b, a = px[x, y]
        if not bg_like(r, g, b, a):
            continue
        px[x, y] = (r, g, b, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                if not visited[j]:
                    nr, ng, nb, na = px[nx, ny]
                    if bg_like(nr, ng, nb, na) or max(abs(nr-r), abs(ng-g), abs(nb-b)) <= tol:
                        q.append((nx, ny))
    return img


def save_image(cid: int, emotion: str, mouth: str, data: bytes):
    if emotion not in EMOTIONS or mouth not in MOUTHS:
        raise ValueError("Emosi/mulut tidak valid")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError("File bukan gambar yang valid")
    img = _remove_flat_background(img.convert("RGBA"))
    if img.height > 1600:
        img = img.resize((int(img.width * 1600 / img.height), 1600), Image.LANCZOS)
    _dir(cid).mkdir(parents=True, exist_ok=True)
    img.save(_dir(cid) / f"{emotion}_{mouth}.png", "PNG")


def delete_image(cid: int, emotion: str, mouth: str):
    p = image_path(cid, emotion, mouth)
    if p:
        p.unlink()


def resolve_emotion(cid: int, emotion: str) -> Optional[str]:
    """Emosi gambar yang dipakai (dengan fallback). None bila karakter belum punya gambar netral."""
    for e in [emotion] + FALLBACK.get(emotion, ["neutral"]):
        if image_path(cid, e, "closed"):
            return e
    return "neutral" if image_path(cid, "neutral", "closed") else None
