"""Renderer video vertikal: narasi (TTS/upload) -> timeline -> frame Pillow -> ffmpeg (+musik)."""
import bisect
import copy
import hashlib
import io
import math
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import audio, characters, config, db, fonts, images, music, tts
from .jobs import Cancelled, Job

# safe zone = area yang tertutup UI platform (caption, tombol like/share), dalam fraksi tinggi/lebar
PLATFORMS = {
    "facebook_reels": {"label": "Facebook Reels", "safe_top": 0.07, "safe_bottom": 0.20, "safe_side": 0.06},
    "youtube_shorts": {"label": "YouTube Shorts", "safe_top": 0.07, "safe_bottom": 0.19, "safe_side": 0.06},
    "tiktok": {"label": "TikTok", "safe_top": 0.08, "safe_bottom": 0.24, "safe_side": 0.12},
    "instagram_reels": {"label": "Instagram Reels", "safe_top": 0.09, "safe_bottom": 0.22, "safe_side": 0.07},
}

# Posisi/ukuran: persen dari lebar (x) / tinggi (y, size) video. None = otomatis (sesuai safe zone platform).
DEFAULT_OPTS = {
    "platforms": ["facebook_reels"], "characterId": None, "voiceMode": "tts", "voice": "",
    "musicId": None, "musicVolume": 12, "imageProvider": "pollinations", "maxImages": 8, "quality": "hd",
    "avatar": {"heightPct": None, "x": 50, "bottom": None},
    "subtitle": {"enabled": True, "font": "dejavu-bold", "size": 3.4, "color": "#ffffff",
                 "strokeColor": "#000000", "strokeWidth": 10, "box": False, "boxColor": "#000000",
                 "boxOpacity": 55, "uppercase": False, "x": 50, "y": None, "width": 88, "maxLines": 3},
    "headline": {"mode": "title", "text": "", "font": "dejavu-bold", "size": 3.0, "color": "#ffffff",
                 "strokeColor": "#000000", "strokeWidth": 0, "box": True, "boxColor": "#000000",
                 "boxOpacity": 60, "uppercase": False, "x": 50, "y": None, "width": 86, "maxLines": 3},
    "watermarkText": "", "watermarkOpacity": 30, "watermarkPosition": "top-right", "watermarkImagePath": "",
    "newsSource": {"enabled": True, "mode": "script", "source": "", "date": "", "position": "bottom-left",
                   "color": "#ffffff", "strokeColor": "#000000", "strokeWidth": 8, "size": 2.0},
}
NESTED = ("avatar", "subtitle", "headline")
QUALITY = {"hd": (1080, 1920, 30), "draft": (540, 960, 24)}

EMO_TINT = {"neutral": (0, 0, 0, 0), "serious": (10, 10, 24, 40), "sad": (30, 60, 120, 75),
            "angry": (160, 20, 20, 70), "scared": (10, 50, 38, 80), "surprised": (40, 30, 80, 40),
            "happy": (255, 190, 80, 38)}


def ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None


def num(v, default=None):
    """Angka dari input (bisa None / '' / string). None/'' -> default."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def rgba(hexs: str, alpha: int = 255):
    h = (hexs or "#ffffff").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha
    except ValueError:
        return 255, 255, 255, alpha


# ------------------------------------------------------------------ font & teks
_font_cache: Dict[tuple, ImageFont.FreeTypeFont] = {}


def font(size: int, font_id: Optional[str] = None):
    size = max(8, int(size))
    key = (font_id or fonts.DEFAULT_ID, size)
    if key not in _font_cache:
        path = fonts.path_for(font_id) or fonts.path_for(fonts.DEFAULT_ID)
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except Exception:
            _font_cache[key] = ImageFont.load_default(size=size)
    return _font_cache[key]


def wrap(text: str, f, max_w: int) -> List[str]:
    d = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def text_layer(text: str, size: int, max_w: int, st: dict, max_lines: int = 3) -> Image.Image:
    """Teks jadi gambar RGBA sesuai gaya: font, warna, outline (% ukuran font), kotak latar + opacity."""
    if st.get("uppercase"):
        text = text.upper()
    f = font(size, st.get("font"))
    stroke = int(size * max(0.0, num(st.get("strokeWidth"), 0)) / 100)
    lines = wrap(text, f, max_w)[:max(1, int(num(max_lines, 3)))]
    d0 = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    lh = int(size * 1.22)
    pad = max(10, int(size * 0.35)) if st.get("box") else 6
    w = int(max(d0.textlength(l, font=f) for l in lines)) + 2 * (stroke + pad)
    h = lh * len(lines) + 2 * (stroke + pad) - int(size * 0.1)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if st.get("box"):
        op = int(255 * max(0, min(100, num(st.get("boxOpacity"), 55))) / 100)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(size * 0.45), fill=rgba(st.get("boxColor"), op))
    fill, sfill = rgba(st.get("color")), rgba(st.get("strokeColor"))
    for i, l in enumerate(lines):
        lw = d.textlength(l, font=f)
        d.text(((w - lw) / 2, stroke + pad + i * lh), l, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill)
    return img


def chunk_text(text: str, max_chars: int = 30) -> List[str]:
    chunks, cur = [], []
    for w in text.split():
        cur.append(w)
        s = " ".join(cur)
        if len(s) >= max_chars or (w[-1] in ".!?,;:" and len(s) >= 14):
            chunks.append(s)
            cur = []
    if cur:
        s = " ".join(cur)
        if chunks and len(s) < 9:
            chunks[-1] += " " + s
        else:
            chunks.append(s)
    return chunks


# ------------------------------------------------------------------ avatar
def _style_sprite(img: Image.Image, style: str, mx: float, my: float, mw: float):
    w, h = img.size
    if style == "circle":
        side = min(w, h)
        x0 = (w - side) // 2
        img = img.crop((x0, 0, x0 + side, side))
        mx, my, mw = (mx * w - x0) / side, my * h / side, mw * w / side
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, side - 1, side - 1], fill=255)
        img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", img.size, 0), mask))
    elif style == "rounded":
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(min(w, h) * 0.08), fill=255)
        img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", img.size, 0), mask))
    return img, mx, my, mw


def draw_mouth(img: Image.Image, cx: float, cy: float, mwid: float, openness: float, wide: float) -> Image.Image:
    """Mulut elips untuk avatar tanpa gambar 'mulut terbuka'. openness 0..1 (tinggi), wide 0..1 (bentuk vokal)."""
    img = img.copy()
    mw_ = max(6.0, mwid * (0.85 + 0.35 * wide))                          # i/e -> lebih lebar
    mh = max(2.0, mwid * (0.05 + 0.52 * openness) * (1.2 - 0.4 * wide))  # o/u -> lebih tinggi & bulat
    S = 4
    bw, bh = int(mw_ * 1.5) + 4, int(mh * 2) + 6
    layer = Image.new("RGBA", (bw * S, bh * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ex0, ey0 = (bw * S - mw_ * S) / 2, (bh * S - mh * S) / 2
    d.ellipse([ex0, ey0, ex0 + mw_ * S, ey0 + mh * S], fill=(48, 10, 16, 240),
              outline=(140, 56, 66, 255), width=S * 2)
    if openness > 0.55:
        d.ellipse([ex0 + mw_ * S * 0.22, ey0 + mh * S * 0.5, ex0 + mw_ * S * 0.78, ey0 + mh * S * 0.92],
                  fill=(170, 70, 82, 235))
    layer = layer.resize((bw, bh), Image.LANCZOS)
    img.paste(layer, (int(cx - bw / 2), int(cy - bh / 2)), layer)
    return img


class Sprites:
    """Sprite avatar per emosi. Mulut: blend halus closed<->open (bila ada gambar mulut terbuka)
    atau mulut elips prosedural 9 tingkat x 3 bentuk. Diberi margin transparan agar bisa dimiringkan."""

    def __init__(self, char: dict, target_h: int, max_w: int):
        self.char, self.target_h, self.max_w = char, target_h, max_w
        self.base: Dict[str, dict] = {}
        self.cache: Dict[tuple, Image.Image] = {}

    def _load(self, cid: int, emo: str, mouth: str):
        p = characters.image_path(cid, emo, mouth)
        if not p:
            return None
        c = self.char
        img, mx, my, mw = _style_sprite(Image.open(p).convert("RGBA"), c["frame_style"],
                                        c["mouth_x"], c["mouth_y"], c["mouth_w"])
        s = min(self.target_h / img.height, self.max_w / img.width)
        w, h = max(1, int(img.width * s)), max(1, int(img.height * s))
        img = img.resize((w, h), Image.LANCZOS)
        pad = int(0.07 * max(w, h))
        canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        canvas.paste(img, (pad, pad))
        return canvas, (mx * w + pad, my * h + pad, mw * w), pad

    def _entry(self, emotion: str):
        used = characters.resolve_emotion(self.char["id"], emotion)
        if used is None:
            return None, None
        if used not in self.base:
            closed = self._load(self.char["id"], used, "closed")
            opened = self._load(self.char["id"], used, "open")
            op_img = None
            if opened:
                op_img = opened[0] if opened[0].size == closed[0].size else opened[0].resize(closed[0].size, Image.LANCZOS)
            self.base[used] = {"closed": closed[0], "open": op_img, "m": closed[1], "pad": closed[2]}
        return used, self.base[used]

    def get(self, emotion: str, openness: float, wide: float, angle: float):
        used, e = self._entry(emotion)
        if e is None:
            return None, 0
        if e["open"] is not None:
            q = int(round(max(0.0, min(1.0, openness)) * 6))
            key = (used, "b", q)
            if key not in self.cache:
                self.cache[key] = e["closed"] if q == 0 else Image.blend(e["closed"], e["open"], q / 6)
        else:
            qo, qw = int(round(max(0.0, min(1.0, openness)) * 8)), int(round(max(0.0, min(1.0, wide)) * 2))
            key = (used, "p", qo, qw)
            if key not in self.cache:
                cx, cy, mw = e["m"]
                self.cache[key] = e["closed"] if qo == 0 else draw_mouth(e["closed"], cx, cy, mw, qo / 8, qw / 2)
        img = self.cache[key]
        if abs(angle) > 0.05:
            img = img.rotate(angle, Image.BICUBIC, center=(img.width / 2, img.height - e["pad"]))
        return img, e["pad"]


def motion(emo: str, t: float, lvl: float, k: float):
    """(dx, dy, sudut) gerak kepala/badan: bernapas + goyang halus + anggukan mengikuti energi suara + emosi."""
    ang = 0.9 * math.sin(2 * math.pi * 0.21 * t + 0.5) + 0.5 * math.sin(2 * math.pi * 0.53 * t + 1.3)
    dx = k * 2.5 * math.sin(2 * math.pi * 0.17 * t)
    dy = k * 3 * math.sin(2 * math.pi * 0.30 * t) - k * lvl * 5
    if emo == "sad":
        dy += k * 10
        ang += 1.4
    elif emo == "angry":
        dx += k * 2.5 * math.sin(t * 37)
        dy -= k * lvl * 5
        ang += 0.6 * math.sin(t * 23)
    elif emo == "scared":
        dx += k * 4 * math.sin(t * 45)
        dy += k * 3 * math.sin(t * 31)
        ang += 1.0 * math.sin(t * 29)
    elif emo == "surprised":
        dy -= k * (6 + lvl * 4)
    elif emo == "happy":
        dy -= k * abs(math.sin(2 * math.pi * 1.8 * t)) * (3 + 6 * lvl)
    return dx, dy, ang


# ------------------------------------------------------------------ composer
class Scene:
    def __init__(self, idx, start, end, sp0, sp1, emotion, text, img, W, H):
        self.idx, self.start, self.end, self.sp0, self.sp1 = idx, start, end, sp0, sp1
        self.emotion, self.text = emotion, text
        s = max(W / img.width, H / img.height)
        self.cover = img.resize((max(W, int(img.width * s)), max(H, int(img.height * s))), Image.LANCZOS)
        self.dir = 1 if idx % 2 == 0 else -1
        self.pan = (-1) ** (idx // 2)
        self.chunks: List[tuple] = []  # (t0, t1, layer, x, y)


class Composer:
    def __init__(self, W, H, fps, platform: str, opts: dict, scenes: List[Scene],
                 env: Tuple[np.ndarray, np.ndarray], char: Optional[dict], title: str):
        self.W, self.H, self.fps, self.opts, self.scenes = W, H, fps, opts, scenes
        self.open, self.wide = env
        self.k = H / 1920.0
        pf = PLATFORMS[platform]
        self.pf = pf
        self.starts = [s.start for s in scenes]
        self.overlays: Dict[str, Image.Image] = {}
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        vig = np.clip((r - 0.55) / 0.9, 0, 1) ** 1.5 * 150
        bot = np.clip((yy / H - 0.55) / 0.45, 0, 1) ** 1.3 * 130
        self._dark = np.maximum(vig, bot).astype(np.uint8)

        safe_b = int(H * (1 - pf["safe_bottom"]))
        # --- avatar: ukuran & posisi bisa diatur
        av = opts["avatar"]
        self.char, self.sprites = char, None
        if char:
            h_pct = num(av.get("heightPct"), None)
            h_pct = h_pct / 100.0 if h_pct else char["height_pct"]
            h_pct = max(0.10, min(1.0, h_pct))
            self.av_h = int(H * h_pct)
            self.av_cx = int(W * num(av.get("x"), 50) / 100)
            bottom = num(av.get("bottom"), None)
            self.av_bottom = int(H * bottom / 100) if bottom is not None else safe_b + int(0.03 * H)
            self.sprites = Sprites(char, self.av_h, int(W * 0.98))
            auto_sub_bottom = self.av_bottom - self.av_h - int(0.012 * H)
        else:
            auto_sub_bottom = safe_b - int(0.02 * H)

        # --- subtitle
        sb = opts["subtitle"]
        if sb.get("enabled", True):
            size = int(H * num(sb.get("size"), 3.4) / 100)
            sub_w = int(W * num(sb.get("width"), 88) / 100)
            cx = W * num(sb.get("x"), 50) / 100
            ycen = num(sb.get("y"), None)
            cpl = sub_w / (size * 0.60)
            max_chars = max(14, int(cpl * 1.6))
            for sc in scenes:
                chs = chunk_text(sc.text, max_chars)
                tot = sum(len(c) for c in chs) or 1
                t = sc.sp0
                for c in chs:
                    d = max(0.3, (sc.sp1 - sc.sp0) * len(c) / tot)
                    layer = text_layer(c, size, sub_w, sb, sb.get("maxLines", 3))
                    x = int(min(max(0, cx - layer.width / 2), W - layer.width))
                    y = int(H * ycen / 100 - layer.height / 2) if ycen is not None else int(auto_sub_bottom - layer.height)
                    sc.chunks.append((t, t + d, layer, x, y))
                    t += d

        # --- judul di atas video
        self.head = None
        hd = opts["headline"]
        htxt = title if hd.get("mode", "title") == "title" else (hd.get("text") or "")
        if hd.get("mode", "title") != "none" and htxt.strip():
            size = int(H * num(hd.get("size"), 3.0) / 100)
            layer = text_layer(htxt.strip()[:140], size, int(W * num(hd.get("width"), 86) / 100), hd, hd.get("maxLines", 3))
            ycen = num(hd.get("y"), None)
            x = int(min(max(0, W * num(hd.get("x"), 50) / 100 - layer.width / 2), W - layer.width))
            y = int(H * ycen / 100 - layer.height / 2) if ycen is not None else int(H * pf["safe_top"])
            self.head = (layer, x, y)

        self.wm = self._watermark(opts)
        self.news_source = self._news_source(opts)

    def _watermark(self, o):
        op = max(0, min(100, int(num(o.get("watermarkOpacity"), 30)))) / 100
        layer = None
        pth = o.get("watermarkImagePath")
        if pth and Path(pth).exists():
            im = Image.open(pth).convert("RGBA")
            w = int(self.W * 0.24)
            layer = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
        elif (o.get("watermarkText") or "").strip():
            layer = text_layer(o["watermarkText"].strip()[:40], int(self.H * 0.026), int(self.W * 0.6),
                               {"color": "#ffffff", "strokeColor": "#000000", "strokeWidth": 8}, 1)
        if layer is None:
            return None
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * op)))
        m, pos = int(self.W * 0.04), o.get("watermarkPosition", "top-right")
        lw, lh = layer.size
        top = int(self.H * self.pf["safe_top"]) + int(self.H * 0.09)
        bottom = int(self.H * (1 - self.pf["safe_bottom"])) - lh - m
        xy = {"top-right": (self.W - lw - m, top), "top-left": (m, top),
              "center": ((self.W - lw) // 2, (self.H - lh) // 2),
              "bottom-left": (m, bottom), "bottom-right": (self.W - lw - m, bottom)}
        return layer, xy.get(pos, xy["top-right"])

    def _news_source(self, o):
        ns = o.get("newsSource") or {}
        if not ns.get("enabled", True):
            return None
        source = (ns.get("source") or "").strip()
        date = (ns.get("date") or "").strip()
        if not source and not date:
            return None
        parts = []
        if source:
            parts.append(f"Sumber: {source[:80]}")
        if date:
            parts.append(f"Terbit: {date[:40]}")
        text = "\n".join(parts)
        size = max(12, int(self.H * num(ns.get("size"), 2.0) / 100))
        layer = text_layer(text, size, int(self.W * 0.62),
                           {"color": ns.get("color", "#ffffff"),
                            "strokeColor": ns.get("strokeColor", "#000000"),
                            "strokeWidth": ns.get("strokeWidth", 8),
                            "box": True, "boxColor": "#000000", "boxOpacity": 45,
                            "uppercase": False}, 2)
        m = int(self.W * 0.04)
        pos = ns.get("position", "bottom-left")
        safe_top = int(self.H * self.pf["safe_top"]) + m
        safe_bottom = int(self.H * (1 - self.pf["safe_bottom"])) - layer.height - m
        xy = {
            "top-left": (m, safe_top),
            "top-center": ((self.W - layer.width) // 2, safe_top),
            "top-right": (self.W - layer.width - m, safe_top),
            "bottom-left": (m, safe_bottom),
            "bottom-center": ((self.W - layer.width) // 2, safe_bottom),
            "bottom-right": (self.W - layer.width - m, safe_bottom),
        }
        return layer, xy.get(pos, xy["bottom-left"])

    def overlay(self, emo: str) -> Image.Image:
        if emo not in self.overlays:
            tint = Image.new("RGBA", (self.W, self.H), EMO_TINT.get(emo, EMO_TINT["neutral"]))
            dark = np.zeros((self.H, self.W, 4), np.uint8)
            dark[..., 3] = self._dark
            self.overlays[emo] = Image.alpha_composite(tint, Image.fromarray(dark, "RGBA"))
        return self.overlays[emo]

    def _bg(self, sc: Scene, t: float) -> Image.Image:
        p = min(1.0, max(0.0, (t - sc.start) / max(0.1, sc.end - sc.start)))
        z = 1.0 + 0.10 * (p if sc.dir > 0 else 1 - p)
        cw, ch = sc.cover.size
        bw, bh = self.W / z, self.H / z
        x0 = min(max(0.0, cw / 2 + (p - 0.5) * sc.pan * (cw - bw) - bw / 2), cw - bw)
        y0 = min(max(0.0, ch / 2 - bh / 2), ch - bh)
        return sc.cover.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + bw, y0 + bh))

    def frame(self, i: int) -> Image.Image:
        t = i / self.fps
        si = max(0, bisect.bisect_right(self.starts, t) - 1)
        sc = self.scenes[si]
        bg = self._bg(sc, t)
        xf = 0.35
        if si > 0 and t - sc.start < xf:
            bg = Image.blend(self._bg(self.scenes[si - 1], t), bg, (t - sc.start) / xf)
        ov = self.overlay(sc.emotion)
        bg.paste(ov, (0, 0), ov)

        j = min(i, len(self.open) - 1)
        lvl = float(self.open[j]) if len(self.open) else 0.0
        wd = float(self.wide[j]) if len(self.wide) else 0.5
        if self.sprites:
            dx, dy, ang = motion(sc.emotion, t, lvl, self.k)
            spr, pad = self.sprites.get(sc.emotion, lvl, wd, ang)
            if spr is not None:
                x = int(self.av_cx - spr.width / 2 + dx)
                y = int(self.av_bottom - (spr.height - pad) + dy)
                bg.paste(spr, (x, y), spr)

        if self.head:
            bg.paste(self.head[0], (self.head[1], self.head[2]), self.head[0])
        if self.wm:
            bg.paste(self.wm[0], self.wm[1], self.wm[0])
        if self.news_source:
            bg.paste(self.news_source[0], self.news_source[1], self.news_source[0])
        for t0, t1, layer, x, y in sc.chunks:
            if t0 <= t < t1 + 0.05:
                bg.paste(layer, (x, y), layer)
                break
        return bg


# ------------------------------------------------------------------ aset per story
def _find_upload(story_id: int) -> Optional[Path]:
    hits = sorted(config.UPLOAD_DIR.glob(f"story_{story_id}_narration.*"))
    return hits[0] if hits else None


def prepare_assets(job: Job, story: dict, script: dict, opts: dict, char: Optional[dict],
                   W: int, H: int, fps: int, progress: Callable[[float, str], None]) -> dict:
    segs = script["segments"]
    sid = story["id"] if "id" in story else script["story_id"]
    texts = [s["text"] for s in segs]
    if opts["voiceMode"] == "upload":
        up = _find_upload(sid)
        if not up:
            raise RuntimeError("Audio narasi belum diupload untuk naskah ini (menu Content Management).")
        progress(0.1, "Membaca audio upload")
        arr = audio.decode(up)
        total = len(arr) / audio.SR
        pb = audio.proportional_bounds(texts, total)
        inner = audio.snap_to_silence(arr, audio.SR, pb[1:-1])
        for j in range(1, len(inner)):  # pastikan urut naik
            inner[j] = max(inner[j], inner[j - 1] + 0.3)
        b = [pb[0]] + inner + [pb[-1]]
        times = [(b[j], b[j + 1]) for j in range(len(segs))]
        starts = [0.0] + [b[j] for j in range(1, len(segs))]
        ends = starts[1:] + [total]
    else:
        voice = opts.get("voice") or (char or {}).get("voice") or tts.VOICES[0]["id"]
        chunks = []
        for j, s in enumerate(segs):
            job.check_cancel()
            progress(0.05 + 0.4 * j / len(segs), f"Suara narasi {j + 1}/{len(segs)}")
            chunks.append(audio.decode(tts.synth(s["text"], voice, s["emotion"])))
        arr, times = audio.concat(chunks)
        total = len(arr) / audio.SR
        starts = [0.0] + [times[j][0] for j in range(1, len(segs))]
        ends = starts[1:] + [total]

    folder = config.MEDIA_DIR / f"story_{sid}"
    folder.mkdir(parents=True, exist_ok=True)
    wav = folder / f"narration_{hashlib.sha1(arr[:48000].tobytes()).hexdigest()[:8]}_{int(total * 10)}.wav"
    audio.write_wav(wav, arr)

    # gambar scene (dikelompokkan agar jumlah gambar <= maxImages)
    n, mx = len(segs), max(1, int(num(opts.get("maxImages"), 8)))
    group = [min(mx - 1, int(j * mx / n)) for j in range(n)] if n > mx else list(range(n))
    imgs: Dict[int, Image.Image] = {}
    for j, g in enumerate(group):
        if g in imgs:
            continue
        job.check_cancel()
        progress(0.45 + 0.5 * len(imgs) / len(set(group)), f"Gambar scene {len(imgs) + 1}/{len(set(group))}")
        prompt = segs[j].get("image_prompt") or "dark empty street at night, fog, cinematic"
        imgs[g] = images.scene_image(prompt, sid, opts["imageProvider"], segs[j]["emotion"], g,
                                     w=min(W, 720), h=min(H, 1280), log=job.log)
    total_frames = int(math.ceil(total * fps))
    env = audio.mouth_signals(arr, audio.SR, fps, total_frames)
    return {"wav": wav, "total": total, "times": times, "starts": starts, "ends": ends, "group": group,
            "imgs": imgs, "env": env, "frames": total_frames}


def build_scenes(segs, a, W, H) -> List[Scene]:
    return [Scene(j, a["starts"][j], a["ends"][j], a["times"][j][0], a["times"][j][1], segs[j]["emotion"],
                  segs[j]["text"], a["imgs"][a["group"][j]], W, H) for j in range(len(segs))]


# ------------------------------------------------------------------ ffmpeg
def encode(comp: Composer, a: dict, out: Path, fps: int, music_path: Optional[Path], music_vol: float,
           job: Job, on_frac: Callable[[float], None]):
    W, H, total = comp.W, comp.H, a["total"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-i", str(a["wav"])]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        fo = max(0.0, total - 2.5)
        fc = ("[1:a]aresample=44100[n];"
              f"[2:a]aresample=44100,volume={music_vol:.3f},afade=t=in:st=0:d=1.5,"
              f"afade=t=out:st={fo:.2f}:d=2.5[m];[n][m]amix=inputs=2:duration=first:normalize=0[a]")
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = a["frames"]
    try:
        for i in range(n):
            if i % 15 == 0:
                job.check_cancel()
                on_frac(i / n)
            proc.stdin.write(comp.frame(i).tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode("utf8", "ignore")
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg gagal: " + err[-400:])
    except BrokenPipeError:
        raise RuntimeError("ffmpeg berhenti: " + proc.stderr.read().decode("utf8", "ignore")[-400:])
    except BaseException:
        proc.kill()
        raise


# ------------------------------------------------------------------ job
def merge_opts(p: dict) -> dict:
    o = copy.deepcopy(DEFAULT_OPTS)
    for k, v in p.items():
        if k in NESTED:
            if isinstance(v, dict):
                o[k].update({kk: vv for kk, vv in v.items() if kk in DEFAULT_OPTS[k]})
        elif k in DEFAULT_OPTS and v is not None:
            o[k] = v
    o["platforms"] = [x for x in (o.get("platforms") or []) if x in PLATFORMS] or ["facebook_reels"]
    return o


def run_render(job: Job, p: dict) -> dict:
    if not ffmpeg_ok():
        raise RuntimeError("ffmpeg tidak ditemukan.")
    ids = [int(x) for x in p.get("storyIds", [])]
    if not ids:
        raise ValueError("Pilih minimal satu naskah.")
    opts = merge_opts(p)
    W, H, fps = QUALITY.get(opts["quality"], QUALITY["hd"])
    char = characters.get(int(opts["characterId"])) if opts.get("characterId") else None
    if char and not char["has_avatar"]:
        raise ValueError(f"Karakter '{char['name']}' belum punya gambar 'netral - mulut tertutup'.")
    if not char:
        job.log("Tanpa karakter: video hanya gambar + subtitle + suara.", "warning")
    mpath = music.get_path(opts.get("musicId"))
    mvol = max(0, min(100, float(opts["musicVolume"]))) / 100

    done, failed = [], []
    plats = opts["platforms"]
    for k, sid in enumerate(ids):
        base, share = 100 * k / len(ids), 100 / len(ids)
        script = db.get_script(sid)
        if not script:
            failed.append({"id": sid, "reason": "naskah belum ada"})
            continue
        script["story_id"] = sid
        label = (script["title"] or "")[:50]

        def prog(frac, stage, base=base, share=share, lo=0.0, hi=0.35):
            job.set_progress(base + share * (lo + (hi - lo) * frac), f"[{k + 1}/{len(ids)}] {stage}")

        try:
            story_opts = copy.deepcopy(opts)
            ns = copy.deepcopy(story_opts.get("newsSource") or {})
            if ns.get("mode", "script") == "script":
                ns["source"] = script.get("source") or script.get("news_source") or ""
                ns["date"] = (script.get("published_date") or script.get("published") or "")[:10]
            story_opts["newsSource"] = ns
            a = prepare_assets(job, {"id": sid}, script, story_opts, char, W, H, fps, prog)
        except Cancelled:
            raise
        except Exception as e:
            failed.append({"id": sid, "reason": str(e)[:250]})
            job.log(f"Gagal menyiapkan '{label}': {e}", "error")
            continue
        job.log(f"'{label}': narasi {a['total']:.1f} dtk, {len(a['imgs'])} gambar")
        scenes = build_scenes(script["segments"], a, W, H)
        for pi, plat in enumerate(plats):
            vid = db.create_video(sid, plat, char["id"] if char else None, opts)
            out = config.OUTPUT_DIR / f"{sid}_{plat}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
            lo = 0.35 + 0.65 * pi / len(plats)
            hi = 0.35 + 0.65 * (pi + 1) / len(plats)
            try:
                comp = Composer(W, H, fps, plat, story_opts, scenes, a["env"], char, script["title"] or "")
                encode(comp, a, out, fps, mpath, mvol, job,
                       lambda f, plat=plat, lo=lo, hi=hi: prog(f, f"Render {PLATFORMS[plat]['label']}", lo=lo, hi=hi))
                db.finish_video(vid, True, out.name, a["total"])
                done.append({"storyId": sid, "platform": plat, "file": out.name})
                job.log(f"Selesai: {out.name}")
            except Cancelled:
                db.finish_video(vid, False, error="Dibatalkan")
                out.unlink(missing_ok=True)
                raise
            except Exception as e:
                db.finish_video(vid, False, error=str(e)[:300])
                out.unlink(missing_ok=True)
                failed.append({"id": sid, "reason": f"{plat}: {str(e)[:200]}"})
                job.log(f"Render {plat} gagal: {e}", "error")
    return {"videos": done, "failed": failed}


# ------------------------------------------------------------------ preview 1 frame
def render_preview(p: dict) -> bytes:
    opts = merge_opts(p)
    W, H, fps = QUALITY["draft"]
    plat = opts["platforms"][0]
    char = characters.get(int(opts["characterId"])) if opts.get("characterId") else None
    emo = p.get("emotion") if p.get("emotion") in tts.PROSODY else "neutral"
    text = p.get("text") or "Contoh subtitle: warga mengaku melihat sosok misterius di dekat jembatan."
    img = images.gradient_image(720, 1280, emo, 1)
    sc = Scene(0, 0.0, 4.0, 0.0, 4.0, emo, text, img, W, H)
    env = (np.array([float(p.get("level", 0.8))], np.float32), np.array([0.5], np.float32))
    comp = Composer(W, H, fps, plat, opts, [sc], env, char, p.get("title") or "Judul berita akan tampil di sini")
    buf = io.BytesIO()
    comp.frame(int(0.5 * fps)).save(buf, "PNG")
    return buf.getvalue()
