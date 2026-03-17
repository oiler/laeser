import sqlite3
from datetime import datetime, timezone
from typing import Optional

from db.connection import get_db

_SELECT = """
    SELECT e.*, s.name AS source_name, s.folder_name AS source_folder
    FROM entries e
    JOIN sources s ON s.id = e.source_id
"""


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def create_entry(
    source_id: int,
    title: str,
    url: Optional[str] = None,
    author: Optional[str] = None,
    description: Optional[str] = None,
    pub_date: Optional[str] = None,
    duration: Optional[str] = None,
) -> dict:
    """Create entry; silently returns existing row on duplicate URL."""
    import sqlite3 as _sqlite3
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO entries (source_id, title, url, author, description, pub_date, duration) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source_id, title, url, author, description, pub_date, duration),
            )
            row = conn.execute(_SELECT + "WHERE e.id = ?", (cursor.lastrowid,)).fetchone()
            return _row(row)
    except _sqlite3.IntegrityError:
        # Duplicate URL — open a fresh connection to fetch the existing entry
        with get_db() as conn:
            row = conn.execute(_SELECT + "WHERE e.url = ?", (url,)).fetchone()
            return _row(row)


def get_entry(entry_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(_SELECT + "WHERE e.id = ?", (entry_id,)).fetchone()
        return _row(row) if row else None


def list_entries(source_id: Optional[int] = None, saved_only: bool = False) -> list[dict]:
    sql = _SELECT + "WHERE 1=1"
    params: list = []
    if source_id is not None:
        sql += " AND e.source_id = ?"
        params.append(source_id)
    if saved_only:
        sql += " AND e.is_saved = 1"
    sql += " ORDER BY e.pub_date DESC, e.created_at DESC"
    with get_db() as conn:
        return [_row(r) for r in conn.execute(sql, params).fetchall()]


def mark_read(entry_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE entries SET read_at = ? WHERE id = ? AND read_at IS NULL",
            (now, entry_id),
        )


def save_entry(entry_id: int, file_path: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE entries SET is_saved = 1, file_path = ? WHERE id = ?",
            (file_path, entry_id),
        )


def unsave_entry(entry_id: int) -> None:
    with get_db() as conn:
        conn.execute("UPDATE entries SET is_saved = 0 WHERE id = ?", (entry_id,))


def update_entry_fetch_status(entry_id: int, status: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE entries SET fetch_status = ? WHERE id = ?", (status, entry_id))


def update_entry_audio_path(entry_id: int, audio_path: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE entries SET audio_path = ? WHERE id = ?", (audio_path, entry_id))


def search_entries(query: str, source_ids: Optional[list[int]] = None) -> list[dict]:
    like = f"%{query}%"
    sql = _SELECT + "WHERE (e.title LIKE ? OR e.author LIKE ? OR e.description LIKE ?)"
    params: list = [like, like, like]
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        sql += f" AND e.source_id IN ({placeholders})"
        params.extend(source_ids)
    sql += " ORDER BY e.pub_date DESC, e.created_at DESC"
    with get_db() as conn:
        return [_row(r) for r in conn.execute(sql, params).fetchall()]
