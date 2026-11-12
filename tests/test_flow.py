"""Tes alur lengkap dengan jaringan & AI dipalsukan. Jalankan: python -m tests.test_flow
(Butuh fastapi terpasang, atau stub saat tes offline.)"""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp()

from app import article_fetch, db, llm, main, research, scorer, writer  # noqa: E402
from app.jobs import Job  # noqa: E402
from tests.test_research import HTML, SAMPLE_RSS  # noqa: E402


def test_all():
    db.init_db()
    seen_queries = []

    def fake_rss(q, d1, d2, session):
        seen_queries.append(q)
        return research.parse_rss(SAMPLE_RSS, q)

    research.fetch_rss = fake_rss
    llm.ai_available = lambda: True

    def fake_score(cands, mode, uq):
        out = {}
        for c in cands:
            out[c["idx"]] = (10, "film") if "film" in c["title"].lower() else (80 - c["idx"], "cocok")
        return out, "in=100 out=50"
    scorer.score_candidates = fake_score

    # --- riset mode horor, rentang hari ini (WIB) = 12 Nov 2026
    job = Job("research", {})
    res = research.run_research(job, {"mode": "horror", "todayOnly": True, "exclude": "", "maxCandidates": 10,
                                      "useAI": True})
    print(res)
    assert len(seen_queries) == len(research.HORROR_PRESET_QUERIES)
    assert res["found"] == 4 and res["topics"] == 2 and res["rejectedByAI"] == 1 and res["saved"] == 1, res
    g = main.articles(1, 25, "", "NEW", "", "")
    scores = [a["overall_score"] for a in g["items"]]
    assert scores == sorted(scores, reverse=True) and len(g["items"]) == 1
    top = g["items"][0]
    assert top["coverage_count"] == 3 and top["ai_score"] is not None

    # --- mode custom wajib ada query; exclude kosong boleh
    try:
        main.start_job("research", {"mode": "custom", "query": "  "})
        raise AssertionError("harus gagal")
    except ValueError:
        pass
    res2 = research.run_research(Job("research", {}), {"mode": "custom", "query": "kisah horor hari ini viral",
                                                       "startDate": "2026-11-01", "endDate": "2026-11-12",
                                                       "exclude": "", "useAI": False})
    assert res2["range"] == ["2026-11-01", "2026-11-12"] and res2["aiScored"] == 0

    # --- queue (pilihan user) lalu tulis naskah
    ids = [a["id"] for a in main.articles(1, 25, "", "NEW", "", "")["items"]][:1]
    assert main.queue_add({"ids": ids}) == {"inserted": 1}
    assert main.queue_list()["items"][0]["stage"] == "QUEUED"

    article_fetch.fetch_text = lambda url, s: ("https://contoh.com/a", article_fetch.extract_text(HTML))

    def fake_llm(system, user, max_tokens=2000):
        assert "TEKS SUMBER" in user       # naskah berbasis isi artikel, bukan judul saja
        return {"title": "Sosok Putih", "segments": [
            {"text": "Warga Desa Sukamaju geger oleh sosok putih di dekat jembatan.", "emotion": "surprised",
             "image_prompt": "foggy bridge"},
            {"text": "Saksi bernama Rudi mengaku melihatnya pukul 22.00 WIB bersama 7 warga lain.",
             "emotion": "serious", "image_prompt": "village"},
            {"text": "Polisi di Jakarta Selatan akan mengecek lokasi.", "emotion": "WEIRD", "image_prompt": "x"}],
            "caption": "cap", "hashtags": ["horor", "#viral"], "story_type": "misteri",
            "source_basis": "b", "fact_boundary": "f"}, "in=1 out=1"
    llm.complete_json = fake_llm
    out = writer.run_write(Job("write", {}), {"storyIds": ids, "durationSeconds": 60})
    assert out["written"] == ids and not out["failed"], out
    assert "Sukamaju" in db.get_story(ids[0])["content"]
    sc = main.script_get(ids[0])
    assert sc["segments"][2]["emotion"] == "neutral"                 # emosi aneh dinormalkan
    assert sc["hashtags"] == "#horor #viral"
    warn = sc["fact_warnings"]
    print("fact_warnings:", warn)
    assert "7" in warn and "Jakarta" in warn and "Rudi" not in warn and "Sukamaju" not in warn
    assert "[serius]" in sc["tts_text"] and sc["uploaded_audio"] is None
    assert db.get_story(ids[0])["stage"] == "WRITTEN"

    # --- gagal ambil isi -> pesan jelas, tidak ngarang
    ids2 = [a["id"] for a in main.articles(1, 25, "", "NEW", "", "")["items"]][:1]
    article_fetch.fetch_text = lambda url, s: ("x", "")
    out2 = writer.run_write(Job("write", {}), {"storyIds": ids2})
    assert out2["failed"] and "isi artikel" in out2["failed"][0]["reason"]
    assert db.get_story(ids2[0])["content_status"] == "FAILED"
    # isi manual lalu coba lagi
    main.set_content(ids2[0], {"content": "Teks manual. " * 40})
    out3 = writer.run_write(Job("write", {}), {"storyIds": ids2})
    assert out3["written"] == ids2, out3

    # --- edit naskah via API
    r = main.script_update(ids[0], {"title": "Baru", "segments": sc["segments"][:2] + [
        {"text": "Penutup.", "emotion": "sad", "image_prompt": ""}]})
    assert r["ok"] and main.script_get(ids[0])["title"] == "Baru"
    # --- hapus dari queue hanya bila belum ada naskah
    try:
        main.queue_remove(ids[0])
        raise AssertionError
    except Exception as e:
        assert getattr(e, "status_code", 0) == 409
    d = main.dashboard()
    print(d["totals"])
    assert d["totals"]["scriptsWritten"] == 2 and d["totals"]["articles"] >= 2
    h = main.health()
    assert h["ok"] and "tz" in h
    c = main.app_config()
    assert len(c["platforms"]) == 4
    print("FLOW OK")


if __name__ == "__main__":
    test_all()
