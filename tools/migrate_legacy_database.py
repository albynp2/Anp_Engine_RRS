"""Safely merge an older Horror Content Factory SQLite database into database/horror.db.

Usage:
  python tools/migrate_legacy_database.py "C:\\path\\to\\old\\horror.db"
  python tools/migrate_legacy_database.py --source "..\\horror.db"

The source database is read-only and is never modified or deleted.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
TARGET_DB = ROOT / "database" / "horror.db"


def emit(message: str) -> None:
    print(message, flush=True)


def tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}


def first(row: dict, *names, default=None):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def rows_as_dicts(conn: sqlite3.Connection, table: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"').fetchall()]


def count(conn, table):
    if table not in tables(conn):
        return 0
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def migrate(source_path: Path) -> None:
    source_path = source_path.expanduser().resolve()
    target_path = TARGET_DB.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Database sumber tidak ditemukan: {source_path}")
    if source_path == target_path:
        raise ValueError("Database sumber dan target sama. Pilih database lama yang berbeda.")

    emit("=" * 72)
    emit("HORROR CONTENT FACTORY — LEGACY DATABASE MIGRATION")
    emit("=" * 72)
    emit(f"SOURCE : {source_path}")
    emit(f"TARGET : {target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    # Import app schema and upgrade any older target schema first.
    sys.path.insert(0, str(ROOT))
    from database.database import create_database
    create_database()
    target = sqlite3.connect(target_path)
    target.row_factory = sqlite3.Row
    target.execute("PRAGMA foreign_keys=ON")

    try:
        source_tables = tables(source)
        if not source_tables.intersection({"stories", "articles", "news"}):
            raise ValueError("Database sumber tidak punya tabel stories/articles/news yang dikenali.")

        backup = target_path.with_name(f"horror_backup_before_legacy_migration_{datetime.now():%Y%m%d_%H%M%S}.db")
        if target_path.exists() and target_path.stat().st_size:
            target.commit()
            target.close()
            shutil.copy2(target_path, backup)
            emit(f"BACKUP : {backup}")
            target = sqlite3.connect(target_path)
            target.row_factory = sqlite3.Row
            target.execute("PRAGMA foreign_keys=ON")

        before = {t: count(target, t) for t in ("stories", "production_queue", "generated_stories")}
        emit(f"TARGET BEFORE: {before}")
        source_conn = source
        story_table = next((t for t in ("stories", "articles", "news") if t in source_tables), None)
        source_stories = rows_as_dicts(source_conn, story_table)
        story_map: dict[object, int] = {}
        inserted_stories = skipped_stories = 0

        target.execute("BEGIN")
        for row in tqdm(source_stories, desc="Migrating stories", unit="row"):
            old_id = first(row, "id", "story_id", "article_id", "news_id")
            title = first(row, "title", "headline", "name", default="(Untitled legacy article)")
            url = first(row, "url", "link", "article_url")
            source_name = first(row, "source", "source_name", "publisher", "domain", default="")
            published = first(row, "published", "published_at", "pub_date", "date")
            status = str(first(row, "status", "story_status", default="NEW") or "NEW").upper()
            created_at = first(row, "created_at", "created", "inserted_at")
            used_at = first(row, "used_at")
            if not url:
                # Keep legacy records without a URL importable and unique.
                url = f"legacy://{story_table}/{old_id if old_id is not None else abs(hash((title, source_name, published)))}"
            existing = target.execute("SELECT id FROM stories WHERE url=?", (url,)).fetchone()
            if existing:
                new_id = existing[0]
                skipped_stories += 1
            else:
                target.execute("""INSERT INTO stories(title,url,source,published,status,created_at,used_at)
                    VALUES(?,?,?,?,?,?,?)""", (title, url, source_name, published, status, created_at, used_at))
                new_id = target.execute("SELECT last_insert_rowid()").fetchone()[0]
                inserted_stories += 1
            if old_id is not None:
                story_map[old_id] = new_id

        # Map legacy story references using the migrated URL when the old ID was not directly mapped.
        def mapped_story_id(row):
            old_sid = first(row, "story_id", "article_id", "news_id")
            if old_sid in story_map:
                return story_map[old_sid]
            if old_sid is not None and story_table:
                old_story = next((x for x in source_stories if first(x, "id", "story_id", "article_id", "news_id") == old_sid), None)
                if old_story:
                    old_url = first(old_story, "url", "link", "article_url")
                    if old_url:
                        found = target.execute("SELECT id FROM stories WHERE url=?", (old_url,)).fetchone()
                        if found:
                            return found[0]
            return None

        queue_table = next((t for t in ("production_queue", "queue", "story_queue") if t in source_tables), None)
        inserted_queue = skipped_queue = invalid_queue = 0
        if queue_table:
            source_queue = rows_as_dicts(source_conn, queue_table)
            for row in tqdm(source_queue, desc="Migrating production queue", unit="row"):
                sid = mapped_story_id(row)
                if sid is None:
                    invalid_queue += 1
                    continue
                exists = target.execute("SELECT id FROM production_queue WHERE story_id=?", (sid,)).fetchone()
                if exists:
                    skipped_queue += 1
                    continue
                target.execute("""INSERT INTO production_queue(story_id,rank,research_popularity,overall_score,selected_at,status)
                    VALUES(?,?,?,?,?,?)""", (
                    sid,
                    first(row, "rank", "position", "queue_rank"),
                    first(row, "research_popularity", "popularity_score", "popularity"),
                    first(row, "overall_score", "score", "ai_score"),
                    first(row, "selected_at", "created_at", "queued_at"),
                    str(first(row, "status", "queue_status", default="SELECTED") or "SELECTED").upper()
                ))
                inserted_queue += 1

        generated_table = next((t for t in ("generated_stories", "written_stories", "scripts", "story_scripts") if t in source_tables), None)
        inserted_scripts = skipped_scripts = invalid_scripts = 0
        if generated_table:
            source_scripts = rows_as_dicts(source_conn, generated_table)
            for row in tqdm(source_scripts, desc="Migrating generated stories", unit="row"):
                sid = mapped_story_id(row)
                if sid is None:
                    invalid_scripts += 1
                    continue
                if target.execute("SELECT id FROM generated_stories WHERE story_id=?", (sid,)).fetchone():
                    skipped_scripts += 1
                    continue
                target.execute("""INSERT INTO generated_stories(story_id,title,hook,script,ending,caption,hashtags,source_basis,story_type,fact_boundary,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                    sid,
                    first(row, "title", "script_title", default=""),
                    first(row, "hook", "opening_hook", default=""),
                    first(row, "script", "body", "narrative", "content", default=""),
                    first(row, "ending", "closing", default=""),
                    first(row, "caption", "description", default=""),
                    first(row, "hashtags", "tags", default=""),
                    first(row, "source_basis"),
                    first(row, "story_type"),
                    first(row, "fact_boundary"),
                    first(row, "created_at", "generated_at", "written_at")
                ))
                inserted_scripts += 1

        target.commit()
        after = {t: count(target, t) for t in ("stories", "production_queue", "generated_stories")}
        emit("\n" + "=" * 72)
        emit("MIGRATION SUMMARY")
        emit("=" * 72)
        emit(f"stories: source={len(source_stories)}, inserted={inserted_stories}, skipped={skipped_stories}")
        emit(f"production_queue: inserted={inserted_queue}, skipped={skipped_queue}, invalid_links={invalid_queue}")
        emit(f"generated_stories: inserted={inserted_scripts}, skipped={skipped_scripts}, invalid_links={invalid_scripts}")
        emit(f"TARGET BEFORE: {before}")
        emit(f"TARGET AFTER : {after}")
        emit("Migration selesai. Database sumber tidak diubah atau dihapus.")
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def main():
    parser = argparse.ArgumentParser(description="Merge legacy Horror Content Factory SQLite DB into the current dashboard schema.")
    parser.add_argument("source", nargs="?", help="Path ke database SQLite lama")
    parser.add_argument("--source", dest="source_flag", help="Path ke database SQLite lama")
    args = parser.parse_args()
    raw = args.source_flag or args.source
    if not raw:
        default = ROOT / "horror.db"
        if default.exists():
            raw = str(default)
            emit(f"Source tidak diberikan. Menggunakan database lama default: {default}")
        else:
            parser.error("Masukkan path database lama, contoh: python tools/migrate_legacy_database.py ..\\horror.db")
    migrate(Path(raw))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit(f"\nERROR: {exc}")
        raise SystemExit(1)
