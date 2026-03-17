from db.connection import get_db

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK(type IN ('podcast', 'rss', 'manual')),
    feed_url        TEXT,
    archive_mode    TEXT CHECK(archive_mode IN ('track_only', 'full_archive')),
    folder_name     TEXT NOT NULL UNIQUE,
    last_fetched_at TEXT,
    last_fetch_error TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    INTEGER NOT NULL REFERENCES sources(id),
    title        TEXT NOT NULL,
    author       TEXT,
    pub_date     TEXT,
    url          TEXT UNIQUE,
    description  TEXT,
    duration     TEXT,
    audio_path   TEXT,
    file_path    TEXT,
    is_saved     INTEGER NOT NULL DEFAULT 0,
    read_at      TEXT,
    fetch_status TEXT NOT NULL DEFAULT 'pending'
                 CHECK(fetch_status IN ('pending', 'ok', 'fetch_failed')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

INSERT OR IGNORE INTO sources (name, type, feed_url, archive_mode, folder_name)
VALUES ('Manual Entries', 'manual', NULL, NULL, 'manual-entries');
"""


def init_db() -> None:
    """Create all tables and seed the synthetic Manual Entries source."""
    with get_db() as conn:
        conn.executescript(_SCHEMA)
