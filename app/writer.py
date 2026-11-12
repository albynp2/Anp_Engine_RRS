"""Penulis naskah: hanya dari isi artikel sumber. Output dipecah per segmen dengan emosi + prompt gambar."""
import re
from typing import List

from . import article_fetch, db, llm
from .jobs import Job

EMOTIONS = ["neutral", "serious", "sad", "angry", "scared", "surprised", "happy"]
WORDS_PER_SEC = 2.4  # kecepatan baca TTS Indonesia, kira-kira

CUE = {"neutral": "", "serious": "[serius]", "sad": "[sedih, pelan]", "angry": "[marah, tegas]",
       "scared": "[tegang, setengah berbisik]", "surprised": "[terkejut]", "happy": "[gembira]"}
SAFE_WORDS = {"indonesia", "tuhan", "allah", "wib", "polri", "tni"}


def build_prompt(story: dict, content: str, target_seconds: int):
    words = int(target_seconds * WORDS_PER_SEC)
    n_min = max(5, round(target_seconds / 8))
    system = (
        "Kamu penulis naskah video berita pendek berbahasa Indonesia. ATURAN KERAS: tulis HANYA dari "
        "TEKS SUMBER. Dilarang menambah fakta, nama, angka, lokasi, waktu, dialog, atau detail suasana "
        "yang tidak tertulis di sumber. Pertahankan kata kehati-hatian (diduga, terduga, menurut "
        "polisi/saksi). Jangan menyatakan hal gaib sebagai fakta: tulis 'menurut warga/saksi'. Hindari "
        "detail kekerasan grafis; jangan sebut identitas anak/korban kekerasan seksual. Gaya: bahasa "
        "lisan mengalir, kalimat pendek, enak didengar. "
        f"Panjang total sekitar {words} kata dalam {n_min}-{n_min + 4} segmen. Segmen pertama = hook 1-2 "
        "kalimat dari fakta terkuat; segmen terakhir = penutup ringan tanpa fakta baru. "
        "Tiap segmen punya emosi suara: " + ", ".join(EMOTIONS) + " (sesuaikan dengan isi, jangan "
        "berlebihan) dan image_prompt (bahasa Inggris, adegan sinematik generik yang aman: tanpa teks, "
        "logo, wajah orang nyata, darah/gore). "
        'Balas JSON saja: {"title":"","segments":[{"text":"","emotion":"","image_prompt":""}],'
        '"caption":"","hashtags":["#"],"story_type":"horor|kriminal|misteri|lainnya",'
        '"source_basis":"1 kalimat dasar fakta","fact_boundary":"hal yang BELUM dikonfirmasi sumber"}')
    user = (f"Judul: {story['title']}\nMedia: {story.get('source', '')}\n"
            f"Tanggal: {story.get('published_date') or (story.get('published') or '')[:10]}\n"
            f"TEKS SUMBER:\n{content[:article_fetch.MAX_CHARS]}")
    return system, user


def derive_fields(segments: List[dict]) -> dict:
    texts = [s["text"] for s in segments]
    return {"hook": texts[0], "ending": texts[-1] if len(texts) > 1 else "",
            "script": "\n".join(texts[1:-1]) if len(texts) > 2 else ""}


def normalize_segments(raw) -> List[dict]:
    segs = []
    for s in raw or []:
        text = re.sub(r"\s+", " ", str(s.get("text", ""))).strip()
        if not text:
            continue
        emo = str(s.get("emotion", "neutral")).strip().lower()
        segs.append({"text": text, "emotion": emo if emo in EMOTIONS else "neutral",
                     "image_prompt": str(s.get("image_prompt", "")).strip()[:300]})
    return segs


def normalize(data: dict) -> dict:
    segs = normalize_segments(data.get("segments"))
    if len(segs) < 3:
        raise ValueError("AI menghasilkan terlalu sedikit segmen naskah")
    tags = data.get("hashtags") or []
    if isinstance(tags, str):
        tags = re.findall(r"#?\w+", tags)
    tags = " ".join(t if t.startswith("#") else "#" + t for t in tags[:12])
    out = {"title": str(data.get("title", "")).strip()[:140], "segments": segs,
           "caption": str(data.get("caption", "")).strip(), "hashtags": tags,
           "story_type": str(data.get("story_type", "")).strip(),
           "source_basis": str(data.get("source_basis", "")).strip(),
           "fact_boundary": str(data.get("fact_boundary", "")).strip()}
    out.update(derive_fields(segs))
    return out


# ------------------------------------------------------------------ pengecek fakta sederhana
def _digits(s: str) -> str:
    return re.sub(r"[.,\s]", "", s)


def find_unsupported(segments: List[dict], source_text: str) -> List[str]:
    """Angka & nama (kata berhuruf besar di tengah kalimat) di naskah yang TIDAK ada di sumber."""
    src = source_text.lower()
    src_digits = re.sub(r"[.,\s]", "", src)
    flagged: List[str] = []
    for seg in segments:
        text = seg["text"]
        for m in re.finditer(r"\d[\d.,]*", text):
            d = _digits(m.group())
            if d and d not in src_digits and m.group() not in flagged:
                flagged.append(m.group())
        for sent in re.split(r"(?<=[.!?])\s+", text):
            words = re.findall(r"[A-Za-z][A-Za-z\-']+", sent)
            for w in words[1:]:
                if w[0].isupper() and w.lower() not in SAFE_WORDS and w.lower() not in src \
                        and w not in flagged:
                    flagged.append(w)
    return flagged[:15]


# ------------------------------------------------------------------ ekspor teks untuk Google AI Studio
def tts_export(script: dict, voice_hint: str = "pembawa berita pria/wanita yang tenang dan jelas") -> str:
    style = (f"Bacakan sebagai {voice_hint} untuk video berita pendek berbahasa Indonesia. Tempo sedang, "
             "artikulasi jelas, ekspresi emosional sesuai petunjuk dalam kurung siku di awal tiap paragraf "
             "(jangan dibaca). Beri jeda sekitar satu detik antar paragraf.")
    paras = []
    for s in script.get("segments", []):
        cue = CUE.get(s.get("emotion", "neutral"), "")
        paras.append((cue + " " if cue else "") + s["text"])
    return ("=== STYLE INSTRUCTIONS (tempel di kolom Style instructions) ===\n" + style +
            "\n\n=== TEKS (tempel di kolom teks) ===\n" + "\n\n".join(paras) + "\n")


def estimate_seconds(segments: List[dict]) -> int:
    return round(sum(len(s["text"].split()) for s in segments) / WORDS_PER_SEC)


# ------------------------------------------------------------------ job
def write_one(story: dict, target_seconds: int) -> dict:
    system, user = build_prompt(story, story["content"], target_seconds)
    data, usage = llm.complete_json(system, user, max_tokens=3000)
    out = normalize(data)
    out["fact_warnings"] = find_unsupported(out["segments"], story["content"])
    out["_usage"] = usage
    if not out["title"]:
        out["title"] = story["title"]
    return out


def run_write(job: Job, p: dict) -> dict:
    ids = [int(x) for x in p.get("storyIds", [])]
    if not ids:
        raise ValueError("Pilih minimal satu berita.")
    force = bool(p.get("force"))
    cfg = db.get_content_settings().get("config", {})
    target = int(p.get("durationSeconds") or cfg.get("durationSeconds") or 60)
    db.queue_add(ids)
    written, failed, skipped = [], [], []
    for k, sid in enumerate(ids):
        job.check_cancel()
        base = 100 * k / len(ids)
        s = db.get_story(sid)
        if not s:
            failed.append({"id": sid, "reason": "berita tidak ditemukan"})
            continue
        if s["has_script"] and not force:
            skipped.append(sid)
            job.log(f"[{k + 1}/{len(ids)}] sudah punya naskah, dilewati: {s['title'][:60]}")
            continue
        job.set_progress(base + 5, f"[{k + 1}/{len(ids)}] Mengambil isi artikel")
        ok, msg = article_fetch.ensure_content(s, job.log)
        if not ok:
            failed.append({"id": sid, "reason": f"isi artikel tidak terbaca ({msg}). Tempel isi manual di "
                                                 "Production Queue."})
            job.log(f"Gagal: {s['title'][:60]} - {msg}", "error")
            continue
        job.log(f"[{k + 1}/{len(ids)}] {msg}")
        s = db.get_story(sid)
        job.set_progress(base + 30 / len(ids) * 3, f"[{k + 1}/{len(ids)}] AI menulis naskah")
        try:
            out = write_one(s, target)
        except Exception as e:
            failed.append({"id": sid, "reason": str(e)[:200]})
            job.log(f"Gagal menulis naskah '{s['title'][:60]}': {e}", "error")
            continue
        db.save_script(sid, out)
        written.append(sid)
        warn = out["fact_warnings"]
        job.log(f"Naskah selesai ({estimate_seconds(out['segments'])} dtk). Token: {out['_usage']}"
                + (f" | PERIKSA, tidak ada di sumber: {', '.join(warn)}" if warn else " | cek fakta OK"),
                "warning" if warn else "info")
    return {"written": written, "failed": failed, "skipped": skipped}
