"""Pilihan font untuk subtitle & judul: font sistem di container + font .ttf/.otf yang di-upload user."""
from pathlib import Path
from typing import List, Optional

from PIL import ImageFont

from . import config

_DJ = "/usr/share/fonts/truetype/dejavu/"
_LB = "/usr/share/fonts/truetype/liberation/"
_FR = "/usr/share/fonts/truetype/freefont/"

SYSTEM = [
    ("dejavu-bold", "DejaVu Sans Bold (tebal, jelas)", _DJ + "DejaVuSans-Bold.ttf"),
    ("dejavu-cond-bold", "DejaVu Sans Condensed Bold (ramping)", _DJ + "DejaVuSansCondensed-Bold.ttf"),
    ("dejavu-regular", "DejaVu Sans Regular (tipis)", _DJ + "DejaVuSans.ttf"),
    ("dejavu-serif-bold", "DejaVu Serif Bold (berkait)", _DJ + "DejaVuSerif-Bold.ttf"),
    ("dejavu-mono-bold", "DejaVu Mono Bold (mesin ketik)", _DJ + "DejaVuSansMono-Bold.ttf"),
    ("liberation-sans-bold", "Liberation Sans Bold (mirip Arial)", _LB + "LiberationSans-Bold.ttf"),
    ("liberation-serif-bold", "Liberation Serif Bold (mirip Times)", _LB + "LiberationSerif-Bold.ttf"),
    ("liberation-narrow-bold", "Liberation Narrow Bold (sempit)", _LB + "LiberationSansNarrow-Bold.ttf"),
    ("freesans-bold", "FreeSans Bold", _FR + "FreeSansBold.ttf"),
    ("freeserif-bold", "FreeSerif Bold", _FR + "FreeSerifBold.ttf"),
]
DEFAULT_ID = "dejavu-bold"
USER_PREFIX = "user:"


def font_dir() -> Path:
    d = config.DATA_DIR / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_fonts() -> List[dict]:
    out = [{"id": i, "label": label} for i, label, p in SYSTEM if Path(p).exists()]
    out += [{"id": USER_PREFIX + f.name, "label": f"{f.stem} (upload)"}
            for f in sorted(font_dir().glob("*")) if f.suffix.lower() in (".ttf", ".otf")]
    return out


def path_for(font_id: Optional[str]) -> Optional[str]:
    font_id = font_id or DEFAULT_ID
    if font_id.startswith(USER_PREFIX):
        p = font_dir() / Path(font_id[len(USER_PREFIX):]).name
        return str(p) if p.exists() else None
    for i, _, p in SYSTEM:
        if i == font_id and Path(p).exists():
            return p
    return None


def add_font(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in (".ttf", ".otf"):
        raise ValueError("Font harus berformat .ttf atau .otf")
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("File font terlalu besar (maks 15 MB)")
    safe = "".join(c for c in Path(filename).stem if c.isalnum() or c in "-_ ")[:60].strip() or "font"
    dest = font_dir() / (safe + ext)
    dest.write_bytes(data)
    try:
        ImageFont.truetype(str(dest), 24)
    except Exception:
        dest.unlink(missing_ok=True)
        raise ValueError("File font tidak valid / tidak bisa dibaca")
    return USER_PREFIX + dest.name
