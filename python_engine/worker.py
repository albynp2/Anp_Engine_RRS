'''JSON-line worker used by the local Node.js API. Never print secrets.'''

import json
import os
import sqlite3
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Keep the original stdout for JSON-line communication with Node.js.
PROTOCOL_STDOUT = sys.stdout

# Prevent Unicode/emoji logging from crashing on Windows terminals.
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def emit(kind, **kwargs):
    """Write one JSON event to the protocol stdout; never write plain logs here."""
    message = {"type": kind, **kwargs}
    print(
        json.dumps(message, ensure_ascii=True, default=str),
        file=PROTOCOL_STDOUT,
        flush=True,
    )


def query_all(sql, params=()):
    from database.database import get_connection

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def run_research(cfg):
    from datetime import datetime, timedelta
    from email.utils import parsedate_to_datetime
    from research.researcher import search_google_news
    from research.content_fetcher import fetch_article_content
    from research.popularity import analyze_popularity
    from database.database import (
        create_database,
        save_story,
        get_story_status,
        get_story_id_by_url,
        queue_selected_topic,
        update_story_content,
        save_ai_score,
    )

    queries = [str(value).strip() for value in cfg.get("queries", []) if str(value).strip()]
    excludes = [str(value).strip().lower() for value in cfg.get("excludedKeywords", []) if str(value).strip()]
    if not queries:
        raise ValueError("Tambahkan minimal satu query RSS.")

    today = datetime.now().strftime("%Y-%m-%d")
    if cfg.get("todayOnly"):
        start = end = today
    else:
        start = cfg.get("startDate") or datetime.now().strftime("%Y-%m-01")
        end = cfg.get("endDate") or today

    if start > end:
        raise ValueError("Tanggal mulai tidak boleh melewati tanggal akhir.")

    # The RSS end date is exclusive, so add one day to include the chosen end date.
    end_exclusive = (datetime.strptime(end, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
    create_database()
    all_items = []

    emit(
        "log",
        level="info",
        message=f"Rentang riset: {start} s.d. {end} (inklusif); query={len(queries)}; todayOnly={bool(cfg.get('todayOnly'))}.",
    )

    for index, query in enumerate(queries, 1):
        emit(
            "progress",
            percent=int(5 + 25 * index / len(queries)),
            stage=f"RSS {index}/{len(queries)}: {query}",
        )
        try:
            items = search_google_news(query, start, end_exclusive)
            all_items.extend(items)
            emit(
                "log",
                level="info" if items else "warning",
                message=f"RSS query {index}/{len(queries)} menghasilkan {len(items)} artikel: {query}",
            )
        except Exception as exc:
            emit("log", level="error", message=f"Query gagal ({query}): {exc}")

    if not all_items:
        emit(
            "log",
            level="warning",
            message="Semua query menghasilkan 0 artikel. Cek rentang tanggal, koneksi internet, atau error RSS di log di atas.",
        )

    emit("progress", percent=35, stage="Deduplication dan filter")
    deduplicated = {}
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()

    for item in all_items:
        url = (item.get("url") or "").strip()
        if not url:
            continue

        title = (item.get("title") or "").lower()
        if any(keyword in title for keyword in excludes):
            continue

        published = item.get("published", "")
        try:
            published_date = parsedate_to_datetime(published).date()
            if not start_date <= published_date <= end_date:
                continue
        except (TypeError, ValueError, OverflowError):
            # Keep the previous pipeline's conservative rule: unknown dates are excluded.
            continue

        deduplicated[url] = item

    filtered = list(deduplicated.values())
    emit("log", message=f"{len(all_items)} hasil mentah; {len(filtered)} lolos filter/dedup.")
    emit("progress", percent=48, stage="Analisis popularitas lokal (TF-IDF/clustering)")

    ranked = analyze_popularity(filtered) if filtered else []
    emit("progress", percent=52, stage="Mengambil konten artikel asli")
    fetch_ok = 0
    fetch_failed = 0
    for index, item in enumerate(filtered, 1):
        story_id = get_story_id_by_url(item["url"])
        if story_id is None:
            save_story(item)
            story_id = get_story_id_by_url(item["url"])
        try:
            fetched = fetch_article_content(item["url"])
            content = fetched["content"]
            if len(content.strip()) < 300:
                raise ValueError("Konten artikel terlalu pendek/tidak terdeteksi.")
            item["source_content"] = content
            item["resolved_url"] = fetched.get("resolved_url") or item["url"]
            item["fetch_http_status"] = fetched.get("http_status")
            update_story_content(story_id, content, "FETCHED", None)
            fetch_ok += 1
        except Exception as exc:
            item["source_content"] = ""
            item["fetch_error"] = str(exc)
            update_story_content(story_id, "", "ISI TIDAK TERSEDIA", str(exc))
            fetch_failed += 1
            emit("log", level="warning", message=f"Source {index}/{len(filtered)} gagal: {item.get('title', '')[:80]} — {str(exc)[:240]}")
        else:
            emit("log", level="info", message=f"Source {index}/{len(filtered)} OK: {item.get('source', '')} — URL akhir: {item.get('resolved_url', item['url'])}")
        emit("progress", percent=int(52 + 10 * index / max(1, len(filtered))), stage=f"Artikel asli {index}/{len(filtered)}")
    filtered = [item for item in filtered if item.get("source_content")]
    emit("log", level="info", message=f"Konten sumber berhasil diambil: {fetch_ok}; tidak tersedia: {fetch_failed}. Kandidat tanpa konten tidak dikirim ke AI.")
    emit("progress", percent=62, stage="Menyimpan artikel ke SQLite")

    new_count = 0
    for item in filtered:
        if get_story_status(item["url"]) is None:
            save_story(item)
            new_count += 1

    # Persist local ranking signals independently from the queue so the library
    # can sort unqueued articles without confusing local popularity with AI score.
    conn = __import__("database.database", fromlist=["get_connection"]).get_connection()
    try:
        for topic in ranked:
            conn.execute("""UPDATE stories SET popularity_score=?, coverage_count=?,
                unique_source_count=?, query_count=? WHERE url=?""",
                (topic.get("popularity_score"), topic.get("coverage_count"),
                 topic.get("unique_source_count"), topic.get("query_count"), topic.get("url")))
        conn.commit()
    finally:
        conn.close()

    emit("log", message=f"{new_count} artikel baru disimpan; {len(filtered) - new_count} sudah ada.")
    candidate_limit = max(1, min(int(cfg.get("topCandidates", 30)), 50))
    candidates = []

    for topic in ranked[:candidate_limit]:
        source_item = next((item for item in filtered if item.get("url") == topic.get("url")), {})
        candidates.append({
            key: (source_item.get(key) if key == "source_content" else topic.get(key))
            for key in (
                "title", "url", "source", "published", "popularity_score",
                "coverage_count", "unique_source_count", "query_count", "source_content",
            )
        })

    if not candidates:
        emit("progress", percent=100, stage="Selesai: tidak ada kandidat yang lolos")
        return {
            "rawCount": len(all_items), "filteredCount": len(filtered),
            "newCount": new_count, "scoredCount": 0, "queuedCount": 0,
            "mode": "local-only" if cfg.get("localOnly") else "ai-scoring",
        }

    if cfg.get("localOnly"):
        emit("log", level="info", message=f"Mode hemat token aktif: {len(candidates)} kandidat dianalisis lokal; OpenAI scoring dilewati.")
        emit("progress", percent=100, stage="Riset lokal selesai — OpenAI tidak dipanggil")
        return {
            "rawCount": len(all_items), "filteredCount": len(filtered),
            "newCount": new_count, "scoredCount": 0, "queuedCount": 0,
            "localCandidates": len(candidates), "mode": "local-only",
        }

    from ai.scorer import score_stories

    emit("progress", percent=72, stage=f"AI scoring {len(candidates)} kandidat")
    scored = score_stories(
        candidates,
        mode=cfg.get("mode", "horror"),
        custom_query=(queries[0] if cfg.get("mode") == "custom" and queries else "")
    )
    top = scored.get("top_10", [])
    if not isinstance(top, list):
        raise ValueError("AI scoring mengembalikan format top_10 yang tidak valid.")
    queued = 0
    saved_score_count = 0
    valid_id_count = 0
    invalid_id_count = 0
    missing_story_count = 0
    duplicate_id_count = 0
    seen_candidate_ids = set()

    for rank, item in enumerate(top, 1):
        try:
            candidate_id = int(item.get("id", 0))
            candidate_index = candidate_id - 1
        except (TypeError, ValueError):
            invalid_id_count += 1
            continue

        if candidate_id in seen_candidate_ids:
            duplicate_id_count += 1
            continue
        seen_candidate_ids.add(candidate_id)

        if candidate_index < 0 or candidate_index >= len(candidates):
            invalid_id_count += 1
            continue

        valid_id_count += 1
        topic = candidates[candidate_index]
        story_id = get_story_id_by_url(topic["url"])
        if story_id is None:
            missing_story_count += 1
            continue

        save_ai_score(story_id, item.get("overall_score", 0), item.get("reason", ""))
        saved_score_count += 1

    emit(
        "log",
        level="info" if saved_score_count else "warning",
        message=(
            f"AI pipeline diagnostic: {len(candidates)} kandidat lokal -> "
            f"{len(top)} hasil AI -> {valid_id_count} ID valid -> "
            f"{saved_score_count} score tersimpan; "
            f"ID invalid={invalid_id_count}, story tidak ditemukan={missing_story_count}, "
            f"ID duplikat={duplicate_id_count}."
        ),
    )

    if top and saved_score_count == 0:
        raise ValueError(f"AI mengembalikan {len(top)} hasil scoring, tetapi tidak ada score yang berhasil disimpan ke database.")

    emit(
        "log",
        level="info" if saved_score_count else "warning",
        message=f"AI scoring selesai: {len(top)} hasil dikembalikan; {saved_score_count} score tersimpan ke SQLite.",
    )
    emit("progress", percent=100, stage=f"Research selesai — {len(filtered)} data, {saved_score_count} score tersimpan")
    return {
        "rawCount": len(all_items), "filteredCount": len(filtered),
        "newCount": new_count,  "scoredCount": saved_score_count, "aiReturnedCount": len(top), "queuedCount": 0, "fetchedCount": fetch_ok, "unavailableCount": fetch_failed,
    }


def run_generate(cfg):
    # The writer module belongs to ai/ in the current project structure.
    from research.writer import generate_story
    from database.database import (
        save_generated_story,
        mark_queue_status,
        story_already_written,
    )

    story_id = int(cfg["storyId"])
    rows = query_all(
        """SELECT q.id queue_id, q.story_id, q.rank, q.research_popularity,
                  q.overall_score, s.title, s.url, s.source, s.published, s.source_content, s.fetch_status
           FROM production_queue q
           JOIN stories s ON s.id = q.story_id
           WHERE q.story_id = ?
           ORDER BY q.id DESC LIMIT 1""",
        (story_id,),
    )
    if not rows:
        raise ValueError("Artikel belum ada di production queue. Masukkan ke antrean dulu.")

    story = rows[0]
    if story_already_written(story_id):
        raise ValueError("Artikel ini sudah memiliki naskah. Cek Story Library.")

    emit("progress", percent=15, stage="Menyiapkan konteks artikel")
    emit("progress", percent=30, stage="Memanggil OpenAI untuk membuat narasi")
    result = generate_story(story)
    emit("progress", percent=85, stage="Menyimpan hasil narasi ke database")
    save_generated_story(story_id, result)
    mark_queue_status(story["queue_id"], "WRITTEN")
    emit("progress", percent=100, stage="Narasi berhasil dibuat")
    return {"storyId": story_id, "title": result.get("title", ""), "result": result}



def run_generate_bulk(cfg):
    story_ids = []
    for value in cfg.get("storyIds", []):
        try:
            story_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    story_ids = list(dict.fromkeys(story_ids))
    if not story_ids:
        raise ValueError("Pilih minimal satu artikel dari Production Queue.")
    results, failures = [], []
    total = len(story_ids)
    for index, story_id in enumerate(story_ids, 1):
        emit("progress", percent=int((index - 1) / total * 95), stage=f"Menulis cerita {index}/{total}")
        try:
            result = run_generate({"storyId": story_id})
            results.append(result)
            emit("log", level="info", message=f"Berhasil: {result.get('title') or story_id}")
        except Exception as exc:
            failures.append({"storyId": story_id, "error": str(exc)})
            emit("log", level="error", message=f"Gagal story #{story_id}: {exc}")
    emit("progress", percent=100, stage=f"Selesai: {len(results)} berhasil, {len(failures)} gagal")
    return {"requested": total, "succeeded": len(results), "failed": len(failures), "results": results, "failures": failures}


def get_content_settings():
    rows = query_all("SELECT config_json, updated_at FROM content_settings WHERE id=1")
    if rows:
        try:
            config = json.loads(rows[0]["config_json"])
        except (TypeError, ValueError):
            config = {}
        return {"config": config, "updatedAt": rows[0].get("updated_at")}
    return {"config": {}, "updatedAt": None}


def save_content_settings(cfg):
    allowed = {
        "platform", "aspectRatio", "width", "height", "fps", "durationSeconds",
        "template", "templateId", "storyId", "avatarId", "fit", "headline", "lowerThird",
        "watermarkText", "watermarkOpacity", "watermarkPosition", "watermarkImageData",
        "watermarkImageName", "voiceMode", "voice", "voiceData", "visualMode",
        "subtitleEnabled", "subtitleColor", "musicMode", "musicId", "selectedStoryIds", "notes"
    }
    config = {key: value for key, value in cfg.items() if key in allowed}
    if config.get("aspectRatio") not in {"9:16", "16:9", "1:1", "4:5"}:
        raise ValueError("Rasio video tidak valid.")
    width, height = int(config.get("width", 1080)), int(config.get("height", 1920))
    if width < 240 or height < 240 or width > 3840 or height > 3840:
        raise ValueError("Resolusi harus antara 240 dan 3840 piksel.")
    config["width"], config["height"] = width, height
    duration = int(config.get("durationSeconds", 60))
    if duration < 5 or duration > 600:
        raise ValueError("Durasi target harus antara 5 dan 600 detik.")
    fps = int(config.get("fps", 30))
    if fps not in {24, 25, 30, 60}:
        raise ValueError("FPS harus 24, 25, 30, atau 60.")
    expected = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0, "4:5": 4 / 5}[config["aspectRatio"]]
    if abs(width / height - expected) > 0.015:
        raise ValueError("Resolusi tidak sesuai dengan aspect ratio yang dipilih.")
    config["durationSeconds"], config["fps"] = duration, fps
    conn = __import__("database.database", fromlist=["get_connection"]).get_connection()
    try:
        conn.execute("""INSERT INTO content_settings(id, config_json, updated_at)
            VALUES(1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json, updated_at=CURRENT_TIMESTAMP""",
            (json.dumps(config, ensure_ascii=False),))
        conn.commit()
    finally:
        conn.close()
    return {"saved": True, "config": config}


def run_action(action, cfg):
    from database.database import create_database, mark_queue_status, queue_selected_topic

    create_database()

    if action == "dashboard":
        counts = {row["status"]: row["n"] for row in query_all("SELECT status, COUNT(*) n FROM stories GROUP BY status")}
        queue = {row["status"]: row["n"] for row in query_all("SELECT status, COUNT(*) n FROM production_queue GROUP BY status")}
        queue_total = query_all("SELECT COUNT(*) n FROM production_queue")[0]["n"]
        total = query_all("SELECT COUNT(*) n FROM stories")[0]["n"]
        written = query_all("SELECT COUNT(*) n FROM generated_stories")[0]["n"]

        from datetime import date, timedelta
        activity_rows = query_all("""
            SELECT date(created_at) AS day, COUNT(*) AS articles
            FROM stories
            WHERE date(created_at) >= date('now', '-13 days')
              AND date(created_at) <= date('now')
            GROUP BY date(created_at)
            ORDER BY day
        """)
        activity_map = {row["day"]: int(row["articles"]) for row in activity_rows if row.get("day")}
        today = date.today()
        research_activity = [
            {"day": (today - timedelta(days=offset)).isoformat(),
             "articles": activity_map.get((today - timedelta(days=offset)).isoformat(), 0)}
            for offset in range(13, -1, -1)
        ]

        return {
            "totalArticles": total,
            "queueTotal": queue_total,
            "written": written,
            "storyStatuses": counts,
            "queueStatuses": queue,
            "researchActivity": research_activity,
            "recentArticles": query_all("""
                SELECT s.id, s.title, s.url, s.source, s.published, s.status,
                       q.status queue_status, q.overall_score
                FROM stories s LEFT JOIN production_queue q ON q.story_id = s.id
                ORDER BY s.id DESC LIMIT 8
            """),
            "recentScripts": query_all("""
                SELECT g.id, g.story_id, g.title, g.created_at, s.title source_title
                FROM generated_stories g JOIN stories s ON s.id = g.story_id
                ORDER BY g.id DESC LIMIT 5
            """),
        }

    if action == "articles":
        page = max(1, int(cfg.get("page", 1)))
        limit = min(100, max(10, int(cfg.get("limit", 25))))
        offset = (page - 1) * limit
        search = f"%{cfg.get('search', '').strip()}%"
        status = cfg.get("status", "ALL")
        # Queue entries are excluded from the available library, not deleted.
        where = "WHERE q.story_id IS NULL AND (s.title LIKE ? OR s.source LIKE ? OR s.url LIKE ?)"
        params = [search, search, search]
        if status not in ("ALL", "NEW", "FETCHED", "SCORED", "SELECTED", "ISI TIDAK TERSEDIA"):
            raise ValueError("Filter status artikel tidak valid.")
        # Status filter must map to the lifecycle fields, not only validate
        # the requested value. This keeps the Gallery filters meaningful:
        # FETCHED/ISI TIDAK TERSEDIA use fetch_status, SCORED uses ai_score,
        # and SELECTED/NEW use the story lifecycle status.
        status_condition = ""
        if status == "FETCHED":
            status_condition = " AND s.fetch_status = ?"
            params.append("FETCHED")
        elif status == "ISI TIDAK TERSEDIA":
            status_condition = " AND s.fetch_status = ?"
            params.append("ISI TIDAK TERSEDIA")
        elif status == "SCORED":
            status_condition = " AND s.ai_score IS NOT NULL"
        elif status in ("NEW", "SELECTED"):
            status_condition = " AND s.status = ?"
            params.append(status)

        where_filtered = where + status_condition

        total = query_all(
            f"SELECT COUNT(*) n FROM stories s LEFT JOIN production_queue q ON q.story_id=s.id {where_filtered}",
            params,
        )[0]["n"]
        rows = query_all(f"""
            SELECT s.id, s.title, s.url, s.source, s.published, s.status,
                   s.popularity_score, s.overall_score, s.coverage_count,
                   s.unique_source_count, s.query_count, s.source_content, s.fetch_status, s.ai_score, s.ai_reason,
                   CASE WHEN g.id IS NULL THEN 0 ELSE 1 END has_script
            FROM stories s
            LEFT JOIN production_queue q ON q.story_id = s.id
            LEFT JOIN generated_stories g ON g.story_id = s.id
            {where_filtered}
        """, params)
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone
        def publication_timestamp(value):
            try:
                return parsedate_to_datetime(value).timestamp()
            except (TypeError, ValueError, OverflowError):
                try:
                    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()
                except (TypeError, ValueError, OverflowError):
                    return 0
        # Hide duplicate URLs that differ only by common tracking parameters.
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        unique_rows = []
        seen_urls = set()
        tracking_keys = {"gclid", "fbclid", "mc_cid", "mc_eid", "oc", "ved", "usg", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
        for row in rows:
            raw_url = str(row.get("url") or "").strip()
            parts = urlsplit(raw_url)
            clean_query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                           if key.lower() not in tracking_keys and not key.lower().startswith("utm_")]
            normalized_url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(clean_query), ""))
            key = normalized_url or raw_url
            if key in seen_urls:
                continue
            seen_urls.add(key)
            unique_rows.append(row)
        rows = unique_rows
        total = len(rows)
        rows.sort(key=lambda row: (
            row.get("overall_score") is not None,
            float(row.get("overall_score") or 0),
            row.get("popularity_score") is not None,
            float(row.get("popularity_score") or 0),
            publication_timestamp(row.get("published")),
            int(row.get("id") or 0),
        ), reverse=True)
        return {"items": rows[offset:offset + limit], "total": total, "page": page, "limit": limit}

    if action == "queue":
        status = cfg.get("status", "ALL")
        where = ""
        params = []
        if status != "ALL":
            where = "WHERE q.status = ?"
            params = [status]
        return {"items": query_all(f"""
            SELECT q.id queue_id, q.story_id, q.rank, q.research_popularity,
                   q.overall_score, q.status queue_status, s.title, s.url,
                   s.source, s.published,
                   CASE WHEN g.id IS NULL THEN 0 ELSE 1 END has_script
            FROM production_queue q
            JOIN stories s ON s.id = q.story_id
            LEFT JOIN generated_stories g ON g.story_id = s.id
            {where}
            ORDER BY CASE WHEN q.overall_score IS NULL THEN 1 ELSE 0 END,
                     q.overall_score DESC, q.selected_at DESC, q.id DESC LIMIT 300
        """, params)}

    if action == "scripts":
        return {"items": query_all("""
            SELECT g.*, s.url, s.source, s.published
            FROM generated_stories g JOIN stories s ON s.id = g.story_id
            ORDER BY g.id DESC LIMIT 300
        """)}

    if action == "select_articles":
        ids = [int(value) for value in cfg.get("ids", [])]
        inserted = 0
        current_rank = query_all("SELECT COALESCE(MAX(rank), 0) AS max_rank FROM production_queue")[0]["max_rank"]
        for rank, story_id in enumerate(ids, int(current_rank or 0) + 1):
            rows = query_all(
                "SELECT id, popularity_score, overall_score FROM stories WHERE id = ? AND ai_score IS NOT NULL",
                (story_id,),
            )
            if rows and queue_selected_topic(
                story_id,
                rank,
                rows[0].get("popularity_score") or 0,
                rows[0].get("overall_score") or rows[0].get("ai_score") or 0,
            ):
                __import__("database.database", fromlist=["get_connection"]).get_connection().execute if False else None
                inserted += 1
        return {"inserted": inserted, "requested": len(ids)}

    if action == "remove_queue_item":
        from database.database import remove_queue_item
        return remove_queue_item(cfg.get("queueId"))

    if action == "set_queue_status":
        queue_id = int(cfg["queueId"])
        status = str(cfg["status"]).upper()
        if status not in {"SELECTED", "WRITTEN", "RENDERED", "PUBLISHED", "FAILED"}:
            raise ValueError("Status tidak valid.")
        mark_queue_status(queue_id, status)
        return {"queueId": queue_id, "status": status}

    if action == "research":
        return run_research(cfg)
    if action == "generate":
        return run_generate(cfg)
    if action == "generate_bulk":
        return run_generate_bulk(cfg)
    if action == "delete_story":
        from database.database import delete_story
        return delete_story(cfg.get("storyId"))

    if action == "ai_status":
        key = str(os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            return {"connected": False, "status": "missing_key", "message": "OPENAI_API_KEY belum dikonfigurasi."}
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            client.models.list()
            return {"connected": True, "status": "connected", "message": "OpenAI API terhubung."}
        except Exception as exc:
            message = str(exc)
            status = "error"
            if "401" in message or "invalid_api_key" in message.lower() or "incorrect api key" in message.lower():
                status = "invalid_key"
                message = "OpenAI API key tidak valid."
            elif "429" in message or "quota" in message.lower() or "rate limit" in message.lower():
                status = "quota_or_rate_limit"
                message = "OpenAI terhubung, tetapi quota/rate limit bermasalah."
            return {"connected": False, "status": status, "message": message[:300]}

    if action == "content_settings":
        return get_content_settings()
    if action == "save_content_settings":
        return save_content_settings(cfg)
    if action == "avatars":
        from database.database import list_avatars
        return {"items": list_avatars()}
    if action == "save_avatar":
        from database.database import save_avatar
        return save_avatar(cfg)
    if action == "music":
        from database.database import list_music
        return {"items": list_music()}
    if action == "save_music":
        from database.database import save_music
        return save_music(cfg)
    if action == "templates":
        from database.database import list_templates
        return {"items": list_templates()}
    if action == "save_template":
        from database.database import save_template
        return save_template(cfg)
    if action == "system":
        database_path = ROOT / "database" / "horror.db"
        return {
            "databasePath": str(database_path.resolve()),
            "databaseExists": database_path.exists(),
            "apiKeyConfigured": bool(os.getenv("OPENAI_API_KEY")),
            "projectRoot": str(ROOT),
        }

    raise ValueError(f"Action tidak dikenal: {action}")


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        # Keep ordinary module print() calls away from stdout so Node.js receives
        # only JSON-line protocol messages. emit() still writes to saved stdout.
        with redirect_stdout(sys.stderr):
            result = run_action(payload.get("action", ""), payload.get("config", {}))
        emit("result", data=result)
    except Exception as exc:
        emit("error", message=str(exc), traceback=traceback.format_exc())
        sys.exit(1)
