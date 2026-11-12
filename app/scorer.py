"""Penilaian AI untuk kandidat berita. Satu request, input ringkas, output ringkas (hemat token)."""
from typing import Dict, List, Tuple

from . import llm

HORROR_TOPIC = "horor/mistis/misteri Indonesia, pembunuhan, atau kasus kriminal Indonesia"


def build_prompt(cands: List[dict], mode: str, user_query: str) -> Tuple[str, str]:
    topic = HORROR_TOPIC if mode == "horror" else f"sesuai pencarian pengguna: \"{user_query[:200]}\""
    system = (
        "Kamu kurator berita untuk video pendek viral. "
        f"Topik target: {topic}. "
        "Beri tiap berita skor fit 0-100: kecocokan dengan topik, berupa berita/kisah NYATA dengan fakta "
        "cukup untuk dinarasikan, dan potensi viral (kolom cov = artikel x media yang meliput; makin "
        "banyak makin bagus). Skor <20 untuk: film/series/novel/fiksi, promosi, listicle, opini, resep, "
        "judul clickbait tanpa fakta, atau tidak relevan dengan topik. "
        'Format baris input: idx|judul|media|cov. Balas JSON saja: {"r":[[idx,fit,"alasan maks 8 kata"],...]} '
        "untuk semua idx.")
    lines = "\n".join(f"{c['idx']}|{c['title'][:120]}|{c['source'][:24]}|{c['coverage']}x{c['sources']}"
                      for c in cands)
    return system, lines


def score_candidates(cands: List[dict], mode: str, user_query: str) -> Tuple[Dict[int, Tuple[float, str]], str]:
    """Return ({idx: (fit, alasan)}, usage_str)."""
    if not cands:
        return {}, ""
    system, user = build_prompt(cands, mode, user_query)
    data, usage = llm.complete_json(system, user, max_tokens=min(6000, 600 + len(cands) * 50))
    out: Dict[int, Tuple[float, str]] = {}
    for row in (data.get("r") or []):
        try:
            idx, fit = int(row[0]), float(row[1])
            reason = str(row[2])[:120] if len(row) > 2 else ""
            out[idx] = (max(0.0, min(100.0, fit)), reason)
        except Exception:
            continue
    return out, usage


def combine(popularity: float, fit) -> float:
    """Skor akhir = 55% popularitas (seberapa banyak muncul di internet) + 45% penilaian AI."""
    if fit is None:
        return round(popularity, 1)
    return round(0.55 * popularity + 0.45 * fit, 1)
