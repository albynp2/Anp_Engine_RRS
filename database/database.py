import sqlite3
from pathlib import Path


# ============================================================
# DATABASE PATH
# ============================================================

DATABASE_DIR = Path(__file__).resolve().parent

DB_PATH = DATABASE_DIR / "horror.db"


def get_connection():

    return sqlite3.connect(DB_PATH)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def _ensure_columns(cursor, table, columns):
    """Add missing columns to an existing SQLite table without dropping data."""
    existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, sql_type in columns.items():
        if name not in existing:
            print(f"[DB MIGRATION] Adding {table}.{name} ({sql_type})")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def create_database():
    """Create the dashboard's canonical schema and safely upgrade older schemas."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT UNIQUE,
                source TEXT,
                published TEXT,
                status TEXT DEFAULT 'NEW',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_at TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS production_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL UNIQUE,
                rank INTEGER,
                research_popularity REAL,
                overall_score REAL,
                selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'SELECTED',
                FOREIGN KEY(story_id) REFERENCES stories(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generated_stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL UNIQUE,
                title TEXT,
                hook TEXT,
                script TEXT,
                ending TEXT,
                caption TEXT,
                hashtags TEXT,
                source_basis TEXT,
                story_type TEXT,
                fact_boundary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(story_id) REFERENCES stories(id)
            )
        """)

        # Schema upgrades for databases created by older versions of the app.
        _ensure_columns(cursor, "stories", {
            "title": "TEXT", "url": "TEXT", "source": "TEXT", "published": "TEXT",
            "status": "TEXT DEFAULT 'NEW'", "created_at": "TIMESTAMP",
            "used_at": "TIMESTAMP", "popularity_score": "REAL", "overall_score": "REAL",
            "coverage_count": "INTEGER", "unique_source_count": "INTEGER", "query_count": "INTEGER"
        })
        _ensure_columns(cursor, "production_queue", {
            "story_id": "INTEGER", "rank": "INTEGER", "research_popularity": "REAL",
            "overall_score": "REAL", "selected_at": "TIMESTAMP",
            "status": "TEXT DEFAULT 'SELECTED'"
        })
        _ensure_columns(cursor, "generated_stories", {
            "story_id": "INTEGER", "title": "TEXT", "hook": "TEXT", "script": "TEXT",
            "ending": "TEXT", "caption": "TEXT", "hashtags": "TEXT",
            "source_basis": "TEXT", "story_type": "TEXT", "fact_boundary": "TEXT",
            "created_at": "TIMESTAMP"
        })

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                config_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# STORY FUNCTIONS
# ============================================================

def save_story(story):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO stories
        (
            title,
            url,
            source,
            published
        )
        VALUES (?, ?, ?, ?)
    """, (
        story["title"],
        story["url"],
        story["source"],
        story["published"]
    ))

    conn.commit()
    conn.close()


def story_exists(url):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM stories
        WHERE url = ?
    """, (url,))

    result = cursor.fetchone()

    conn.close()

    return result is not None


def get_story_id_by_url(url):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM stories
        WHERE url = ?
    """, (url,))

    result = cursor.fetchone()

    conn.close()

    if result:
        return result[0]

    return None


def get_story_status(url):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status
        FROM stories
        WHERE url = ?
    """, (url,))

    result = cursor.fetchone()

    conn.close()

    if result:
        return result[0]

    return None


# ============================================================
# PRODUCTION QUEUE
# ============================================================

def queue_selected_topic(
    story_id,
    rank,
    research_popularity,
    overall_score
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO production_queue
        (
            story_id,
            rank,
            research_popularity,
            overall_score
        )
        VALUES (?, ?, ?, ?)
    """, (
        story_id,
        rank,
        research_popularity,
        overall_score
    ))

    inserted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return inserted


def get_next_queue_item():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            q.id,
            q.story_id,
            q.rank,
            q.research_popularity,
            q.overall_score,

            s.title,
            s.url,
            s.source,
            s.published

        FROM production_queue q

        JOIN stories s
            ON q.story_id = s.id

        WHERE q.status = 'SELECTED'

        ORDER BY
            q.rank ASC,
            q.id ASC

        LIMIT 1
    """)

    row = cursor.fetchone()

    conn.close()

    if not row:
        return None

    return {
        "queue_id": row[0],
        "story_id": row[1],
        "rank": row[2],
        "research_popularity": row[3],
        "overall_score": row[4],
        "title": row[5],
        "url": row[6],
        "source": row[7],
        "published": row[8]
    }


def get_queue_items(
    status="SELECTED",
    limit=10
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            q.id,
            q.story_id,
            q.rank,
            q.research_popularity,
            q.overall_score,

            s.title,
            s.url,
            s.source,
            s.published

        FROM production_queue q

        JOIN stories s
            ON q.story_id = s.id

        WHERE q.status = ?

        ORDER BY
            q.rank ASC,
            q.id ASC

        LIMIT ?
    """, (
        status,
        limit
    ))

    rows = cursor.fetchall()

    conn.close()

    results = []

    for row in rows:

        results.append({

            "queue_id": row[0],
            "story_id": row[1],
            "rank": row[2],
            "research_popularity": row[3],
            "overall_score": row[4],
            "title": row[5],
            "url": row[6],
            "source": row[7],
            "published": row[8]
        })

    return results


def mark_queue_status(
    queue_id,
    status
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE production_queue

        SET status = ?

        WHERE id = ?
    """, (
        status,
        queue_id
    ))

    conn.commit()
    conn.close()


def get_queue_counts():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            status,
            COUNT(*)

        FROM production_queue

        GROUP BY status
    """)

    rows = cursor.fetchall()

    conn.close()

    counts = {}

    for status, count in rows:
        counts[status] = count

    return counts


# ============================================================
# GENERATED STORIES
# ============================================================

def save_generated_story(
    story_id,
    result
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO generated_stories
        (
            story_id,
            title,
            hook,
            script,
            ending,
            caption,
            hashtags,
            source_basis,
            story_type,
            fact_boundary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        story_id,
        result.get("title", ""),
        result.get("hook", ""),
        result.get("script", ""),
        result.get("ending", ""),
        result.get("caption", ""),
        ",".join(result.get("hashtags", [])) if isinstance(result.get("hashtags", []), list) else str(result.get("hashtags", "")),
        result.get("source_basis", ""),
        result.get("story_type", ""),
        result.get("fact_boundary", "")
    ))

    conn.commit()
    conn.close()


def story_already_written(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM generated_stories
        WHERE story_id = ?
    """, (story_id,))

    result = cursor.fetchone()

    conn.close()

    return result is not None

# ============================================================
# STORIES FOR TESTING / DEVELOPMENT
# ============================================================

def get_new_stories(limit=30):
    """Return NEW stories in a stable dictionary format."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, url, source, published, status
            FROM stories
            WHERE status = 'NEW'
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [
            {
                "story_id": row[0],
                "id": row[0],
                "title": row[1],
                "url": row[2],
                "source": row[3],
                "published": row[4],
                "status": row[5],
            }
            for row in rows
        ]
    finally:
        conn.close()
