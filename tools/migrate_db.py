"""Backward-compatible entry point for legacy database migration.

Usage from project root:
    python tools/migrate_db.py "C:\\path\\to\\old\\horror.db"

If no path is supplied, PROJECT/horror.db is used when it exists.
"""
from migrate_legacy_database import main

if __name__ == "__main__":
    main()
