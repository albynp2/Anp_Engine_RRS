"""Shared database API for Horror Content Factory."""

from .database import (
    DB_PATH,
    create_database,
    get_connection,
    save_story,
    story_exists,
    get_story_id_by_url,
    get_story_status,
    queue_selected_topic,
    get_next_queue_item,
    get_queue_items,
    mark_queue_status,
    get_queue_counts,
    save_generated_story,
    story_already_written,
    get_new_stories,
)

__all__ = [
    "DB_PATH", "create_database", "get_connection", "save_story",
    "story_exists", "get_story_id_by_url", "get_story_status",
    "queue_selected_topic", "get_next_queue_item", "get_queue_items",
    "mark_queue_status", "get_queue_counts", "save_generated_story",
    "story_already_written", "get_new_stories",
]
