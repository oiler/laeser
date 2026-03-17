import sqlite3
from datetime import datetime, timezone
from typing import Optional

from db.connection import get_db


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def create_source(
    name: str,
    type: str,
    folder_name: str,
    feed_url: Optional[str] = None,
    archive_mode: Optional[str] = None,
) -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO sources (name, type, feed_url, archive_mode, folder_name) VALUES (?, ?, ?, ?, ?)",
            (name, type, feed_url, archive_mode, folder_name),
        )
        return _row(conn.execute("SELECT * FROM sources WHERE id = ?", (cursor.lastrowid,)).fetchone())


def get_source(source_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return _row(row) if row else None


def list_sources() -> list[dict]:
    with get_db() as conn:
        return [_row(r) for r in conn.execute("SELECT * FROM sources ORDER BY name").fetchall()]


def list_sources_with_unread_count() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.*, COUNT(CASE WHEN e.read_at IS NULL THEN 1 END) AS unread_count
            FROM sources s
            LEFT JOIN entries e ON e.source_id = s.id
            GROUP BY s.id
            ORDER BY s.name
            """
        ).fetchall()
        return [_row(r) for r in rows]


def delete_source(source_id: int) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


def update_source_fetch_status(source_id: int, error: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE sources SET last_fetched_at = ?, last_fetch_error = ? WHERE id = ?",
            (now, error, source_id),
        )
