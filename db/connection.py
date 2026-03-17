import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


def get_db_path() -> Path:
    """Return DB path. Override with LAESER_DB_PATH env var for testing."""
    return Path(os.environ.get("LAESER_DB_PATH", "laeser.db"))


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection with foreign keys enabled and auto commit/rollback."""
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
