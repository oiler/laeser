# Laeser Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Laeser, a local web app for long-term archival of RSS articles and podcast episodes, with per-source markdown files, SQLite index, and an HTMX-driven three-panel browser UI.

**Architecture:** FastAPI backend with SQLite for indexing and search. Content archived as markdown files in a `library/` directory (one folder per source). Jinja2 + HTMX for the three-panel UI (source list → entry list → entry reader). APScheduler for background feed refreshes. All DB paths and library paths are configurable via env vars for test isolation.

**Tech Stack:** Python 3.11, uv, FastAPI, Uvicorn, Jinja2, HTMX 2.x (CDN), feedparser, APScheduler, python-frontmatter, requests, pytest, httpx

---

## File Structure

```
laeser/
  pyproject.toml              # uv project config, all dependencies
  .python-version             # pins Python 3.11
  .gitignore                  # excludes library/, laeser.db, .venv/
  main.py                     # FastAPI app, route mounting, lifespan (DB init + scheduler)

  db/
    __init__.py
    connection.py             # get_db_path(), get_db() context manager
    schema.py                 # init_db() — CREATE TABLE + seed Manual Entries source
    sources.py                # Source CRUD + list_sources_with_unread_count()
    entries.py                # Entry CRUD — all queries join with sources for source_name
    tags.py                   # Tag CRUD: create, add_to_entry, remove_from_entry, get_entry_tags

  feeds/
    __init__.py
    fetcher.py                # fetch_and_parse_feed(url) → list[dict]
    downloader.py             # download_file(url, dest_path) with HTTP range resume
    scheduler.py              # setup_scheduler(app), refresh_source(source_id), refresh_all()

  storage.py                  # write_entry_file(entry) → Path; slugify(); frontmatter

  routes/
    __init__.py
    sources.py                # GET /, POST /sources, DELETE /sources/{id}, POST /sources/{id}/refresh
    entries.py                # GET /entries, GET /entries/{id}, POST save/unsave/read/tags
    search.py                 # GET /search
    audio.py                  # GET /audio/{file_path:path}

  templates/
    base.html                 # 3-panel shell: sidebar + entry-list + entry-reader
    _sidebar.html             # source list with unread counts (HTMX fragment)
    _entry_list.html          # entry rows (HTMX fragment)
    _entry_reader.html        # full entry content + audio player (HTMX fragment)
    _search_results.html      # search result rows (reuses entry row structure)
    _add_source_form.html     # inline form for adding a new source

  static/
    style.css                 # minimal CSS for 3-panel layout

  tests/
    conftest.py               # isolate_db (autouse), client fixture
    test_db_sources.py
    test_db_entries.py
    test_db_tags.py
    test_feeds_fetcher.py
    test_storage.py
    test_routes_sources.py
    test_routes_entries.py
    test_routes_search.py

  library/                    # runtime content storage (gitignored)
  docs/
  example-files/
```

---

## Chunk 1: Foundation & Database Layer

**Files in this chunk:**
`pyproject.toml`, `.python-version`, `.gitignore`, `main.py`, `db/__init__.py`, `db/connection.py`, `db/schema.py`, `db/sources.py`, `db/entries.py`, `db/tags.py`, `tests/conftest.py`, `tests/test_db_sources.py`, `tests/test_db_entries.py`, `tests/test_db_tags.py`

---

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "laeser"
version = "0.1.0"
description = "A hybrid RSS and podcast reader with local archival"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.9",
    "feedparser>=6.0.11",
    "apscheduler>=3.10.0",
    "requests>=2.31.0",
    "python-frontmatter>=1.1.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
    "pytest-mock>=3.12.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create `.python-version`**

```
3.11
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
laeser.db
library/
*.egg-info/
.venv/
```

- [ ] **Step 4: Create `static/.gitkeep` and `templates/.gitkeep`**

```bash
mkdir -p static templates
touch static/.gitkeep templates/.gitkeep
```

This ensures `static/` exists on disk before the app mounts it (`StaticFiles` raises on startup if the directory is missing). Git does not track empty directories, so `.gitkeep` files ensure both directories are committed.

- [ ] **Step 5: Install dependencies**

Run: `uv sync`

Expected: `.venv/` created, all packages installed, no errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version .gitignore static/.gitkeep templates/.gitkeep
git commit -m "chore: project setup with uv"
```

---

### Task 2: Database Connection

**Files:**
- Create: `db/__init__.py`
- Create: `db/connection.py`

- [ ] **Step 1: Create `db/__init__.py`** (empty file)

- [ ] **Step 2: Create `db/connection.py`**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add db/
git commit -m "feat: SQLite connection manager"
```

---

### Task 3: Database Schema

**Files:**
- Create: `db/schema.py`

- [ ] **Step 1: Create `db/schema.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add db/schema.py
git commit -m "feat: database schema with Manual Entries seed"
```

---

### Task 4: Source CRUD

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_db_sources.py`
- Create: `db/sources.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
import os
import pytest


@pytest.fixture(autouse=True)
def isolate_db(tmp_path):
    """Redirect DB and library to temp dirs for each test."""
    db_path = tmp_path / "test.db"
    library_path = tmp_path / "library"
    library_path.mkdir()
    os.environ["LAESER_DB_PATH"] = str(db_path)
    os.environ["LAESER_LIBRARY_PATH"] = str(library_path)
    from db.schema import init_db
    init_db()
    yield
    os.environ.pop("LAESER_DB_PATH", None)
    os.environ.pop("LAESER_LIBRARY_PATH", None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)
```

- [ ] **Step 2: Create `tests/test_db_sources.py`**

```python
import pytest
from db.sources import (
    create_source,
    delete_source,
    get_source,
    list_sources,
    list_sources_with_unread_count,
    update_source_fetch_status,
)


def _make_source(**kwargs):
    defaults = dict(
        name="Security Now",
        type="podcast",
        feed_url="https://feeds.twit.tv/sn.xml",
        archive_mode="full_archive",
        folder_name="security-now",
    )
    defaults.update(kwargs)
    return create_source(**defaults)


def test_create_source():
    source = _make_source()
    assert source["id"] is not None
    assert source["name"] == "Security Now"
    assert source["archive_mode"] == "full_archive"
    assert source["last_fetch_error"] is None


def test_list_sources_includes_manual():
    sources = list_sources()
    names = [s["name"] for s in sources]
    assert "Manual Entries" in names


def test_create_duplicate_folder_name_raises():
    _make_source(folder_name="my-show", name="Show A")
    with pytest.raises(Exception):
        _make_source(folder_name="my-show", name="Show B")


def test_get_source():
    source = _make_source(name="In Our Time", folder_name="in-our-time")
    fetched = get_source(source["id"])
    assert fetched["name"] == "In Our Time"


def test_get_source_returns_none_for_missing():
    assert get_source(9999) is None


def test_delete_source():
    source = _make_source(folder_name="temp-show", name="Temp")
    delete_source(source["id"])
    assert get_source(source["id"]) is None


def test_update_source_fetch_status_success():
    source = _make_source()
    update_source_fetch_status(source["id"], error=None)
    updated = get_source(source["id"])
    assert updated["last_fetched_at"] is not None
    assert updated["last_fetch_error"] is None


def test_update_source_fetch_status_error():
    source = _make_source()
    update_source_fetch_status(source["id"], error="Connection refused")
    updated = get_source(source["id"])
    assert updated["last_fetch_error"] == "Connection refused"
    assert updated["last_fetched_at"] is not None


def test_list_sources_with_unread_count():
    sources = list_sources_with_unread_count()
    assert all("unread_count" in s for s in sources)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_sources.py -v`

Expected: `ImportError: cannot import name 'create_source' from 'db.sources'`

- [ ] **Step 4: Create `db/sources.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_sources.py -v`

Expected: All 9 tests PASS (including `test_create_source` which now asserts `last_fetch_error`)

- [ ] **Step 6: Commit**

```bash
git add db/sources.py tests/conftest.py tests/test_db_sources.py
git commit -m "feat: source CRUD with tests"
```

---

### Task 5: Entry CRUD

**Files:**
- Create: `db/entries.py`
- Create: `tests/test_db_entries.py`

- [ ] **Step 1: Create `tests/test_db_entries.py`**

```python
import pytest
from db.sources import create_source
from db.entries import (
    create_entry,
    get_entry,
    list_entries,
    mark_read,
    save_entry,
    search_entries,
    unsave_entry,
    update_entry_fetch_status,
)


@pytest.fixture
def source():
    return create_source(
        name="Security Now", type="podcast",
        feed_url="https://feeds.twit.tv/sn.xml",
        archive_mode="full_archive", folder_name="security-now",
    )


@pytest.fixture
def entry(source):
    return create_entry(
        source_id=source["id"], title="Episode 1047: XZ Backdoor",
        url="https://twit.tv/sn/1047", author="Steve Gibson",
        description="Show notes here", pub_date="2024-04-02",
    )


def test_create_entry(source):
    e = create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1")
    assert e["id"] is not None
    assert e["fetch_status"] == "pending"
    assert e["is_saved"] == 0
    assert e["source_name"] == "Security Now"


def test_create_entry_deduplicates_by_url(source, entry):
    create_entry(source_id=source["id"], title="Duplicate", url="https://twit.tv/sn/1047")
    entries = list_entries(source_id=source["id"])
    assert len(entries) == 1


def test_list_entries_for_source(source):
    create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1")
    create_entry(source_id=source["id"], title="Ep 2", url="https://example.com/2")
    assert len(list_entries(source_id=source["id"])) == 2


def test_list_entries_saved_only(source):
    e1 = create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1")
    create_entry(source_id=source["id"], title="Ep 2", url="https://example.com/2")
    save_entry(e1["id"], file_path="library/security-now/ep1.md")
    assert len(list_entries(saved_only=True)) == 1


def test_mark_read(entry):
    assert entry["read_at"] is None
    mark_read(entry["id"])
    assert get_entry(entry["id"])["read_at"] is not None


def test_mark_read_is_idempotent(entry):
    mark_read(entry["id"])
    first_read_at = get_entry(entry["id"])["read_at"]
    mark_read(entry["id"])
    assert get_entry(entry["id"])["read_at"] == first_read_at


def test_save_entry(entry):
    save_entry(entry["id"], file_path="library/security-now/ep1047.md")
    updated = get_entry(entry["id"])
    assert updated["is_saved"] == 1
    assert updated["file_path"] == "library/security-now/ep1047.md"


def test_unsave_preserves_file_path(entry):
    save_entry(entry["id"], file_path="library/security-now/ep1047.md")
    unsave_entry(entry["id"])
    updated = get_entry(entry["id"])
    assert updated["is_saved"] == 0
    assert updated["file_path"] == "library/security-now/ep1047.md"


def test_update_entry_fetch_status(entry):
    update_entry_fetch_status(entry["id"], "ok")
    assert get_entry(entry["id"])["fetch_status"] == "ok"


def test_search_by_title(source):
    create_entry(source_id=source["id"], title="XZ Backdoor Episode", url="https://example.com/1")
    create_entry(source_id=source["id"], title="TCP Episode", url="https://example.com/2")
    results = search_entries(query="XZ Backdoor")
    assert len(results) == 1
    assert results[0]["title"] == "XZ Backdoor Episode"


def test_search_by_description(source):
    create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1", description="backdoor vulnerability")
    create_entry(source_id=source["id"], title="Ep 2", url="https://example.com/2", description="networking basics")
    assert len(search_entries(query="vulnerability")) == 1


def test_search_filtered_by_source_ids(source):
    source2 = create_source(name="Other Show", type="rss", feed_url="https://other.com",
                             archive_mode="track_only", folder_name="other-show")
    create_entry(source_id=source["id"], title="Security XZ", url="https://example.com/1")
    create_entry(source_id=source2["id"], title="Security TCP", url="https://example.com/2")
    results = search_entries(query="Security", source_ids=[source["id"]])
    assert len(results) == 1
    assert results[0]["source_name"] == "Security Now"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_entries.py -v`

Expected: `ImportError: cannot import name 'create_entry'`

- [ ] **Step 3: Create `db/entries.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_entries.py -v`

Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add db/entries.py tests/test_db_entries.py
git commit -m "feat: entry CRUD with search — always joins source_name"
```

---

### Task 6: Tag CRUD

**Files:**
- Create: `db/tags.py`
- Create: `tests/test_db_tags.py`

- [ ] **Step 1: Create `tests/test_db_tags.py`**

```python
import pytest
from db.sources import create_source
from db.entries import create_entry
from db.tags import add_tag_to_entry, create_tag, get_entry_tags, list_tags, remove_tag_from_entry


@pytest.fixture
def entry():
    s = create_source(name="Show", type="rss", feed_url="https://example.com",
                      archive_mode="track_only", folder_name="show")
    return create_entry(source_id=s["id"], title="Ep 1", url="https://example.com/1")


def test_create_tag():
    tag = create_tag("security")
    assert tag["name"] == "security"
    assert tag["id"] is not None


def test_create_tag_is_idempotent():
    t1 = create_tag("networking")
    t2 = create_tag("networking")
    assert t1["id"] == t2["id"]


def test_add_and_get_tags(entry):
    tag = create_tag("security")
    add_tag_to_entry(entry["id"], tag["id"])
    tags = get_entry_tags(entry["id"])
    assert len(tags) == 1
    assert tags[0]["name"] == "security"


def test_remove_tag(entry):
    tag = create_tag("security")
    add_tag_to_entry(entry["id"], tag["id"])
    remove_tag_from_entry(entry["id"], tag["id"])
    assert get_entry_tags(entry["id"]) == []


def test_add_tag_is_idempotent(entry):
    tag = create_tag("security")
    add_tag_to_entry(entry["id"], tag["id"])
    add_tag_to_entry(entry["id"], tag["id"])  # no error
    assert len(get_entry_tags(entry["id"])) == 1


def test_list_tags():
    create_tag("security")
    create_tag("networking")
    names = [t["name"] for t in list_tags()]
    assert "security" in names
    assert "networking" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_tags.py -v`

Expected: `ImportError: cannot import name 'create_tag'`

- [ ] **Step 3: Create `db/tags.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_tags.py -v`

Expected: All 6 tests PASS

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add db/tags.py tests/test_db_tags.py
git commit -m "feat: tag CRUD with tests"
```

---

### Task 7: Minimal FastAPI App

**Files:**
- Create: `routes/__init__.py`
- Create: `main.py`

- [ ] **Step 1: Create `routes/__init__.py`** (empty file)

- [ ] **Step 2: Create `main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db.schema import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Laeser", lifespan=lifespan)

# static/ is created in Task 1 (static/.gitkeep) — always present
app.mount("/static", StaticFiles(directory="static"), name="static")
```

- [ ] **Step 3: Verify app starts**

Run: `uv run uvicorn main:app --reload`

Expected: Server starts at http://127.0.0.1:8000, no errors. Kill with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
git add routes/__init__.py main.py
git commit -m "feat: minimal FastAPI app with DB init on startup"
```

---

## Chunk 2: Feed Fetching & Library Storage

**Files in this chunk:**
`feeds/__init__.py`, `feeds/fetcher.py`, `feeds/downloader.py`, `storage.py`, `tests/test_feeds_fetcher.py`, `tests/test_storage.py`

---

### Task 8: Feed Fetcher

**Files:**
- Create: `feeds/__init__.py`
- Create: `feeds/fetcher.py`
- Create: `tests/test_feeds_fetcher.py`

- [ ] **Step 1: Create `tests/test_feeds_fetcher.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from feeds.fetcher import fetch_and_parse_feed, parse_feed_entry


# Minimal feedparser-like result structure
def _fake_feed(entries):
    feed = MagicMock()
    feed.bozo = False
    feed.entries = entries
    return feed


def _fake_entry(
    title="Episode 1",
    link="https://example.com/ep1",
    summary="Show notes here",
    author="Steve Gibson",
    published="Tue, 02 Apr 2024 00:00:00 +0000",
    enclosures=None,
    itunes_duration=None,
):
    e = MagicMock()
    e.get = lambda key, default=None: {
        "title": title,
        "link": link,
        "summary": summary,
        "author": author,
        "published": published,
        "itunes_duration": itunes_duration,
    }.get(key, default)
    e.title = title
    e.link = link
    e.get("summary", "")
    e.summary = summary
    e.author = author
    e.published = published
    e.enclosures = enclosures or []
    e.itunes_duration = itunes_duration
    return e


def test_parse_feed_entry_extracts_fields():
    entry = _fake_entry()
    result = parse_feed_entry(entry)
    assert result["title"] == "Episode 1"
    assert result["url"] == "https://example.com/ep1"
    assert result["description"] == "Show notes here"
    assert result["author"] == "Steve Gibson"


def test_parse_feed_entry_extracts_audio_enclosure():
    enc = MagicMock()
    enc.type = "audio/mpeg"
    enc.href = "https://example.com/ep1.mp3"
    entry = _fake_entry(enclosures=[enc])
    result = parse_feed_entry(entry)
    assert result["enclosure_url"] == "https://example.com/ep1.mp3"


def test_parse_feed_entry_no_enclosure():
    entry = _fake_entry(enclosures=[])
    result = parse_feed_entry(entry)
    assert result["enclosure_url"] is None


def test_parse_feed_entry_extracts_duration():
    entry = _fake_entry(itunes_duration="01:23:45")
    result = parse_feed_entry(entry)
    assert result["duration"] == "01:23:45"


def test_fetch_and_parse_feed_returns_list(monkeypatch):
    fake = _fake_feed([_fake_entry(title="Ep 1", link="https://example.com/1"),
                       _fake_entry(title="Ep 2", link="https://example.com/2")])
    monkeypatch.setattr("feeds.fetcher.feedparser.parse", lambda url: fake)
    results = fetch_and_parse_feed("https://example.com/feed.rss")
    assert len(results) == 2
    assert results[0]["title"] == "Ep 1"


def test_fetch_and_parse_feed_raises_on_bozo(monkeypatch):
    fake = MagicMock()
    fake.bozo = True
    fake.bozo_exception = Exception("malformed XML")
    monkeypatch.setattr("feeds.fetcher.feedparser.parse", lambda url: fake)
    with pytest.raises(ValueError, match="malformed"):
        fetch_and_parse_feed("https://example.com/bad.rss")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_feeds_fetcher.py -v`

Expected: `ImportError: No module named 'feeds'`

- [ ] **Step 3: Create `feeds/__init__.py`** (empty file)

- [ ] **Step 4: Create `feeds/fetcher.py`**

```python
import feedparser
from typing import Optional


def parse_feed_entry(entry) -> dict:
    """Extract a normalised dict from a feedparser entry object."""
    enclosure_url: Optional[str] = None
    for enc in getattr(entry, "enclosures", []):
        if getattr(enc, "type", "").startswith("audio/"):
            enclosure_url = getattr(enc, "href", None)
            break

    return {
        "title": getattr(entry, "title", "") or "",
        "url": getattr(entry, "link", None),
        "author": getattr(entry, "author", None),
        "description": getattr(entry, "summary", None) or getattr(entry, "description", None),
        "pub_date": getattr(entry, "published", None),
        "duration": getattr(entry, "itunes_duration", None),
        "enclosure_url": enclosure_url,
    }


def fetch_and_parse_feed(url: str) -> list[dict]:
    """
    Fetch and parse an RSS/Atom feed URL.
    Returns a list of normalised entry dicts.
    Raises ValueError if the feed is malformed (bozo).
    """
    feed = feedparser.parse(url)
    if feed.bozo:
        raise ValueError(f"Malformed feed at {url}: {feed.bozo_exception}")
    return [parse_feed_entry(e) for e in feed.entries]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_feeds_fetcher.py -v`

Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add feeds/ tests/test_feeds_fetcher.py
git commit -m "feat: RSS/podcast feed fetcher with tests"
```

---

### Task 9: File Downloader

**Files:**
- Create: `feeds/downloader.py`

- [ ] **Step 1: Create `tests/test_feeds_downloader.py`**

```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from feeds.downloader import download_file


def _mock_response(status_code=200, content=b"audio data", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.iter_content = lambda chunk_size: [content]
    resp.raise_for_status = MagicMock()
    return resp


def test_download_file_success(tmp_path):
    dest = tmp_path / "ep.mp3"
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(200)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is True
    assert dest.exists()
    assert dest.read_bytes() == b"audio data"


def test_download_file_404_returns_false(tmp_path):
    dest = tmp_path / "ep.mp3"
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(404)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is False
    assert not dest.exists()


def test_download_file_416_returns_true(tmp_path):
    """416 = Range Not Satisfiable = file already complete."""
    dest = tmp_path / "ep.mp3"
    dest.write_bytes(b"existing content")
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(416)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is True


def test_download_file_resumes_partial(tmp_path):
    dest = tmp_path / "ep.mp3"
    dest.write_bytes(b"partial")
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(206)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is True
    # Verify Range header was sent
    call_kwargs = mock_get.call_args[1]
    assert "Range" in call_kwargs.get("headers", {})


def test_download_file_cleans_up_on_fresh_failure(tmp_path):
    dest = tmp_path / "ep.mp3"
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is False
    assert not dest.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_feeds_downloader.py -v`

Expected: `ImportError: No module named 'feeds.downloader'`

- [ ] **Step 3: Create `feeds/downloader.py`**

```python
import logging
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "Laeser/0.1 (polite downloader)"
TIMEOUT_SECONDS = 300
DEFAULT_DELAY_SECONDS = 5


def download_file(
    url: str,
    dest_path: Path,
    delay_seconds: int = DEFAULT_DELAY_SECONDS,
) -> bool:
    """
    Download a file to dest_path with HTTP range-request resume support.
    Returns True on success, False on failure.
    Waits delay_seconds before starting (for polite rate limiting in bulk downloads).
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Check for existing partial download
    headers = {"User-Agent": USER_AGENT}
    existing_size = dest_path.stat().st_size if dest_path.exists() else 0
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"
        logger.info(f"Resuming download at byte {existing_size}: {url}")

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS, stream=True)

        if response.status_code == 416:
            # Range not satisfiable — file already complete
            logger.info(f"Already complete: {dest_path.name}")
            return True

        if response.status_code == 404:
            logger.warning(f"Not found (404): {url}")
            return False

        response.raise_for_status()

        mode = "ab" if existing_size > 0 and response.status_code == 206 else "wb"
        with open(dest_path, mode) as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        actual_size = dest_path.stat().st_size
        logger.info(f"Downloaded {dest_path.name} ({actual_size / 1024 / 1024:.1f} MB)")
        return True

    except requests.RequestException as e:
        logger.error(f"Download failed for {url}: {e}")
        # Clean up partial file only if we started fresh (not a resume)
        if existing_size == 0 and dest_path.exists():
            dest_path.unlink()
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_feeds_downloader.py -v`

Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add feeds/downloader.py tests/test_feeds_downloader.py
git commit -m "feat: resumable file downloader with tests"
```

---

### Task 10: Library Writer (Markdown)

**Files:**
- Create: `storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Create `tests/test_storage.py`**

```python
import os
from pathlib import Path
import frontmatter
from storage import write_entry_file, slugify


def test_slugify():
    assert slugify("Hello World!") == "hello-world"
    assert slugify("The XZ Backdoor (2024)") == "the-xz-backdoor-2024"
    assert slugify("A" * 100)[:80] == slugify("A" * 100)  # truncated to 80 chars


def test_write_entry_file_creates_file(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Security Now 1047: XZ Backdoor",
        "source_name": "Security Now",
        "source_folder": "security-now",
        "author": "Steve Gibson",
        "pub_date": "2024-04-02",
        "url": "https://twit.tv/sn/1047",
        "audio_path": "",
        "description": "Show notes here.",
        "tags": [],
    }
    path = write_entry_file(entry)
    assert path.exists()
    assert path.suffix == ".md"
    assert "security-now" in str(path)


def test_write_entry_file_frontmatter(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Test Episode",
        "source_name": "My Show",
        "source_folder": "my-show",
        "author": "Author Name",
        "pub_date": "2024-01-15",
        "url": "https://example.com/ep",
        "audio_path": "library/my-show/ep.mp3",
        "description": "Episode description.",
        "tags": ["security", "networking"],
    }
    path = write_entry_file(entry)
    post = frontmatter.load(str(path))
    assert post["title"] == "Test Episode"
    assert post["source"] == "My Show"
    assert post["author"] == "Author Name"
    assert post["pub_date"] == "2024-01-15"
    assert post["url"] == "https://example.com/ep"
    assert post["audio_path"] == "library/my-show/ep.mp3"
    assert post["tags"] == ["security", "networking"]
    assert post.content == "Episode description."


def test_write_entry_file_overwrites_on_resave(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Test Episode", "source_name": "My Show", "source_folder": "my-show",
        "author": "", "pub_date": "2024-01-15", "url": "https://example.com/ep",
        "audio_path": "", "description": "First save.", "tags": [],
    }
    path1 = write_entry_file(entry)
    entry["description"] = "Updated save."
    path2 = write_entry_file(entry)
    assert path1 == path2
    post = frontmatter.load(str(path2))
    assert post.content == "Updated save."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage.py -v`

Expected: `ImportError: No module named 'storage'`

- [ ] **Step 3: Create `storage.py`**

```python
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import frontmatter


def get_library_path() -> Path:
    """Return library path. Override with LAESER_LIBRARY_PATH env var for testing."""
    return Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug, max 80 chars."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:80]


def write_entry_file(entry: dict) -> Path:
    """
    Write or overwrite an entry as a markdown file with YAML frontmatter.
    Returns the Path of the written file.

    entry dict keys: title, source_name, source_folder, author, pub_date,
                     url, audio_path, description, tags (list of str)
    """
    library = get_library_path()
    source_folder = library / entry["source_folder"]
    source_folder.mkdir(parents=True, exist_ok=True)

    pub_date = entry.get("pub_date") or ""
    date_prefix = pub_date[:10] if pub_date else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = slugify(entry["title"])
    file_path = source_folder / f"{date_prefix}-{slug}.md"

    post = frontmatter.Post(
        entry.get("description") or "",
        title=entry["title"],
        source=entry["source_name"],
        author=entry.get("author") or "",
        pub_date=pub_date,
        url=entry.get("url") or "",
        audio_path=entry.get("audio_path") or "",
        tags=entry.get("tags") or [],
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    return file_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage.py -v`

Expected: All 4 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "feat: markdown library writer with frontmatter and tests"
```

---

## Chunk 3: Core UI — Routes & Templates

**Files in this chunk:**
`routes/sources.py`, `routes/entries.py`, `templates/base.html`, `templates/_sidebar.html`, `templates/_entry_list.html`, `templates/_entry_reader.html`, `templates/_add_source_form.html`, `static/style.css`, `tests/test_routes_sources.py`, `tests/test_routes_entries.py`

---

### Task 11: Static Files & Base Layout

**Files:**
- Create: `static/style.css`
- Create: `templates/base.html`

- [ ] **Step 1: Create `static/style.css`**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body { font-family: system-ui, sans-serif; font-size: 14px; background: #f5f5f5; color: #222; height: 100vh; overflow: hidden; }

.layout { display: grid; grid-template-columns: 220px 340px 1fr; height: 100vh; }

/* Sidebar */
aside { border-right: 1px solid #ddd; background: #fafafa; overflow-y: auto; padding: 12px 0; }
.nav-views, .source-list { list-style: none; }
.nav-views li, .source-list li { padding: 0; }
.nav-views a, .source-list a { display: flex; justify-content: space-between; padding: 6px 16px; text-decoration: none; color: inherit; cursor: pointer; }
.nav-views a:hover, .source-list a:hover { background: #e8e8e8; }
.sidebar-divider { border: none; border-top: 1px solid #ddd; margin: 8px 0; }
.badge { background: #0066cc; color: white; border-radius: 10px; padding: 1px 6px; font-size: 11px; }
.btn-add-source { display: block; width: calc(100% - 24px); margin: 12px; padding: 6px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; }

/* Entry list */
main { border-right: 1px solid #ddd; overflow-y: auto; background: white; }
.entry-list { list-style: none; }
.entry-row { display: flex; flex-direction: column; padding: 10px 14px; border-bottom: 1px solid #eee; cursor: pointer; position: relative; }
.entry-row:hover { background: #f0f4ff; }
.entry-row.unread .entry-title { font-weight: 600; }
.entry-title { flex: 1; }
.entry-details { font-size: 12px; color: #777; margin-top: 2px; }
.save-btn { position: absolute; right: 10px; top: 10px; background: none; border: none; font-size: 16px; cursor: pointer; color: #aaa; }
.save-btn.saved { color: #f5a623; }
.icon-podcast { font-size: 11px; margin-left: 4px; }
.empty-state { padding: 24px; color: #999; }

/* Search */
.search-bar { padding: 10px 14px; border-bottom: 1px solid #eee; position: sticky; top: 0; background: white; z-index: 10; }
.search-bar input { width: 100%; padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; }

/* Entry reader */
article { overflow-y: auto; padding: 24px; background: white; }
.entry-header h1 { font-size: 20px; margin-bottom: 8px; }
.entry-meta { font-size: 12px; color: #777; margin-bottom: 8px; }
.original-link { font-size: 12px; color: #0066cc; text-decoration: none; }
.entry-tags { margin: 12px 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.tag { background: #eef; border-radius: 12px; padding: 2px 10px; font-size: 12px; display: flex; align-items: center; gap: 4px; }
.tag button { background: none; border: none; cursor: pointer; color: #999; padding: 0; line-height: 1; }
.entry-tags input { border: 1px solid #ccc; border-radius: 12px; padding: 2px 10px; font-size: 12px; }
.entry-body { margin-top: 16px; line-height: 1.7; white-space: pre-wrap; }

/* Audio player */
.audio-player { position: sticky; bottom: 0; background: #f5f5f5; border-top: 1px solid #ddd; padding: 12px; margin-top: 24px; }
.audio-player audio { width: 100%; }
.audio-controls { display: flex; gap: 8px; margin-top: 6px; }
.audio-controls button { padding: 2px 10px; border: 1px solid #ccc; border-radius: 4px; background: white; cursor: pointer; font-size: 12px; }
.audio-controls button.active { background: #0066cc; color: white; border-color: #0066cc; }
```

- [ ] **Step 2: Create `templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Laeser</title>
    <script src="https://unpkg.com/htmx.org@2.0.3" crossorigin="anonymous"></script>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="layout">
        <aside id="sidebar">
            {% include "_sidebar.html" %}
        </aside>

        <main id="entry-list">
            <p class="empty-state">Select a source to browse entries.</p>
        </main>

        <article id="entry-reader">
            <p class="empty-state">Select an entry to read.</p>
        </article>
    </div>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add static/style.css templates/base.html
git commit -m "feat: base 3-panel layout and CSS"
```

---

### Task 12: Sidebar Template & Add Source Form

**Files:**
- Create: `templates/_sidebar.html`
- Create: `templates/_add_source_form.html`

- [ ] **Step 1: Create `templates/_sidebar.html`**

```html
<nav>
    <ul class="nav-views">
        <li>
            <a hx-get="/entries" hx-target="#entry-list" hx-push-url="false">
                All Items
            </a>
        </li>
        <li>
            <a hx-get="/entries?saved=1" hx-target="#entry-list" hx-push-url="false">
                Library
            </a>
        </li>
    </ul>
    <hr class="sidebar-divider">
    <ul class="source-list">
        {% for source in sources %}
        {% if source.type != 'manual' %}
        <li>
            <a hx-get="/entries?source_id={{ source.id }}" hx-target="#entry-list" hx-push-url="false">
                {{ source.name }}
                {% if source.unread_count %}
                <span class="badge">{{ source.unread_count }}</span>
                {% endif %}
            </a>
        </li>
        {% endif %}
        {% endfor %}
    </ul>
    <hr class="sidebar-divider">
    <button class="btn-add-source"
            hx-get="/sources/add-form"
            hx-target="#entry-list"
            hx-swap="innerHTML">
        + Add Source
    </button>
</nav>
```

- [ ] **Step 2: Create `templates/_add_source_form.html`**

```html
<div style="padding: 20px;">
    <h2 style="margin-bottom: 16px;">Add Source</h2>
    <form hx-post="/sources"
          hx-target="#sidebar"
          hx-swap="outerHTML"
          style="display: flex; flex-direction: column; gap: 12px;">
        <label>
            Feed URL<br>
            <input type="url" name="feed_url" placeholder="https://example.com/feed.rss"
                   required style="width: 100%; padding: 6px; margin-top: 4px;">
        </label>
        <label>
            Display Name<br>
            <input type="text" name="name" placeholder="Security Now"
                   required style="width: 100%; padding: 6px; margin-top: 4px;">
        </label>
        <label>
            Type<br>
            <select name="type" style="width: 100%; padding: 6px; margin-top: 4px;">
                <option value="podcast">Podcast</option>
                <option value="rss">RSS / Article Feed</option>
            </select>
        </label>
        <label>
            Archive Mode<br>
            <select name="archive_mode" style="width: 100%; padding: 6px; margin-top: 4px;">
                <option value="track_only">Track Only (index metadata)</option>
                <option value="full_archive">Full Archive (download all)</option>
            </select>
        </label>
        <button type="submit" style="padding: 8px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer;">
            Add Source
        </button>
    </form>
</div>
```

- [ ] **Step 3: Commit**

```bash
git add templates/_sidebar.html templates/_add_source_form.html
git commit -m "feat: sidebar and add source form templates"
```

---

### Task 13: Source Routes

**Files:**
- Create: `routes/sources.py`
- Create: `tests/test_routes_sources.py`

- [ ] **Step 1: Create `tests/test_routes_sources.py`**

```python
import pytest
from db.sources import create_source


def test_homepage_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Laeser" in resp.text


def test_add_source_via_post(client):
    resp = client.post("/sources", data={
        "feed_url": "https://feeds.twit.tv/sn.xml",
        "name": "Security Now",
        "type": "podcast",
        "archive_mode": "full_archive",
    })
    assert resp.status_code == 200
    # Response is the refreshed sidebar HTML
    assert "Security Now" in resp.text


def test_add_source_returns_sidebar(client):
    resp = client.post("/sources", data={
        "feed_url": "https://example.com/feed.rss",
        "name": "My Show",
        "type": "rss",
        "archive_mode": "track_only",
    })
    assert "My Show" in resp.text


def test_delete_source(client):
    source = create_source(name="To Delete", type="rss",
                           feed_url="https://example.com", archive_mode="track_only",
                           folder_name="to-delete")
    resp = client.delete(f"/sources/{source['id']}")
    assert resp.status_code == 200
    assert "To Delete" not in resp.text


def test_get_add_source_form(client):
    resp = client.get("/sources/add-form")
    assert resp.status_code == 200
    assert "Feed URL" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes_sources.py -v`

Expected: FAIL — routes not registered yet.

- [ ] **Step 3: Create `routes/sources.py`**

```python
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db.sources import (
    create_source,
    delete_source,
    list_sources_with_unread_count,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _sidebar_response(request: Request) -> HTMLResponse:
    sources = list_sources_with_unread_count()
    return templates.TemplateResponse(
        "_sidebar.html", {"request": request, "sources": sources}
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    sources = list_sources_with_unread_count()
    return templates.TemplateResponse("base.html", {"request": request, "sources": sources})


@router.get("/sources/add-form", response_class=HTMLResponse)
def add_source_form(request: Request):
    return templates.TemplateResponse("_add_source_form.html", {"request": request})


@router.post("/sources", response_class=HTMLResponse)
def add_source(
    request: Request,
    feed_url: str = Form(...),
    name: str = Form(...),
    type: str = Form(...),
    archive_mode: str = Form(...),
):
    import re
    folder_name = re.sub(r"[^\w]+", "-", name.lower()).strip("-")
    create_source(
        name=name,
        type=type,
        feed_url=feed_url,
        archive_mode=archive_mode,
        folder_name=folder_name,
    )
    return _sidebar_response(request)


@router.delete("/sources/{source_id}", response_class=HTMLResponse)
def remove_source(request: Request, source_id: int):
    delete_source(source_id)
    return _sidebar_response(request)
```

- [ ] **Step 4: Register router in `main.py`**

Add to `main.py`:

```python
from routes.sources import router as sources_router
app.include_router(sources_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_sources.py -v`

Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add routes/sources.py tests/test_routes_sources.py main.py
git commit -m "feat: source management routes with tests"
```

---

### Task 14: Entry List Template & Route

**Files:**
- Create: `templates/_entry_list.html`
- Create: `routes/entries.py` (partial — list only)
- Create: `tests/test_routes_entries.py` (partial)

- [ ] **Step 1: Create `templates/_entry_list.html`**

```html
<div class="search-bar">
    <input type="text"
           name="q"
           placeholder="Search entries..."
           hx-get="/search"
           hx-target="#entry-list"
           hx-trigger="input changed delay:300ms"
           hx-include="[name='source_id']">
    <input type="hidden" name="source_id" value="{{ source_id or '' }}">
</div>

{% if entries %}
<ul class="entry-list">
    {% for entry in entries %}
    <li class="entry-row {% if not entry.read_at %}unread{% endif %}"
        hx-get="/entries/{{ entry.id }}"
        hx-target="#entry-reader"
        hx-push-url="false">
        <div class="entry-meta">
            <span class="entry-title">{{ entry.title }}</span>
            {% if entry.audio_path %}
            <span class="icon-podcast" title="Podcast episode">🎙</span>
            {% endif %}
        </div>
        <div class="entry-details">
            <span>{{ entry.source_name }}</span>
            {% if entry.author %} · <span>{{ entry.author }}</span>{% endif %}
            {% if entry.pub_date %} · <span>{{ entry.pub_date[:10] }}</span>{% endif %}
        </div>
        {% include "_save_button.html" %}
    </li>
    {% endfor %}
</ul>
{% else %}
<p class="empty-state">No entries found.</p>
{% endif %}
```

- [ ] **Step 2: Create `templates/_save_button.html`**

```html
<button class="save-btn {% if entry.is_saved %}saved{% endif %}"
        hx-post="/entries/{{ entry.id }}/{% if entry.is_saved %}unsave{% else %}save{% endif %}"
        hx-target="this"
        hx-swap="outerHTML"
        onclick="event.stopPropagation()"
        title="{% if entry.is_saved %}Remove from library{% else %}Save to library{% endif %}">
    {% if entry.is_saved %}★{% else %}☆{% endif %}
</button>
```

- [ ] **Step 3: Create `tests/test_routes_entries.py`** (partial)

```python
import pytest
from db.sources import create_source
from db.entries import create_entry


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                         feed_url="https://feeds.twit.tv/sn.xml",
                         archive_mode="full_archive", folder_name="security-now")


@pytest.fixture
def entry(source):
    return create_entry(source_id=source["id"], title="Ep 1047",
                        url="https://example.com/1047", description="Show notes.")


def test_entry_list_all(client, entry):
    resp = client.get("/entries")
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text


def test_entry_list_by_source(client, source, entry):
    resp = client.get(f"/entries?source_id={source['id']}")
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text


def test_entry_list_library_view(client, entry):
    # Before saving — should not appear in library
    resp = client.get("/entries?saved=1")
    assert "Ep 1047" not in resp.text
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes_entries.py -v`

Expected: FAIL — `/entries` route not found

- [ ] **Step 5: Create `routes/entries.py`** (list portion)

```python
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# NOTE: Imports below include functions used in Tasks 15 and 16 (reader route, save/tag
# routes). They are pre-staged here so this file does not need re-editing each task.
# Linters may flag some as unused until those steps are complete — this is expected.
from db.entries import (
    create_entry,
    get_entry,
    list_entries,
    mark_read,
    save_entry,
    search_entries,
    unsave_entry,
)
from db.tags import add_tag_to_entry, create_tag, get_entry_tags, remove_tag_from_entry
from storage import write_entry_file

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/entries", response_class=HTMLResponse)
def entry_list(
    request: Request,
    source_id: Optional[int] = None,
    saved: bool = False,
):
    entries = list_entries(source_id=source_id, saved_only=saved)
    return templates.TemplateResponse(
        "_entry_list.html",
        {"request": request, "entries": entries, "source_id": source_id},
    )
```

- [ ] **Step 6: Register router in `main.py`**

Add to `main.py`:

```python
from routes.entries import router as entries_router
app.include_router(entries_router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_entries.py -v`

Expected: All 3 tests PASS

- [ ] **Step 8: Commit**

```bash
git add templates/_entry_list.html templates/_save_button.html routes/entries.py tests/test_routes_entries.py main.py
git commit -m "feat: entry list route and template"
```

---

### Task 15: Entry Reader Template & Route

**Files:**
- Create: `templates/_entry_reader.html`
- Modify: `routes/entries.py` (add reader route)
- Modify: `tests/test_routes_entries.py` (add reader tests)

> **Cross-chunk dependency note:** `_entry_reader.html` renders the tag section inline. HTMX tag-add/remove operations (`hx-post`, `hx-delete` on the tags input and buttons) will return `_entry_tags.html` as a swap fragment — but that template is not created until Task 16. Tag interactions will show 500 errors until Task 16 is complete. This is expected — finish Task 15 first, then Task 16 will wire it up.

- [ ] **Step 1: Create `templates/_entry_reader.html`**

```html
<div class="reader-content">
    <header class="entry-header">
        <h1>{{ entry.title }}</h1>
        <div class="entry-meta">
            <span>{{ entry.source_name }}</span>
            {% if entry.author %} · <span>{{ entry.author }}</span>{% endif %}
            {% if entry.pub_date %} · <span>{{ entry.pub_date[:10] }}</span>{% endif %}
        </div>
        {% if entry.url %}
        <a href="{{ entry.url }}" target="_blank" class="original-link">View original ↗</a>
        {% endif %}
    </header>

    <div class="entry-tags" id="entry-tags-{{ entry.id }}">
        <strong>Tags:</strong>
        {% for tag in tags %}
        <span class="tag">
            {{ tag.name }}
            <button hx-delete="/entries/{{ entry.id }}/tags/{{ tag.id }}"
                    hx-target="#entry-tags-{{ entry.id }}"
                    hx-swap="outerHTML">×</button>
        </span>
        {% endfor %}
        <input type="text"
               placeholder="Add tag…"
               name="tag_name"
               hx-post="/entries/{{ entry.id }}/tags"
               hx-target="#entry-tags-{{ entry.id }}"
               hx-swap="outerHTML"
               hx-trigger="keydown[key=='Enter']">
    </div>

    <div class="entry-body">{{ entry.description or "No content available." }}</div>

    {% if entry.audio_path %}
    <div class="audio-player">
        <audio id="audio-player" controls>
            <source src="/audio/{{ entry.audio_path }}" type="audio/mpeg">
        </audio>
        <div class="audio-controls">
            <button onclick="setSpeed(1)" id="speed-1x" class="active">1×</button>
            <button onclick="setSpeed(1.5)" id="speed-1-5x">1.5×</button>
            <button onclick="setSpeed(2)" id="speed-2x">2×</button>
        </div>
        <script>
          function setSpeed(rate) {
            document.getElementById('audio-player').playbackRate = rate;
            ['speed-1x','speed-1-5x','speed-2x'].forEach(id => document.getElementById(id).classList.remove('active'));
            document.getElementById('speed-' + rate.toString().replace('.', '-') + 'x').classList.add('active');
          }
        </script>
    </div>
    {% endif %}
</div>
```

- [ ] **Step 2: Add reader tests to `tests/test_routes_entries.py`**

Append:

```python
def test_entry_reader_renders(client, entry):
    resp = client.get(f"/entries/{entry['id']}")
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text
    assert "Show notes." in resp.text


def test_entry_reader_marks_as_read(client, entry):
    from db.entries import get_entry as db_get_entry
    assert db_get_entry(entry["id"])["read_at"] is None
    client.get(f"/entries/{entry['id']}")
    assert db_get_entry(entry["id"])["read_at"] is not None
```

- [ ] **Step 3: Run new tests to verify they fail**

Run: `uv run pytest tests/test_routes_entries.py::test_entry_reader_renders -v`

Expected: FAIL — `/entries/{id}` route not found

- [ ] **Step 4: Add reader route to `routes/entries.py`**

Add after the `entry_list` route:

```python
@router.get("/entries/{entry_id}", response_class=HTMLResponse)
def entry_reader(request: Request, entry_id: int):
    entry = get_entry(entry_id)
    if not entry:
        return HTMLResponse("Entry not found", status_code=404)
    mark_read(entry_id)
    tags = get_entry_tags(entry_id)
    return templates.TemplateResponse(
        "_entry_reader.html",
        {"request": request, "entry": entry, "tags": tags},
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_entries.py -v`

Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add templates/_entry_reader.html routes/entries.py tests/test_routes_entries.py
git commit -m "feat: entry reader route and template with read-tracking"
```

---

## Chunk 4: Save, Tag, Search & Audio

**Files in this chunk:**
`routes/entries.py` (save/unsave/tag endpoints), `routes/search.py`, `routes/audio.py`, `templates/_search_results.html`, `tests/test_routes_entries.py` (save/tag tests), `tests/test_routes_search.py`

---

### Task 16: Save, Unsave & Tag Routes

**Files:**
- Modify: `routes/entries.py`
- Modify: `tests/test_routes_entries.py`

- [ ] **Step 1: Add save/tag tests to `tests/test_routes_entries.py`**

Append:

```python
def test_save_entry(client, entry):
    resp = client.post(f"/entries/{entry['id']}/save")
    assert resp.status_code == 200
    assert "★" in resp.text  # saved star shown
    from db.entries import get_entry as db_get
    assert db_get(entry["id"])["is_saved"] == 1


def test_unsave_entry(client, entry):
    client.post(f"/entries/{entry['id']}/save")
    resp = client.post(f"/entries/{entry['id']}/unsave")
    assert resp.status_code == 200
    assert "☆" in resp.text


def test_add_tag_to_entry(client, entry):
    resp = client.post(f"/entries/{entry['id']}/tags", data={"tag_name": "security"})
    assert resp.status_code == 200
    assert "security" in resp.text


def test_remove_tag_from_entry(client, entry):
    from db.tags import create_tag, add_tag_to_entry
    tag = create_tag("networking")
    add_tag_to_entry(entry["id"], tag["id"])
    resp = client.delete(f"/entries/{entry['id']}/tags/{tag['id']}")
    assert resp.status_code == 200
    assert "networking" not in resp.text
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `uv run pytest tests/test_routes_entries.py::test_save_entry -v`

Expected: FAIL — `/entries/{id}/save` route not found

- [ ] **Step 3: Add save/unsave/tag routes to `routes/entries.py`**

```python
def _tags_response(request: Request, entry_id: int) -> HTMLResponse:
    entry = get_entry(entry_id)
    tags = get_entry_tags(entry_id)
    return templates.TemplateResponse(
        "_entry_tags.html",
        {"request": request, "entry": entry, "tags": tags},
    )


def _save_button_response(request: Request, entry_id: int) -> HTMLResponse:
    entry = get_entry(entry_id)
    return templates.TemplateResponse(
        "_save_button.html",
        {"request": request, "entry": entry},
    )


@router.post("/entries/{entry_id}/save", response_class=HTMLResponse)
def save_entry_route(request: Request, entry_id: int):
    entry = get_entry(entry_id)
    if entry and not entry["is_saved"]:
        path = write_entry_file({
            "title": entry["title"],
            "source_name": entry["source_name"],
            "source_folder": entry["source_folder"],
            "author": entry.get("author") or "",
            "pub_date": entry.get("pub_date") or "",
            "url": entry.get("url") or "",
            "audio_path": entry.get("audio_path") or "",
            "description": entry.get("description") or "",
            "tags": [t["name"] for t in get_entry_tags(entry_id)],
        })
        save_entry(entry_id, file_path=str(path))
    return _save_button_response(request, entry_id)


@router.post("/entries/{entry_id}/unsave", response_class=HTMLResponse)
def unsave_entry_route(request: Request, entry_id: int):
    unsave_entry(entry_id)
    return _save_button_response(request, entry_id)


@router.post("/entries/{entry_id}/tags", response_class=HTMLResponse)
def add_tag(request: Request, entry_id: int, tag_name: str = Form(...)):
    tag = create_tag(tag_name.strip().lower())
    add_tag_to_entry(entry_id, tag["id"])
    return _tags_response(request, entry_id)


@router.delete("/entries/{entry_id}/tags/{tag_id}", response_class=HTMLResponse)
def remove_tag(request: Request, entry_id: int, tag_id: int):
    remove_tag_from_entry(entry_id, tag_id)
    return _tags_response(request, entry_id)
```

- [ ] **Step 4: Create `templates/_entry_tags.html`** (the HTMX swap target for tag updates)

```html
<div class="entry-tags" id="entry-tags-{{ entry.id }}">
    <strong>Tags:</strong>
    {% for tag in tags %}
    <span class="tag">
        {{ tag.name }}
        <button hx-delete="/entries/{{ entry.id }}/tags/{{ tag.id }}"
                hx-target="#entry-tags-{{ entry.id }}"
                hx-swap="outerHTML">×</button>
    </span>
    {% endfor %}
    <input type="text"
           placeholder="Add tag…"
           name="tag_name"
           hx-post="/entries/{{ entry.id }}/tags"
           hx-target="#entry-tags-{{ entry.id }}"
           hx-swap="outerHTML"
           hx-trigger="keydown[key=='Enter']">
</div>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_entries.py -v`

Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
git add routes/entries.py templates/_entry_tags.html tests/test_routes_entries.py
git commit -m "feat: save, unsave, tag routes with tests"
```

---

### Task 17: Search Route & Template

**Files:**
- Create: `routes/search.py`
- Create: `templates/_search_results.html`
- Create: `tests/test_routes_search.py`

- [ ] **Step 1: Create `tests/test_routes_search.py`**

```python
import pytest
from db.sources import create_source
from db.entries import create_entry


@pytest.fixture
def populated_db():
    s = create_source(name="Security Now", type="podcast",
                      feed_url="https://feeds.twit.tv/sn.xml",
                      archive_mode="full_archive", folder_name="security-now")
    create_entry(source_id=s["id"], title="XZ Backdoor Episode",
                 url="https://example.com/1", description="security vulnerability")
    create_entry(source_id=s["id"], title="TCP Fundamentals",
                 url="https://example.com/2", description="networking basics")
    return s


def test_search_returns_results(client, populated_db):
    resp = client.get("/search?q=XZ+Backdoor")
    assert resp.status_code == 200
    assert "XZ Backdoor Episode" in resp.text
    assert "TCP Fundamentals" not in resp.text


def test_search_no_results(client, populated_db):
    resp = client.get("/search?q=quantum+computing")
    assert resp.status_code == 200
    assert "No entries found" in resp.text


def test_search_filtered_by_source(client, populated_db):
    s2 = create_source(name="Other Show", type="rss", feed_url="https://other.com",
                       archive_mode="track_only", folder_name="other-show")
    create_entry(source_id=s2["id"], title="XZ on Other Show",
                 url="https://other.com/1")
    resp = client.get(f"/search?q=XZ&source_id={populated_db['id']}")
    assert "XZ Backdoor Episode" in resp.text
    assert "XZ on Other Show" not in resp.text


def test_search_empty_query_returns_all(client, populated_db):
    resp = client.get("/search?q=")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes_search.py -v`

Expected: FAIL — `/search` route not found

- [ ] **Step 3: Create `routes/search.py`**

```python
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db.entries import list_entries, search_entries

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/search", response_class=HTMLResponse)
def search(
    request: Request,
    q: str = "",
    source_id: Optional[int] = None,
):
    if not q.strip():
        entries = list_entries(source_id=source_id)
    else:
        source_ids = [source_id] if source_id else None
        entries = search_entries(query=q.strip(), source_ids=source_ids)

    return templates.TemplateResponse(
        "_search_results.html",
        {"request": request, "entries": entries, "query": q, "source_id": source_id},
    )
```

- [ ] **Step 4: Create `templates/_search_results.html`**

```html
{% if entries %}
<ul class="entry-list">
    {% for entry in entries %}
    <li class="entry-row {% if not entry.read_at %}unread{% endif %}"
        hx-get="/entries/{{ entry.id }}"
        hx-target="#entry-reader"
        hx-push-url="false">
        <div class="entry-meta">
            <span class="entry-title">{{ entry.title }}</span>
            {% if entry.audio_path %}
            <span class="icon-podcast" title="Podcast episode">🎙</span>
            {% endif %}
        </div>
        <div class="entry-details">
            <span>{{ entry.source_name }}</span>
            {% if entry.author %} · <span>{{ entry.author }}</span>{% endif %}
            {% if entry.pub_date %} · <span>{{ entry.pub_date[:10] }}</span>{% endif %}
        </div>
        {% include "_save_button.html" %}
    </li>
    {% endfor %}
</ul>
{% else %}
<p class="empty-state">No entries found{% if query %} for "{{ query }}"{% endif %}.</p>
{% endif %}
```

- [ ] **Step 5: Register router in `main.py`**

Add to `main.py`:

```python
from routes.search import router as search_router
app.include_router(search_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_search.py -v`

Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add routes/search.py templates/_search_results.html tests/test_routes_search.py main.py
git commit -m "feat: search route and template with tests"
```

---

### Task 18: Audio Serving Route

**Files:**
- Create: `tests/test_routes_audio.py`
- Create: `routes/audio.py`

- [ ] **Step 1: Create `tests/test_routes_audio.py`**

```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_audio(tmp_path, monkeypatch):
    """TestClient with LAESER_LIBRARY_PATH set to a tmp directory containing a real file."""
    monkeypatch.setenv("LAESER_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("LAESER_DB_PATH", str(tmp_path / "test.db"))
    # Create a small audio file to serve
    audio_dir = tmp_path / "test-show"
    audio_dir.mkdir()
    (audio_dir / "episode.mp3").write_bytes(b"\xff\xfb" + b"\x00" * 128)  # minimal MP3 header

    from main import app
    return TestClient(app)


def test_audio_serves_existing_file(client_with_audio):
    resp = client_with_audio.get("/audio/test-show/episode.mp3")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/")


def test_audio_returns_404_for_missing_file(client_with_audio):
    resp = client_with_audio.get("/audio/test-show/nonexistent.mp3")
    assert resp.status_code == 404


def test_audio_returns_403_for_path_traversal(client_with_audio):
    resp = client_with_audio.get("/audio/../laeser.db")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes_audio.py -v`

Expected: FAIL — `ImportError` or 404 on all routes (audio router not registered yet)

- [ ] **Step 3: Create `routes/audio.py`**

```python
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


def get_library_path() -> Path:
    return Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))


@router.get("/audio/{file_path:path}")
def serve_audio(file_path: str):
    """
    Serve an audio file from the library directory.
    file_path is relative to the library root (e.g. "security-now/sn-1047.mp3").
    """
    full_path = get_library_path() / file_path

    # Security: resolve the path and ensure it stays within library
    try:
        resolved = full_path.resolve()
        library_resolved = get_library_path().resolve()
        resolved.relative_to(library_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(str(resolved), media_type="audio/mpeg")
```

- [ ] **Step 4: Register router in `main.py`**

Add to `main.py`:

```python
from routes.audio import router as audio_router
app.include_router(audio_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_routes_audio.py -v`

Expected: All 3 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add routes/audio.py tests/test_routes_audio.py main.py
git commit -m "feat: audio file serving with path traversal protection and tests"
```

---

## Chunk 5: Scheduler, Feed Ingestion & Integration

**Files in this chunk:**
`feeds/scheduler.py`, `routes/sources.py` (refresh endpoint), `main.py` (final wiring), integration smoke test

---

### Task 19: Background Scheduler

**Files:**
- Create: `feeds/scheduler.py`
- Modify: `routes/sources.py` (add refresh route)
- Modify: `main.py` (start scheduler in lifespan)

- [ ] **Step 1: Create `feeds/scheduler.py`**

```python
import logging
from pathlib import Path

# BackgroundScheduler (thread-based) is correct here: refresh_source() is sync blocking I/O.
# AsyncIOScheduler requires coroutines and would block the event loop with sync functions.
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db.entries import create_entry, update_entry_fetch_status
from db.sources import list_sources, update_source_fetch_status
from feeds.downloader import download_file
from feeds.fetcher import fetch_and_parse_feed

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()
REFRESH_INTERVAL_HOURS = 6


def refresh_source(source_id: int, source: dict) -> None:
    """Fetch a source's feed and upsert entries. Downloads audio for full_archive sources."""
    logger.info(f"Refreshing source: {source['name']}")
    try:
        entries = fetch_and_parse_feed(source["feed_url"])
        update_source_fetch_status(source_id, error=None)
    except Exception as e:
        logger.error(f"Failed to fetch {source['name']}: {e}")
        update_source_fetch_status(source_id, error=str(e))
        return

    for parsed in entries:
        entry = create_entry(
            source_id=source_id,
            title=parsed["title"] or "Untitled",
            url=parsed["url"],
            author=parsed.get("author"),
            description=parsed.get("description"),
            pub_date=parsed.get("pub_date"),
            duration=parsed.get("duration"),
        )
        update_entry_fetch_status(entry["id"], "ok")

        if source["archive_mode"] == "full_archive" and parsed.get("enclosure_url"):
            _download_audio(entry, parsed["enclosure_url"], source["folder_name"])


def _download_audio(entry: dict, url: str, folder_name: str) -> None:
    """Download audio for an entry if not already present."""
    from db.entries import update_entry_audio_path
    import os

    library = Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))
    ext = url.split(".")[-1].split("?")[0] or "mp3"
    filename = f"{entry['pub_date'][:10] if entry.get('pub_date') else 'unknown'}-{entry['id']}.{ext}"
    dest = library / folder_name / filename

    if dest.exists():
        return  # already downloaded

    success = download_file(url, dest, delay_seconds=3)
    if success:
        # Store path relative to library root (e.g. "security-now/sn-1047.mp3")
        # The /audio/{file_path} route appends this to the library root to serve the file.
        audio_path = str(dest.relative_to(library))
        update_entry_audio_path(entry["id"], audio_path)
        logger.info(f"Audio saved: {audio_path}")


def refresh_all() -> None:
    """Refresh all non-manual sources."""
    for source in list_sources():
        if source["type"] == "manual" or not source.get("feed_url"):
            continue
        refresh_source(source["id"], source)


def setup_scheduler(app) -> None:
    """Attach scheduler to app lifespan — start on startup, stop on shutdown."""
    _scheduler.add_job(
        refresh_all,
        trigger=IntervalTrigger(hours=REFRESH_INTERVAL_HOURS),
        id="refresh_all",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler started — refreshing every {REFRESH_INTERVAL_HOURS}h")


def shutdown_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Add manual refresh endpoint to `routes/sources.py`**

Add to `routes/sources.py`:

```python
from starlette.concurrency import run_in_threadpool

from feeds.scheduler import refresh_source as do_refresh


@router.post("/sources/{source_id}/refresh", response_class=HTMLResponse)
async def refresh_source_route(request: Request, source_id: int):
    # run_in_threadpool offloads the sync blocking refresh_source() to a thread,
    # keeping the FastAPI event loop free during the feed fetch.
    from db.sources import get_source
    source = get_source(source_id)
    if source:
        await run_in_threadpool(do_refresh, source_id, source)
    return _sidebar_response(request)
```

- [ ] **Step 3: Wire scheduler into `main.py` lifespan**

Update `main.py`:

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db.schema import init_db
from feeds.scheduler import setup_scheduler, shutdown_scheduler
from routes.sources import router as sources_router
from routes.entries import router as entries_router
from routes.search import router as search_router
from routes.audio import router as audio_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    setup_scheduler(app)
    yield
    shutdown_scheduler()


app = FastAPI(title="Laeser", lifespan=lifespan)

Path("static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(sources_router)
app.include_router(entries_router)
app.include_router(search_router)
app.include_router(audio_router)
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add feeds/scheduler.py routes/sources.py main.py
git commit -m "feat: APScheduler background feed refresh + manual refresh route"
```

---

### Task 20: Integration Smoke Test

**Files:**
- No new files — manual verification steps

- [ ] **Step 1: Start the app**

Run: `uv run uvicorn main:app --reload`

Expected: Server starts at http://127.0.0.1:8000, DB initialised, scheduler running.

- [ ] **Step 2: Add a podcast source**

Open http://127.0.0.1:8000 in the browser.

Click "+ Add Source" and add:
- Feed URL: `https://feeds.twit.tv/sn.xml`
- Name: `Security Now`
- Type: Podcast
- Archive Mode: Track Only

Expected: Sidebar refreshes and shows "Security Now".

- [ ] **Step 3: Trigger a manual refresh**

In the sidebar, click the "Refresh" button next to "Security Now" (rendered by `_sidebar.html`).

Alternatively, use browser DevTools to look up the actual source ID and trigger manually:
```js
// Step 1: find the source ID from the page HTML
document.querySelector('[hx-post^="/sources/"]').getAttribute('hx-post')
// e.g. returns "/sources/2/refresh" — use that ID
fetch('/sources/2/refresh', {method: 'POST'})
```

Expected: Feed fetched, entries appear in entry list.

- [ ] **Step 4: Browse and read an entry**

Click "Security Now" in sidebar → entry list appears. Click an entry → reader panel shows title, description, metadata.

Expected: Entry row becomes visually "read" (not bold) after opening.

- [ ] **Step 5: Save an entry**

Click the ☆ star on an entry.

Expected: Star turns to ★. Check `library/security-now/` — a markdown file exists with correct frontmatter.

- [ ] **Step 6: Search**

Type a keyword in the search bar.

Expected: Entry list updates as you type (debounced). Results match keyword in title or description.

- [ ] **Step 7: Final commit**

```bash
# Stage only tracked source files — not library/, laeser.db, or .venv/
git add -u
git status  # verify nothing unintended is staged
git commit -m "chore: v0.1 integration verified — laeser complete"
```
