"""Gambar latar scene dari AI gratis (Pollinations) / OpenAI / gradient offline. Hasil di-cache."""
import base64
import hashlib
import io
import random
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import numpy as np
import requests
from PIL import Image

from . import config

STYLE = (", cinematic dark moody illustration, dramatic lighting, vertical composition, "
         "no text, no watermark, no logo, no real person, no gore")

PROVIDERS = [
    {"id": "website", "label": "Screenshot website berita (sumber asli)"},
    {"id": "pollinations", "label": "AI gratis (Pollinations) - butuh internet"},
    {"id": "openai", "label": "OpenAI image (berbayar, pakai API key)"},
    {"id": "gradient", "label": "Gradient gelap (offline, tanpa gambar AI)"},
]

PALETTE = {  # emosi -> (atas, bawah)
    "neutral": ((18, 24, 38), (6, 8, 14)), "serious": ((22, 22, 34), (5, 5, 10)),
    "sad": ((14, 30, 58), (4, 8, 20)), "angry": ((70, 14, 14), (14, 3, 3)),
    "scared": ((10, 40, 36), (2, 10, 10)), "surprised": ((40, 30, 70), (8, 6, 18)),
    "happy": ((80, 56, 24), (20, 12, 6)),
}


def gradient_image(w: int, h: int, emotion: str = "neutral", seed: int = 0) -> Image.Image:
    top, bot = PALETTE.get(emotion, PALETTE["neutral"])
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t
    arr = np.repeat(arr, w, axis=1)
    rng = np.random.default_rng(seed)
    arr += rng.normal(0, 3.0, size=(h, w, 1)).astype(np.float32)  # grain halus
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _pollinations(prompt: str, w: int, h: int, seed: int) -> Image.Image:
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt + STYLE)}"
           f"?width={w}&height={h}&nologo=true&seed={seed}")
    r = requests.get(url, timeout=120, headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content))
    img.load()
    return img.convert("RGB")


def _website_screenshot(url: str, w: int, h: int) -> Image.Image:
    if not url:
        raise RuntimeError("URL berita tidak tersedia untuk screenshot website.")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright belum terpasang. Jalankan: pip install playwright && playwright install chromium") from e
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            shot = page.screenshot(type="jpeg", quality=90)
        finally:
            browser.close()
    return Image.open(io.BytesIO(shot)).convert("RGB")


def _openai(prompt: str) -> Image.Image:
    from .llm import _client
    r = _client().images.generate(model=config.OPENAI_IMAGE_MODEL, prompt=prompt + STYLE,
                                  size="1024x1536")
    return Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")


def scene_image(prompt: str, story_id: int, provider: str, emotion: str, idx: int,
                w: int = 720, h: int = 1280, log: Callable = lambda m, l="info": None,
                source_url: str = "") -> Image.Image:
    """Kembalikan PIL image untuk satu scene. Bila gagal -> gradient (dan dicatat di log)."""
    folder = config.MEDIA_DIR / f"story_{story_id}"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{provider}|{prompt}|{source_url}|{w}x{h}".encode()).hexdigest()[:16]
    cache = folder / f"img_{key}.jpg"
    if provider != "gradient" and prompt and cache.exists():
        try:
            return Image.open(cache).convert("RGB")
        except Exception:
            pass
    seed = int(key[:6], 16) % 100000
    if provider != "gradient" and prompt:
        for attempt in range(2):
            try:
                img = _website_screenshot(source_url, w, h) if provider == "website" else (_openai(prompt) if provider == "openai" else _pollinations(prompt, w, h, seed + attempt))
                img.save(cache, "JPEG", quality=90)
                return img
            except Exception as e:
                log(f"Gambar scene {idx + 1} gagal (percobaan {attempt + 1}): {str(e)[:120]}", "warning")
        log(f"Scene {idx + 1} memakai gradient sebagai pengganti.", "warning")
    if provider in ("openai", "pollinations", "website"):
        raise RuntimeError(f"Provider gambar '{provider}' gagal menghasilkan gambar setelah 2 percobaan.")
    return gradient_image(w, h, emotion, seed)
