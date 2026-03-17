import sqlite3
from db.connection import get_db


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def create_tag(name: str) -> dict:
    """Create tag or return existing one with same name."""
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        return _row(conn.execute("SELECT * FROM tags WHERE name = ?", (name,)).fetchone())


def add_tag_to_entry(entry_id: int, tag_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) VALUES (?, ?)",
            (entry_id, tag_id),
        )


def remove_tag_from_entry(entry_id: int, tag_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "DELETE FROM entry_tags WHERE entry_id = ? AND tag_id = ?",
            (entry_id, tag_id),
        )


def get_entry_tags(entry_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT t.* FROM tags t JOIN entry_tags et ON et.tag_id = t.id WHERE et.entry_id = ? ORDER BY t.name",
            (entry_id,),
        ).fetchall()
        return [_row(r) for r in rows]


def list_tags() -> list[dict]:
    with get_db() as conn:
        return [_row(r) for r in conn.execute("SELECT * FROM tags ORDER BY name").fetchall()]
