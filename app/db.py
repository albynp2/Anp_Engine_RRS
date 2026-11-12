"""SQLite layer. Skema kompatibel dengan horror.db versi lama (kolom baru ditambah otomatis)."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config

STAGES = ["NEW", "QUEUED", "WRITTEN", "RENDERING", "RENDERED", "PUBLISHED"]


@contextmanager
def conn():
    c = sqlite3.connect(str(config.DB_PATH), timeout=30)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def q_all(sql: str, params: Iterable = ()) -> List[Dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, tuple(params)).fetchall()]


def q_one(sql: str, params: Iterable = ()) -> Optional[Dict[str, Any]]:
    with conn() as c:
        r = c.execute(sql, tuple(params)).fetchone()
        return dict(r) if r else None


def execute(sql: str, params: Iterable = ()) -> int:
    with conn() as c:
        cur = c.execute(sql, tuple(params))
        return cur.lastrowid


def _ensure_columns(c, table: str, cols: Dict[str, str]):
    have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, decl in cols.items():
        if name not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


VIEW_SQL = """
CREATE VIEW v_stories AS
SELECT s.*,
  (SELECT COUNT(*) FROM production_queue q WHERE q.story_id = s.id) AS in_queue,
  (SELECT COUNT(*) FROM generated_stories g WHERE g.story_id = s.id) AS has_script,
  (SELECT COUNT(*) FROM videos v WHERE v.story_id = s.id AND v.status = 'DONE') AS videos_done,
  (SELECT COUNT(*) FROM videos v WHERE v.story_id = s.id AND v.status = 'RENDERING') AS videos_rendering,
  (SELECT COUNT(*) FROM videos v WHERE v.story_id = s.id AND v.status = 'DONE'
        AND v.published_at IS NOT NULL) AS videos_published,
  CASE
    WHEN (SELECT COUNT(*) FROM videos v WHERE v.story_id = s.id AND v.status = 'DONE'
          AND v.published_at IS NOT NULL) > 0 THEN 'PUBLISHED'
    WHEN (SELECT COUNT(*) FROM videos v WHERE v.story_id = s.id AND v.status = 'DONE') > 0 THEN 'RENDERED'
    WHEN (SELECT COUNT(*) FROM videos v WHERE v.story_id = s.id AND v.status = 'RENDERING') > 0 THEN 'RENDERING'
    WHEN (SELECT COUNT(*) FROM generated_stories g WHERE g.story_id = s.id) > 0 THEN 'WRITTEN'
    WHEN (SELECT COUNT(*) FROM production_queue q WHERE q.story_id = s.id) > 0 THEN 'QUEUED'
    ELSE 'NEW'
  END AS stage
FROM stories s
"""


def init_db():
    config.ensure_dirs()
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, url TEXT UNIQUE, source TEXT,
            published TEXT, status TEXT DEFAULT 'NEW',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, used_at TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS production_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT, story_id INTEGER NOT NULL UNIQUE, rank INTEGER,
            research_popularity REAL, overall_score REAL,
            selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'SELECTED')""")
        c.execute("""CREATE TABLE IF NOT EXISTS generated_stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, story_id INTEGER NOT NULL UNIQUE, title TEXT,
            hook TEXT, script TEXT, ending TEXT, caption TEXT, hashtags TEXT, source_basis TEXT,
            story_type TEXT, fact_boundary TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS content_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1), config_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS research_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT, params_json TEXT,
            found INTEGER DEFAULT 0, kept INTEGER DEFAULT 0, scored_by_ai INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            voice TEXT DEFAULT 'id-ID-ArdiNeural', height_pct REAL DEFAULT 0.38,
            mouth_x REAL DEFAULT 0.5, mouth_y REAL DEFAULT 0.62, mouth_w REAL DEFAULT 0.16,
            frame_style TEXT DEFAULT 'none', notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS music_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, filename TEXT NOT NULL,
            source TEXT, license_note TEXT, builtin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, story_id INTEGER NOT NULL, platform TEXT,
            character_id INTEGER, status TEXT DEFAULT 'RENDERING', path TEXT, duration REAL,
            error TEXT, options_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, published_at TIMESTAMP)""")

        _ensure_columns(c, "stories", {
            "popularity_score": "REAL", "overall_score": "REAL", "coverage_count": "INTEGER",
            "unique_source_count": "INTEGER", "query_count": "INTEGER",
            "ai_score": "REAL", "ai_reason": "TEXT", "published_date": "TEXT",
            "content": "TEXT", "content_status": "TEXT", "content_url": "TEXT",
            "cluster_json": "TEXT", "run_id": "INTEGER", "mode": "TEXT", "query": "TEXT"})
        _ensure_columns(c, "production_queue", {
            "research_popularity": "REAL", "overall_score": "REAL", "rank": "INTEGER",
            "status": "TEXT DEFAULT 'SELECTED'", "selected_at": "TIMESTAMP"})
        _ensure_columns(c, "generated_stories", {
            "segments_json": "TEXT", "fact_warnings": "TEXT", "updated_at": "TIMESTAMP"})
        c.execute("CREATE INDEX IF NOT EXISTS idx_stories_score ON stories(overall_score)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_videos_story ON videos(story_id)")
        c.execute("DROP VIEW IF EXISTS v_stories")
        c.execute(VIEW_SQL)
        # video yang menggantung 'RENDERING' karena app mati -> FAILED
        c.execute("UPDATE videos SET status='FAILED', error='Dihentikan (app restart)' "
                  "WHERE status='RENDERING'")


# ------------------------------------------------------------------ stories
def upsert_candidate(c: dict) -> Tuple[int, bool]:
    """Simpan kandidat hasil riset. Kembalikan (story_id, is_new)."""
    row = q_one("SELECT id FROM stories WHERE url = ?", (c["url"],))
    fields = {
        "popularity_score": c.get("popularity_score"), "ai_score": c.get("ai_score"),
        "ai_reason": c.get("ai_reason"), "overall_score": c.get("overall_score"),
        "coverage_count": c.get("coverage_count"),
        "unique_source_count": c.get("unique_source_count"),
        "query_count": c.get("query_count"), "cluster_json": c.get("cluster_json"),
        "run_id": c.get("run_id"), "mode": c.get("mode"), "query": c.get("query"),
    }
    if row:
        sets = ", ".join(f"{k}=?" for k in fields)
        execute(f"UPDATE stories SET {sets} WHERE id=?", list(fields.values()) + [row["id"]])
        return row["id"], False
    cols = ["title", "url", "source", "published", "published_date"] + list(fields)
    vals = [c["title"], c["url"], c.get("source"), c.get("published"),
            c.get("published_date")] + list(fields.values())
    sid = execute(f"INSERT INTO stories ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
    return sid, True


def get_story(story_id: int) -> Optional[dict]:
    return q_one("SELECT * FROM v_stories WHERE id = ?", (story_id,))


def list_articles(page=1, limit=25, search="", stage="NEW", date_from="", date_to="") -> dict:
    where, params = [], []
    if stage and stage != "ALL":
        where.append("stage = ?")
        params.append(stage)
    if search:
        where.append("(title LIKE ? OR source LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    day = "COALESCE(published_date, date(created_at, '+7 hours'))"
    if date_from:
        where.append(f"{day} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{day} <= ?")
        params.append(date_to)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = q_one(f"SELECT COUNT(*) n FROM v_stories {w}", params)["n"]
    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))
    items = q_all(
        f"""SELECT id, title, url, source, published, published_date, popularity_score, ai_score,
                   ai_reason, overall_score, coverage_count, unique_source_count, query_count,
                   content_status, stage, created_at
            FROM v_stories {w}
            ORDER BY overall_score DESC, popularity_score DESC, id DESC
            LIMIT ? OFFSET ?""", params + [limit, (page - 1) * limit])
    return {"items": items, "total": total, "page": page, "limit": limit}


# ------------------------------------------------------------------ queue
def queue_add(ids: List[int]) -> int:
    inserted = 0
    with conn() as c:
        for sid in ids:
            s = c.execute("SELECT id, popularity_score, overall_score FROM stories WHERE id=?",
                          (sid,)).fetchone()
            if not s:
                continue
            exists = c.execute("SELECT 1 FROM production_queue WHERE story_id=?", (sid,)).fetchone()
            if exists:
                continue
            rank = (c.execute("SELECT COALESCE(MAX(rank),0)+1 FROM production_queue").fetchone()[0])
            c.execute("""INSERT INTO production_queue
                (story_id, rank, research_popularity, overall_score, status)
                VALUES (?,?,?,?, 'SELECTED')""",
                      (sid, rank, s["popularity_score"], s["overall_score"]))
            inserted += 1
    return inserted


def queue_list() -> List[dict]:
    return q_all("""
        SELECT q.id AS queue_id, q.story_id, q.rank, q.selected_at, s.title, s.source, s.url,
               s.overall_score, s.popularity_score, s.ai_score, s.content_status, s.stage,
               (SELECT LENGTH(content) FROM stories x WHERE x.id = s.id) AS content_len
        FROM production_queue q JOIN v_stories s ON s.id = q.story_id
        ORDER BY (s.stage = 'QUEUED') DESC, q.rank ASC""")


def queue_remove(story_id: int) -> bool:
    s = get_story(story_id)
    if not s or s["stage"] != "QUEUED":
        return False
    execute("DELETE FROM production_queue WHERE story_id=?", (story_id,))
    return True


def sync_queue_status(story_id: int):
    s = get_story(story_id)
    if not s:
        return
    m = {"QUEUED": "SELECTED", "WRITTEN": "WRITTEN", "RENDERING": "WRITTEN",
         "RENDERED": "RENDERED", "PUBLISHED": "PUBLISHED"}
    if s["stage"] in m:
        execute("UPDATE production_queue SET status=? WHERE story_id=?", (m[s["stage"]], story_id))


# ------------------------------------------------------------------ scripts
def save_script(story_id: int, d: dict):
    now = config.utc_now_str()
    execute("""INSERT INTO generated_stories
        (story_id, title, hook, script, ending, caption, hashtags, source_basis, story_type,
         fact_boundary, segments_json, fact_warnings, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(story_id) DO UPDATE SET
          title=excluded.title, hook=excluded.hook, script=excluded.script, ending=excluded.ending,
          caption=excluded.caption, hashtags=excluded.hashtags, source_basis=excluded.source_basis,
          story_type=excluded.story_type, fact_boundary=excluded.fact_boundary,
          segments_json=excluded.segments_json, fact_warnings=excluded.fact_warnings,
          updated_at=excluded.updated_at""",
            (story_id, d.get("title"), d.get("hook"), d.get("script"), d.get("ending"),
             d.get("caption"), d.get("hashtags"), d.get("source_basis"), d.get("story_type"),
             d.get("fact_boundary"), json.dumps(d.get("segments", []), ensure_ascii=False),
             json.dumps(d.get("fact_warnings", []), ensure_ascii=False), now, now))
    sync_queue_status(story_id)


def _script_row(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    for k in ("segments_json", "fact_warnings"):
        target = k.replace("_json", "")
        try:
            val = json.loads(r.get(k) or "[]")
        except Exception:
            val = []
        r[target] = val
        if target != k:
            r.pop(k, None)
    return r


def get_script(story_id: int) -> Optional[dict]:
    return _script_row(q_one("""
        SELECT g.*, s.source, s.url, s.published, s.stage, s.title AS news_title
        FROM generated_stories g JOIN v_stories s ON s.id = g.story_id WHERE g.story_id = ?""",
                             (story_id,)))


def list_scripts() -> List[dict]:
    rows = q_all("""
        SELECT g.story_id, g.title, g.hook, g.created_at, g.updated_at, g.fact_warnings,
               g.segments_json, s.source, s.url, s.stage, s.title AS news_title
        FROM generated_stories g JOIN v_stories s ON s.id = g.story_id
        ORDER BY g.updated_at DESC, g.id DESC""")
    out = []
    for r in rows:
        r = _script_row(r)
        r["segment_count"] = len(r.get("segments", []))
        r["words"] = sum(len((x.get("text") or "").split()) for x in r.get("segments", []))
        r.pop("segments", None)
        out.append(r)
    return out


def delete_script(story_id: int):
    execute("DELETE FROM generated_stories WHERE story_id=?", (story_id,))
    sync_queue_status(story_id)
    execute("UPDATE production_queue SET status='SELECTED' WHERE story_id=? "
            "AND NOT EXISTS (SELECT 1 FROM generated_stories WHERE story_id=?)", (story_id, story_id))


# ------------------------------------------------------------------ videos
def create_video(story_id: int, platform: str, character_id, options: dict) -> int:
    vid = execute("""INSERT INTO videos (story_id, platform, character_id, status, options_json)
                     VALUES (?,?,?, 'RENDERING', ?)""",
                  (story_id, platform, character_id, json.dumps(options, default=str)))
    sync_queue_status(story_id)
    return vid


def finish_video(video_id: int, ok: bool, path: str = None, duration: float = None, error: str = None):
    execute("UPDATE videos SET status=?, path=?, duration=?, error=? WHERE id=?",
            ("DONE" if ok else "FAILED", path, duration, error, video_id))
    v = q_one("SELECT story_id FROM videos WHERE id=?", (video_id,))
    if v:
        sync_queue_status(v["story_id"])


def list_videos(story_id: int = None) -> List[dict]:
    sql = """SELECT v.id, v.story_id, v.platform, v.character_id, v.status, v.path, v.duration,
                    v.error, v.created_at, v.published_at, g.title, ch.name AS character_name
             FROM videos v LEFT JOIN generated_stories g ON g.story_id = v.story_id
             LEFT JOIN characters ch ON ch.id = v.character_id"""
    params: list = []
    if story_id:
        sql += " WHERE v.story_id = ?"
        params.append(story_id)
    return q_all(sql + " ORDER BY v.id DESC LIMIT 200", params)


def set_video_published(video_id: int, published: bool) -> bool:
    v = q_one("SELECT story_id, status FROM videos WHERE id=?", (video_id,))
    if not v or v["status"] != "DONE":
        return False
    execute("UPDATE videos SET published_at=? WHERE id=?",
            (config.utc_now_str() if published else None, video_id))
    sync_queue_status(v["story_id"])
    return True


def delete_video(video_id: int) -> Optional[str]:
    v = q_one("SELECT story_id, path FROM videos WHERE id=?", (video_id,))
    if not v:
        return None
    execute("DELETE FROM videos WHERE id=?", (video_id,))
    sync_queue_status(v["story_id"])
    return v["path"]


# ------------------------------------------------------------------ settings
def get_content_settings() -> dict:
    r = q_one("SELECT config_json, updated_at FROM content_settings WHERE id=1")
    if not r:
        return {"config": {}, "updatedAt": None}
    try:
        return {"config": json.loads(r["config_json"]), "updatedAt": r["updated_at"]}
    except Exception:
        return {"config": {}, "updatedAt": r["updated_at"]}


def put_content_settings(cfg: dict):
    execute("""INSERT INTO content_settings (id, config_json, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json,
               updated_at=CURRENT_TIMESTAMP""", (json.dumps(cfg, ensure_ascii=False),))


# ------------------------------------------------------------------ dashboard
def dashboard(days: int = 14) -> dict:
    t = q_one("""SELECT
        COUNT(*) AS articles,
        SUM(stage='NEW') AS new, SUM(stage='QUEUED') AS queued, SUM(stage='WRITTEN') AS written_waiting,
        SUM(stage='RENDERING') AS rendering, SUM(stage='RENDERED') AS rendered,
        SUM(stage='PUBLISHED') AS published
        FROM v_stories""") or {}
    t = {k: int(v or 0) for k, v in t.items()}
    scripts = q_one("SELECT COUNT(*) n FROM generated_stories")["n"]
    totals = {
        "articles": t["articles"],
        "scriptsWritten": scripts,
        "videosDone": t["rendered"] + t["published"],
        "published": t["published"],
        "inProgress": t["queued"] + t["written_waiting"] + t["rendering"],
        "stages": {"NEW": t["new"], "QUEUED": t["queued"], "WRITTEN": t["written_waiting"],
                   "RENDERING": t["rendering"], "RENDERED": t["rendered"],
                   "PUBLISHED": t["published"]},
    }

    today = config.today_local()
    start = today - timedelta(days=days - 1)
    buckets = {(start + timedelta(days=i)).isoformat(): {"articles": 0, "scripts": 0, "published": 0}
               for i in range(days)}
    # ambil sedikit lebih banyak (UTC) lalu bucket per hari WIB
    since = (start - timedelta(days=1)).isoformat()

    def fill(sql, key):
        for r in q_all(sql, (since,)):
            dt = config.utc_str_to_local(r["ts"])
            if dt and dt.date().isoformat() in buckets:
                buckets[dt.date().isoformat()][key] += 1

    fill("SELECT created_at AS ts FROM stories WHERE created_at >= ?", "articles")
    fill("SELECT created_at AS ts FROM generated_stories WHERE created_at >= ?", "scripts")
    fill("SELECT published_at AS ts FROM videos WHERE published_at IS NOT NULL AND published_at >= ?",
         "published")
    activity = [{"day": d, **v} for d, v in buckets.items()]

    recent = q_all("""SELECT id, title, source, stage, overall_score, created_at
                      FROM v_stories ORDER BY id DESC LIMIT 8""")
    for r in recent:
        dt = config.utc_str_to_local(r["created_at"])
        r["created_local"] = dt.strftime("%d %b %Y %H:%M") if dt else ""
    last_run = q_one("SELECT * FROM research_runs ORDER BY id DESC LIMIT 1")
    return {"totals": totals, "activity": activity, "recent": recent, "lastRun": last_run,
            "today": today.isoformat()}
