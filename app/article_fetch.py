"""Ambil isi artikel asli supaya AI menulis naskah dari fakta, bukan dari judul saja."""
import base64
import json
import re
from typing import List, Optional, Tuple
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from . import config, db

MIN_CHARS = 400
MAX_CHARS = 6000
BOILER = ("baca juga", "baca:", "simak", "ikuti", "advertisement", "scroll to", "copyright",
          "lihat juga", "klik di sini", "berita terkait", "follow", "subscribe", "iklan",
          "baca selengkapnya", "(adv)", "sumber:", "editor:", "penulis:", "reporter:")


# ------------------------------------------------------------------ decode link Google News
def _gid(url: str) -> Optional[str]:
    u = urlparse(url)
    parts = [p for p in u.path.split("/") if p]
    if u.hostname == "news.google.com" and len(parts) >= 2 and parts[-2] in ("articles", "read"):
        return parts[-1]
    return None


def _decode_old_style(gid: str) -> Optional[str]:
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4))
    except Exception:
        return None
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    return m.group(0).decode("ascii", "ignore") if m else None


def _decode_new_style(gid: str, s: requests.Session) -> Optional[str]:
    """Metode batchexecute (format ID baru Google News). Belum bisa dites offline."""
    sig = ts = None
    for base in (f"https://news.google.com/articles/{gid}",
                 f"https://news.google.com/rss/articles/{gid}"):
        try:
            r = s.get(base, timeout=20, headers={"User-Agent": config.USER_AGENT})
            node = BeautifulSoup(r.text, "html.parser").find(attrs={"data-n-a-sg": True})
            if node:
                sig, ts = node.get("data-n-a-sg"), node.get("data-n-a-ts")
                break
        except Exception:
            continue
    if not sig:
        return None
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,'
             f'null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts},"{sig}"]')
    body = "f.req=" + quote(json.dumps([[["Fbv4je", inner]]]))
    try:
        r = s.post("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body, timeout=20,
                   headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                            "User-Agent": config.USER_AGENT})
        data = json.loads(r.text.split("\n\n")[1])[:-2]
        return json.loads(data[0][2])[1]
    except Exception:
        return None


def resolve_url(url: str, s: Optional[requests.Session] = None) -> str:
    s = s or requests.Session()
    gid = _gid(url)
    if not gid:
        return url
    return _decode_old_style(gid) or _decode_new_style(gid, s) or url


# ------------------------------------------------------------------ ekstraksi teks
def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    meta_desc = ""
    for sel in ({"property": "og:description"}, {"name": "description"}):
        m = soup.find("meta", attrs=sel)
        if m and m.get("content"):
            meta_desc = m["content"].strip()
            break
    for t in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript",
                   "iframe", "figure", "figcaption", "button"]):
        t.decompose()

    best, best_len = None, 0
    for cont in soup.find_all(["article", "main", "div", "section"]):
        ps = cont.find_all("p", recursive=False)
        n = sum(len(p.get_text(" ", strip=True)) for p in ps if len(p.get_text(strip=True)) >= 40)
        if n > best_len:
            best, best_len = cont, n
    ps = best.find_all("p", recursive=False) if best is not None and best_len > 200 else soup.find_all("p")

    paras, seen = [], set()
    for p in ps:
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        low = t.lower()
        if len(t) < 40 or low.startswith(BOILER) or low in seen:
            continue
        seen.add(low)
        paras.append(t)
    text = "\n".join(paras)
    if len(text) < MIN_CHARS and meta_desc and meta_desc not in text:
        text = (meta_desc + "\n" + text).strip()
    return cut(text)


def cut(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    chunk = text[:limit]
    end = max(chunk.rfind(". "), chunk.rfind("\n"))
    return chunk[: end + 1] if end > limit * 0.6 else chunk


def fetch_text(url: str, s: requests.Session) -> Tuple[str, str]:
    real = resolve_url(url, s)
    if "news.google.com" in (urlparse(real).hostname or ""):
        return real, ""  # gagal di-decode
    r = s.get(real, timeout=25, headers={"User-Agent": config.USER_AGENT, "Accept-Language": "id,en;q=0.8"})
    r.raise_for_status()
    if "text/html" not in r.headers.get("content-type", "text/html"):
        return real, ""
    r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
    return real, extract_text(r.text)


# ------------------------------------------------------------------ untuk satu story
def ensure_content(story: dict, log=lambda m, l="info": None) -> Tuple[bool, str]:
    """Pastikan story punya isi artikel. Return (ok, pesan). Isi disimpan di DB (kolom content)."""
    if story.get("content") and len(story["content"]) >= MIN_CHARS:
        return True, "isi sudah ada"
    urls: List[str] = [story["url"]]
    try:
        urls += [a["url"] for a in json.loads(story.get("cluster_json") or "[]")]
    except Exception:
        pass
    s = requests.Session()
    last_err = "isi artikel tidak terbaca"
    for u in urls[:4]:
        try:
            real, text = fetch_text(u, s)
            if len(text) >= MIN_CHARS:
                db.execute("UPDATE stories SET content=?, content_status='OK', content_url=? WHERE id=?",
                           (text, real, story["id"]))
                return True, f"isi diambil dari {urlparse(real).hostname} ({len(text)} huruf)"
            last_err = f"isi terlalu pendek dari {urlparse(real).hostname}"
        except Exception as e:
            last_err = str(e)[:150]
        log(f"Gagal ambil isi dari salah satu sumber: {last_err}", "warning")
    db.execute("UPDATE stories SET content_status='FAILED' WHERE id=?", (story["id"],))
    return False, last_err
