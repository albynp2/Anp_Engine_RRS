"""Konfigurasi global Engine RRS (semua dari environment / .env)."""
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # dotenv opsional
    pass

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.getenv("APP_TZ", "Asia/Jakarta"))
except Exception:  # tzdata tidak ada -> WIB tetap (UTC+7)
    TZ = timezone(timedelta(hours=7))

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DB_PATH = DATA_DIR / "horror.db"
MEDIA_DIR = DATA_DIR / "media"          # gambar scene + narasi per story
CHAR_DIR = DATA_DIR / "characters"      # gambar avatar
MUSIC_DIR = DATA_DIR / "music"          # library musik
OUTPUT_DIR = DATA_DIR / "outputs"       # video hasil render
UPLOAD_DIR = DATA_DIR / "uploads"       # audio narasi hasil upload, watermark, dll
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", str(BASE_DIR / "frontend" / "dist")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip()
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "").strip()

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def ensure_dirs():
    for d in (DATA_DIR, MEDIA_DIR, CHAR_DIR, MUSIC_DIR, OUTPUT_DIR, UPLOAD_DIR):
        d.mkdir(parents=True, exist_ok=True)


def now_local() -> datetime:
    return datetime.now(TZ)


def today_local() -> date:
    return now_local().date()


def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def utc_str_to_local(ts: str):
    """'YYYY-MM-DD HH:MM:SS' (UTC dari SQLite) -> datetime lokal WIB. None kalau gagal."""
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).astimezone(TZ)
    except Exception:
        return None
