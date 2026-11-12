"""Skor popularitas berita: seberapa banyak artikel & media berbeda yang membahas topik yang sama.

Catatan jujur: jumlah pengunjung per artikel tidak tersedia dari sumber gratis mana pun.
Indikator terbaik yang bisa diukur adalah "berapa banyak media berbeda meliput kejadian yang sama".
"""
import math
import re
from typing import Dict, List

STOP = {"yang", "dan", "di", "ke", "dari", "ini", "itu", "dengan", "saat", "karena", "para",
        "sebuah", "ada", "dalam", "untuk", "hingga", "oleh", "tentang", "asal", "indonesia",
        "viral", "kabar", "berita", "terbaru", "hari", "kini"}


def clean_title(title: str) -> str:
    t = re.sub(r"[^a-z0-9\s]", " ", (title or "").lower())
    return " ".join(w for w in t.split() if len(w) >= 3 and w not in STOP)


def _similarity(docs: List[str]):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    try:
        m = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_df=0.9).fit_transform(docs)
        return cosine_similarity(m)
    except ValueError:  # vocabulary kosong
        return None


def cluster(items: List[dict], threshold: float = 0.38):
    n = len(items)
    sim = _similarity([clean_title(i["title"]) or i["title"].lower() for i in items]) if n > 1 else None
    if sim is None:
        return [[i] for i in range(n)], sim
    assigned, groups = set(), []
    for i in range(n):
        if i in assigned:
            continue
        g = [i]
        assigned.add(i)
        for j in range(i + 1, n):
            if j not in assigned and sim[i, j] >= threshold:
                g.append(j)
                assigned.add(j)
        groups.append(g)
    return groups, sim


def score(coverage: int, sources: int, queries: int) -> float:
    """0-100. Log-scale supaya 6 vs 12 artikel tetap terbedakan (versi lama jenuh di 5 artikel)."""
    cov = min(1.0, math.log1p(coverage) / math.log1p(12))
    src = min(1.0, math.log1p(sources) / math.log1p(8))
    qry = min(1.0, queries / 3.0)
    return round(100 * (0.40 * cov + 0.50 * src + 0.10 * qry), 1)


def analyze(items: List[dict]) -> List[Dict]:
    """items: dict dengan title,url,source,published(dt/None),query. Hasil diurutkan skor tertinggi."""
    if not items:
        return []
    groups, sim = cluster(items)
    results = []
    for g in groups:
        members = [items[i] for i in g]
        # wakil = artikel yang paling "sentral" di cluster
        if sim is not None and len(g) > 1:
            best = max(g, key=lambda i: float(sum(sim[i, j] for j in g)))
        else:
            best = g[0]
        rep = items[best]
        sources = {(m.get("source") or "").strip().lower() for m in members if m.get("source")}
        queries = {(m.get("query") or "").strip().lower() for m in members if m.get("query")}
        results.append({
            "rep": rep,
            "members": members,
            "coverage_count": len(members),
            "unique_source_count": len(sources),
            "query_count": len(queries),
            "popularity_score": score(len(members), len(sources), len(queries)),
        })
    results.sort(key=lambda r: (r["popularity_score"], r["rep"].get("published_ts") or 0), reverse=True)
    return results
