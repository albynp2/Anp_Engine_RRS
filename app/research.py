"""Research: cari berita (Google News RSS) -> filter -> popularity -> AI scoring -> simpan ke gallery."""
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple

import requests

from . import config, db, llm, popularity, scorer
from .jobs import Job

RSS_URL = "https://news.google.com/rss/search"

# Mode 1: preset "horor" = horor + pembunuhan + kriminal (sesuai permintaan)
HORROR_PRESET_QUERIES = [
    "kisah horor nyata Indonesia viral",
    "kejadian mistis Indonesia viral",
    "penampakan misterius Indonesia",
    "teror hantu viral Indonesia",
    "kasus pembunuhan Indonesia viral",
    "pembunuhan sadis terungkap",
    "kasus kriminal viral Indonesia",
    "misteri kasus Indonesia belum terungkap",
]
HORROR_DEFAULT_EXCLUDE = ["film", "netflix", "bioskop", "sinopsis", "trailer", "rekomendasi",
                          "rating", "drakor", "novel", "webtoon"]


# ------------------------------------------------------------------ tanggal & input
def resolve_dates(today_only: bool, start: str, end: str, today: Optional[date] = None) -> Tuple[date, date]:
    """Aturan:
    - 'Hari ini saja' dicentang        -> hari ini (WIB)
    - tidak dicentang & ada tgl        -> pakai start/end; bila salah satu kosong, dilengkapi
    - tidak dicentang & kosong semua   -> hari ini
    """
    today = today or config.today_local()
    if today_only:
        return today, today

    def parse(s):
        s = (s or "").strip()
        return date.fromisoformat(s[:10]) if s else None

    d1, d2 = parse(start), parse(end)
    if not d1 and not d2:
        return today, today
    if d1 and not d2:
        d2 = max(today, d1)
    if d2 and not d1:
        d1 = d2
    if d1 > d2:
        d1, d2 = d2, d1
    return d1, d2


def parse_list(text: str) -> List[str]:
    return [x.strip() for x in re.split(r"[\n,;]+", text or "") if x.strip()]


def pick_queries(mode: str, query_text: str) -> List[str]:
    if mode == "horror":
        return list(HORROR_PRESET_QUERIES)
    qs = [q.strip() for q in (query_text or "").splitlines() if q.strip()]
    if not qs:
        raise ValueError("Isi kata kunci pencarian dulu (mode input sendiri).")
    return qs[:6]


# ------------------------------------------------------------------ RSS
def fetch_rss(query: str, d_from: date, d_to: date, session: requests.Session) -> List[dict]:
    q = f"{query} after:{d_from.isoformat()} before:{(d_to + timedelta(days=1)).isoformat()}"
    r = session.get(RSS_URL, params={"q": q, "hl": "id", "gl": "ID", "ceid": "ID:id"},
                    timeout=25, headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    return parse_rss(r.content, query)


def parse_rss(xml_bytes: bytes, query: str) -> List[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        suffix = f" - {source}"
        if source and title.endswith(suffix):
            title = title[: -len(suffix)].strip()
        dt = None
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate")).astimezone(config.TZ)
        except Exception:
            pass
        items.append({"title": title, "url": link, "source": source or "Unknown", "dt": dt,
                      "published": dt.isoformat() if dt else "",
                      "published_date": dt.date().isoformat() if dt else None,
                      "published_ts": dt.timestamp() if dt else 0, "query": query})
    return items


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def filter_items(items: List[dict], d_from: date, d_to: date, excludes: List[str]) -> List[dict]:
    ex = [e.lower() for e in excludes]
    seen_url, seen_title, out = set(), set(), []
    for it in items:
        if it["dt"] and not (d_from <= it["dt"].date() <= d_to):
            continue  # tanggal terbit (WIB) di luar rentang
        tl = it["title"].lower()
        if any(e in tl for e in ex):
            continue
        nt = norm_title(it["title"])
        if it["url"] in seen_url or nt in seen_title:
            continue
        seen_url.add(it["url"])
        seen_title.add(nt)
        out.append(it)
    return out


# ------------------------------------------------------------------ job utama
def run_research(job: Job, p: dict) -> dict:
    mode = p.get("mode") if p.get("mode") in ("horror", "custom") else "custom"
    queries = pick_queries(mode, p.get("query", ""))
    d_from, d_to = resolve_dates(bool(p.get("todayOnly")), p.get("startDate", ""), p.get("endDate", ""))
    excludes = parse_list(p.get("exclude", ""))
    max_cand = max(3, min(40, int(p.get("maxCandidates") or 15)))
    use_ai = bool(p.get("useAI", True)) and llm.ai_available()

    job.log(f"Mode: {'Horor/Pembunuhan/Kriminal' if mode == 'horror' else 'Input sendiri'}")
    job.log(f"Rentang tanggal (WIB): {d_from} s/d {d_to} | exclude: {', '.join(excludes) or '(kosong)'}")
    if p.get("useAI", True) and not llm.ai_available():
        job.log("OPENAI_API_KEY kosong -> skor hanya dari popularitas lokal.", "warning")

    session = requests.Session()
    raw: List[dict] = []
    failed = 0
    for i, q in enumerate(queries):
        job.check_cancel()
        job.set_progress(5 + 35 * i / len(queries), f"Mencari: {q}")
        try:
            got = fetch_rss(q, d_from, d_to, session)
            job.log(f"'{q}' -> {len(got)} artikel")
            raw += got
        except Exception as e:
            failed += 1
            job.log(f"Gagal mencari '{q}': {e}", "warning")
        time.sleep(0.4)
    if failed == len(queries):
        raise RuntimeError("Semua pencarian gagal. Cek koneksi internet laptop.")

    items = filter_items(raw, d_from, d_to, excludes)
    job.log(f"Total mentah {len(raw)} -> setelah filter tanggal/exclude/duplikat: {len(items)}")
    run_id = db.execute("INSERT INTO research_runs (mode, params_json, found) VALUES (?,?,?)",
                        (mode, json.dumps(p, ensure_ascii=False), len(items)))
    if not items:
        return {"runId": run_id, "found": 0, "saved": 0, "message": "Tidak ada berita pada rentang ini."}

    job.set_progress(45, "Menghitung popularitas")
    clusters = popularity.analyze(items)
    top = clusters[:max_cand]
    job.log(f"{len(clusters)} topik unik; {len(top)} kandidat teratas diproses")

    fits = {}
    ai_used = 0
    if use_ai:
        job.check_cancel()
        job.set_progress(60, f"AI menilai {len(top)} kandidat")
        cands = [{"idx": i, "title": c["rep"]["title"], "source": c["rep"]["source"],
                  "coverage": c["coverage_count"], "sources": c["unique_source_count"]}
                 for i, c in enumerate(top)]
        try:
            fits, usage = scorer.score_candidates(cands, mode, "\n".join(queries))
            ai_used = len(fits)
            job.log(f"AI selesai menilai {ai_used}/{len(top)} kandidat. Token: {usage}")
        except Exception as e:
            job.log(f"Penilaian AI gagal, pakai skor popularitas saja: {e}", "warning")

    job.set_progress(85, "Menyimpan ke gallery")
    saved = new = rejected = 0
    for i, c in enumerate(top):
        fit, reason = fits.get(i, (None, ""))
        if fit is not None and fit <= 15:
            rejected += 1
            continue
        rep = c["rep"]
        alts = [{"title": m["title"], "url": m["url"], "source": m["source"]}
                for m in c["members"] if m["url"] != rep["url"]][:6]
        overall = scorer.combine(c["popularity_score"], fit)
        _, is_new = db.upsert_candidate({
            "title": rep["title"], "url": rep["url"], "source": rep["source"],
            "published": rep["published"], "published_date": rep["published_date"],
            "popularity_score": c["popularity_score"], "ai_score": fit, "ai_reason": reason,
            "overall_score": overall, "coverage_count": c["coverage_count"],
            "unique_source_count": c["unique_source_count"], "query_count": c["query_count"],
            "cluster_json": json.dumps(alts, ensure_ascii=False), "run_id": run_id, "mode": mode,
            "query": rep["query"]})
        saved += 1
        new += int(is_new)
    db.execute("UPDATE research_runs SET kept=?, scored_by_ai=? WHERE id=?", (saved, ai_used, run_id))
    job.log(f"Tersimpan {saved} kandidat ({new} baru, {rejected} ditolak AI).")
    return {"runId": run_id, "found": len(items), "topics": len(clusters), "saved": saved,
            "newArticles": new, "rejectedByAI": rejected, "aiScored": ai_used,
            "range": [d_from.isoformat(), d_to.isoformat()]}
