# Bulk Audio Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user select multiple episodes and download their audio files via a single sequential background worker that is polite to hosts and never floods the local machine.

**Architecture:** A new `feeds/download_queue.py` owns a thread-safe queue and one daemon worker thread, started/stopped by the app lifespan. A new `POST /entries/download-bulk` endpoint enqueues eligible entries. Download lifecycle state is persisted in a new `audio_status` column so the entry list renders progress on re-render; on startup the worker re-enqueues interrupted entries.

**Tech Stack:** FastAPI, Jinja2, HTMX 2.0, SQLite, Python `queue`/`threading`, APScheduler (existing), pytest.

---

## File Structure

- `db/schema.py` — add `enclosure_url` and `audio_status` columns to the `entries` table plus migrations for existing databases.
- `db/entries.py` — `create_entry` gains an `enclosure_url` param; add `set_audio_status`, `set_enclosure_url`, `list_entries_by_audio_status`.
- `feeds/scheduler.py` — pass `enclosure_url` into `create_entry`; refactor `_download_audio` to use the shared path helper.
- `feeds/downloader.py` — add `audio_dest_path` helper (with the extensionless-URL fix).
- `feeds/download_queue.py` — **new.** Queue, worker thread, `enqueue`, `process_download`, `start_worker`, `stop_worker`.
- `main.py` — start/stop the download worker in the app lifespan.
- `routes/entries.py` — add `POST /entries/download-bulk`.
- `templates/_entry_list.html` — add the "Download audio" toolbar button and per-row status indicator.
- `static/style.css` — style the status indicator.
- `scripts/backfill_enclosure_urls.py` — **new.** One-shot enclosure-URL backfill.
- Tests: `tests/test_db_entries.py`, `tests/test_feeds_downloader.py`, `tests/test_download_queue.py` (new), `tests/test_routes_entries.py`, `tests/test_backfill_enclosure_urls.py` (new).

---

### Task 1: Data model — enclosure URL and audio status

**Files:**
- Modify: `db/schema.py`
- Modify: `db/entries.py`
- Modify: `feeds/scheduler.py`
- Test: `tests/test_db_entries.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_db_entries.py`:

```python
def test_create_entry_stores_enclosure_url(source):
    from db.entries import create_entry, get_entry
    e = create_entry(source_id=source["id"], title="With Audio",
                      url="https://example.com/wa", enclosure_url="https://cdn.example.com/wa.mp3")
    assert get_entry(e["id"])["enclosure_url"] == "https://cdn.example.com/wa.mp3"


def test_new_entry_audio_status_defaults_to_none(source):
    from db.entries import create_entry, get_entry
    e = create_entry(source_id=source["id"], title="No Audio Yet",
                      url="https://example.com/nay")
    assert get_entry(e["id"])["audio_status"] == "none"


def test_set_audio_status(source):
    from db.entries import create_entry, get_entry, set_audio_status
    e = create_entry(source_id=source["id"], title="Status Ep", url="https://example.com/se")
    set_audio_status(e["id"], "queued")
    assert get_entry(e["id"])["audio_status"] == "queued"


def test_set_enclosure_url(source):
    from db.entries import create_entry, get_entry, set_enclosure_url
    e = create_entry(source_id=source["id"], title="Backfill Ep", url="https://example.com/be")
    set_enclosure_url(e["id"], "https://cdn.example.com/be.mp3")
    assert get_entry(e["id"])["enclosure_url"] == "https://cdn.example.com/be.mp3"


def test_list_entries_by_audio_status(source):
    from db.entries import create_entry, set_audio_status, list_entries_by_audio_status
    e1 = create_entry(source_id=source["id"], title="Q1", url="https://example.com/q1")
    e2 = create_entry(source_id=source["id"], title="D1", url="https://example.com/d1")
    create_entry(source_id=source["id"], title="N1", url="https://example.com/n1")
    set_audio_status(e1["id"], "queued")
    set_audio_status(e2["id"], "downloading")
    ids = {e["id"] for e in list_entries_by_audio_status(["queued", "downloading"])}
    assert ids == {e1["id"], e2["id"]}
```

`tests/test_db_entries.py` may not already define a `source` fixture — check the top of the file. If it does not, add this fixture near the top:

```python
import pytest
from db.sources import create_source


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                         feed_url="https://feeds.twit.tv/sn.xml",
                         archive_mode="full_archive", folder_name="security-now")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_db_entries.py -k "enclosure or audio_status" -v`
Expected: FAIL — `enclosure_url` parameter / `set_audio_status` / `set_enclosure_url` / `list_entries_by_audio_status` do not exist, and the columns are missing.

- [ ] **Step 3: Add the columns to the schema**

In `db/schema.py`, in the `_SCHEMA` string, replace the `entries` table definition with this version (adds `enclosure_url` after `audio_path`, and `audio_status` after the `fetch_status` block):

```sql
CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    INTEGER NOT NULL REFERENCES sources(id),
    title        TEXT NOT NULL,
    author       TEXT,
    pub_date     TEXT,
    url          TEXT UNIQUE,
    guid         TEXT UNIQUE,
    description  TEXT,
    duration     TEXT,
    audio_path   TEXT,
    enclosure_url TEXT,
    file_path    TEXT,
    is_saved     INTEGER NOT NULL DEFAULT 0,
    read_at      TEXT,
    fetch_status TEXT NOT NULL DEFAULT 'pending'
                 CHECK(fetch_status IN ('pending', 'ok', 'fetch_failed')),
    audio_status TEXT NOT NULL DEFAULT 'none'
                 CHECK(audio_status IN ('none', 'queued', 'downloading', 'downloaded', 'failed')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Add the migrations for existing databases**

In `db/schema.py`, in `init_db()`, after the existing `guid` migration block and before the `CREATE UNIQUE INDEX` line, add:

```python
        if "enclosure_url" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN enclosure_url TEXT")
        if "audio_status" not in cols:
            conn.execute(
                "ALTER TABLE entries ADD COLUMN audio_status TEXT NOT NULL DEFAULT 'none' "
                "CHECK(audio_status IN ('none', 'queued', 'downloading', 'downloaded', 'failed'))"
            )
            conn.execute(
                "UPDATE entries SET audio_status = 'downloaded' "
                "WHERE audio_path IS NOT NULL AND audio_status = 'none'"
            )
```

(`cols` is the snapshot taken once at the top of `init_db`; each `if` checks it independently, matching the existing `guid` pattern.)

- [ ] **Step 5: Update `create_entry` and add the new DB functions**

In `db/entries.py`, change `create_entry` to accept and store `enclosure_url`. Replace its signature and `INSERT` statement:

```python
def create_entry(
    source_id: int,
    title: str,
    url: Optional[str] = None,
    guid: Optional[str] = None,
    author: Optional[str] = None,
    description: Optional[str] = None,
    pub_date: Optional[str] = None,
    duration: Optional[str] = None,
    enclosure_url: Optional[str] = None,
) -> dict:
    """Create entry; silently returns existing row on duplicate guid or URL."""
    import sqlite3 as _sqlite3
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO entries (source_id, title, url, guid, author, description, pub_date, duration, enclosure_url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (source_id, title, url, guid, author, description, pub_date, duration, enclosure_url),
            )
            row = conn.execute(_SELECT + "WHERE e.id = ?", (cursor.lastrowid,)).fetchone()
            return _row(row)
    except _sqlite3.IntegrityError:
        # Duplicate guid or URL — fetch existing entry
        with get_db() as conn:
            if guid:
                row = conn.execute(_SELECT + "WHERE e.guid = ?", (guid,)).fetchone()
                if row:
                    return _row(row)
            row = conn.execute(_SELECT + "WHERE e.url = ?", (url,)).fetchone()
            return _row(row)
```

Then add these three functions at the end of `db/entries.py`:

```python
def set_audio_status(entry_id: int, status: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE entries SET audio_status = ? WHERE id = ?", (status, entry_id))


def set_enclosure_url(entry_id: int, url: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE entries SET enclosure_url = ? WHERE id = ?", (url, entry_id))


def list_entries_by_audio_status(statuses: list[str]) -> list[dict]:
    placeholders = ",".join("?" * len(statuses))
    sql = _SELECT + f"WHERE e.audio_status IN ({placeholders})"
    with get_db() as conn:
        return [_row(r) for r in conn.execute(sql, statuses).fetchall()]
```

- [ ] **Step 6: Pass `enclosure_url` through the scheduler**

In `feeds/scheduler.py`, in `refresh_source`, the `create_entry(...)` call adds one argument. Change it to:

```python
        entry = create_entry(
            source_id=source_id,
            title=parsed["title"] or "Untitled",
            url=parsed["url"],
            guid=parsed.get("guid"),
            author=parsed.get("author"),
            description=parsed.get("description"),
            pub_date=parsed.get("pub_date"),
            duration=parsed.get("duration"),
            enclosure_url=parsed.get("enclosure_url"),
        )
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_db_entries.py tests/test_feeds_fetcher.py -v`
Expected: PASS — all new tests pass and existing entry/fetcher tests still pass.

- [ ] **Step 8: Commit**

```bash
git add db/schema.py db/entries.py feeds/scheduler.py tests/test_db_entries.py
git commit -m "feat: persist enclosure_url and audio_status on entries"
```

---

### Task 2: Audio path helper and extensionless-URL fix

**Files:**
- Modify: `feeds/downloader.py`
- Modify: `feeds/scheduler.py`
- Test: `tests/test_feeds_downloader.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_feeds_downloader.py`:

```python
def test_audio_dest_path_normal_extension():
    from pathlib import Path
    from feeds.downloader import audio_dest_path
    dest = audio_dest_path(Path("/lib"), "security-now", "Episode 1047", "2026-05-01",
                           "https://cdn.example.com/sn1047.mp3")
    assert dest == Path("/lib/security-now/2026-05-01-episode-1047.mp3")


def test_audio_dest_path_strips_query_string():
    from pathlib import Path
    from feeds.downloader import audio_dest_path
    dest = audio_dest_path(Path("/lib"), "pod", "Ep", "2026-05-01",
                           "https://cdn.example.com/ep.mp3?token=abc123")
    assert dest.suffix == ".mp3"


def test_audio_dest_path_extensionless_url_falls_back_to_mp3():
    from pathlib import Path
    from feeds.downloader import audio_dest_path
    dest = audio_dest_path(Path("/lib"), "pod", "Ep", "2026-05-01",
                           "https://cdn.example.com/stream/12345")
    assert dest.suffix == ".mp3"


def test_audio_dest_path_dotted_path_no_real_extension_falls_back():
    from pathlib import Path
    from feeds.downloader import audio_dest_path
    # last segment has a dot but the "extension" is too long to be real
    dest = audio_dest_path(Path("/lib"), "pod", "Ep", "2026-05-01",
                           "https://example.com/audio.somelongtoken")
    assert dest.suffix == ".mp3"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_feeds_downloader.py -k audio_dest_path -v`
Expected: FAIL — `audio_dest_path` does not exist.

- [ ] **Step 3: Add the `audio_dest_path` helper**

In `feeds/downloader.py`, add these imports at the top (alongside the existing imports):

```python
from urllib.parse import urlparse

from naming import entry_base
```

Then add this function at the end of `feeds/downloader.py`:

```python
def audio_dest_path(
    library: Path,
    folder_name: str,
    title: str,
    pub_date: Optional[str],
    url: str,
) -> Path:
    """Build the on-disk destination for an entry's audio file.

    The extension is taken from the URL's last path segment only when it is a
    short alphanumeric token; otherwise it falls back to 'mp3'. This avoids the
    garbage extensions produced by extensionless URLs.
    """
    last_segment = urlparse(url).path.rsplit("/", 1)[-1]
    ext = last_segment.rsplit(".", 1)[-1] if "." in last_segment else ""
    if not (ext and len(ext) <= 5 and ext.isalnum()):
        ext = "mp3"
    return library / folder_name / f"{entry_base(title, pub_date)}.{ext}"
```

- [ ] **Step 4: Refactor `_download_audio` to use the helper**

In `feeds/scheduler.py`, add `audio_dest_path` to the downloader import:

```python
from feeds.downloader import audio_dest_path, download_file
```

Then replace the body of `_download_audio` with:

```python
def _download_audio(entry: dict, url: str, folder_name: str) -> None:
    """Download audio for an entry if not already present."""
    library = Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))
    dest = audio_dest_path(library, folder_name, entry["title"], entry.get("pub_date"), url)

    if dest.exists():
        return  # already downloaded

    success = download_file(url, dest, delay_seconds=3)
    if success:
        audio_path = str(dest.relative_to(library))
        update_entry_audio_path(entry["id"], audio_path)
        logger.info(f"Audio saved: {audio_path}")
```

(The `entry_base` import in `scheduler.py` is now unused — remove it from the imports if present: the line `from naming import entry_base`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_feeds_downloader.py tests/test_feeds_fetcher.py -v`
Expected: PASS — `audio_dest_path` tests pass, existing downloader tests still pass.

- [ ] **Step 6: Commit**

```bash
git add feeds/downloader.py feeds/scheduler.py tests/test_feeds_downloader.py
git commit -m "feat: add audio_dest_path helper with extensionless-URL fix"
```

---

### Task 3: Download queue and worker

**Files:**
- Create: `feeds/download_queue.py`
- Modify: `main.py`
- Test: `tests/test_download_queue.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_download_queue.py`:

```python
import pytest

from db.sources import create_source
from db.entries import create_entry, get_entry, set_audio_status


@pytest.fixture(autouse=True)
def _drain_queue():
    """The download queue is module-level state; drain it around every test."""
    from feeds import download_queue
    while not download_queue._queue.empty():
        download_queue._queue.get_nowait()
    yield
    while not download_queue._queue.empty():
        download_queue._queue.get_nowait()


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                         feed_url="https://feeds.twit.tv/sn.xml",
                         archive_mode="full_archive", folder_name="security-now")


def test_enqueue_sets_queued_status(source):
    from feeds.download_queue import enqueue
    e = create_entry(source_id=source["id"], title="Ep", url="https://example.com/e",
                     enclosure_url="https://cdn.example.com/e.mp3")
    enqueue(e["id"])
    assert get_entry(e["id"])["audio_status"] == "queued"


def test_process_download_success(source, monkeypatch):
    from feeds import download_queue
    e = create_entry(source_id=source["id"], title="Good Ep", pub_date="2026-05-01",
                     url="https://example.com/g", enclosure_url="https://cdn.example.com/g.mp3")
    monkeypatch.setattr(download_queue, "download_file", lambda url, dest: True)
    download_queue.process_download(e["id"])
    row = get_entry(e["id"])
    assert row["audio_status"] == "downloaded"
    assert row["audio_path"] == "security-now/2026-05-01-good-ep.mp3"


def test_process_download_failure(source, monkeypatch):
    from feeds import download_queue
    e = create_entry(source_id=source["id"], title="Bad Ep",
                     url="https://example.com/b", enclosure_url="https://cdn.example.com/b.mp3")
    monkeypatch.setattr(download_queue, "download_file", lambda url, dest: False)
    download_queue.process_download(e["id"])
    assert get_entry(e["id"])["audio_status"] == "failed"


def test_process_download_skips_entry_without_enclosure_url(source, monkeypatch):
    from feeds import download_queue
    e = create_entry(source_id=source["id"], title="No URL", url="https://example.com/nu")

    def _fail(url, dest):
        raise AssertionError("download_file should not be called")

    monkeypatch.setattr(download_queue, "download_file", _fail)
    download_queue.process_download(e["id"])
    assert get_entry(e["id"])["audio_status"] == "none"


def test_requeue_pending_enqueues_queued_and_downloading(source):
    from feeds import download_queue
    e1 = create_entry(source_id=source["id"], title="Q", url="https://example.com/q",
                      enclosure_url="https://cdn.example.com/q.mp3")
    e2 = create_entry(source_id=source["id"], title="D", url="https://example.com/d",
                      enclosure_url="https://cdn.example.com/d.mp3")
    set_audio_status(e1["id"], "queued")
    set_audio_status(e2["id"], "downloading")
    download_queue._requeue_pending()
    requeued = set()
    while not download_queue._queue.empty():
        requeued.add(download_queue._queue.get_nowait())
    assert requeued == {e1["id"], e2["id"]}


def test_worker_processes_enqueued_entry(source, monkeypatch):
    from feeds import download_queue
    monkeypatch.setattr(download_queue, "download_file", lambda url, dest: True)
    download_queue.start_worker()
    try:
        e = create_entry(source_id=source["id"], title="Worker Ep", pub_date="2026-05-01",
                         url="https://example.com/w", enclosure_url="https://cdn.example.com/w.mp3")
        download_queue.enqueue(e["id"])
        download_queue._queue.join()
        assert get_entry(e["id"])["audio_status"] == "downloaded"
    finally:
        download_queue.stop_worker()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_download_queue.py -v`
Expected: FAIL — `feeds/download_queue.py` does not exist (collection error).

- [ ] **Step 3: Create the download queue module**

Create `feeds/download_queue.py`:

```python
import logging
import os
import queue
import threading
from pathlib import Path
from typing import Optional

from db.entries import (
    get_entry,
    list_entries_by_audio_status,
    set_audio_status,
    update_entry_audio_path,
)
from feeds.downloader import audio_dest_path, download_file

logger = logging.getLogger(__name__)

# Module-level queue of entry IDs; None is the worker-stop sentinel.
_queue: "queue.Queue" = queue.Queue()
_worker: Optional[threading.Thread] = None


def enqueue(entry_id: int) -> None:
    """Mark an entry queued and put it on the download queue."""
    set_audio_status(entry_id, "queued")
    _queue.put(entry_id)


def process_download(entry_id: int) -> None:
    """Download one entry's audio. No-ops on a missing entry, an entry with no
    enclosure URL, or an entry whose audio is already on disk."""
    entry = get_entry(entry_id)
    if not entry or not entry.get("enclosure_url") or entry.get("audio_path"):
        return
    set_audio_status(entry_id, "downloading")
    library = Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))
    dest = audio_dest_path(
        library, entry["source_folder"], entry["title"],
        entry.get("pub_date"), entry["enclosure_url"],
    )
    if download_file(entry["enclosure_url"], dest):
        update_entry_audio_path(entry_id, str(dest.relative_to(library)))
        set_audio_status(entry_id, "downloaded")
    else:
        set_audio_status(entry_id, "failed")


def _worker_loop() -> None:
    while True:
        entry_id = _queue.get()
        if entry_id is None:  # stop sentinel
            _queue.task_done()
            return
        try:
            process_download(entry_id)
        except Exception:
            logger.exception(f"Download failed for entry {entry_id}")
            try:
                set_audio_status(entry_id, "failed")
            except Exception:
                logger.exception(f"Could not mark entry {entry_id} as failed")
        finally:
            _queue.task_done()


def _requeue_pending() -> None:
    """Re-enqueue entries left mid-flight by a previous run."""
    for entry in list_entries_by_audio_status(["queued", "downloading"]):
        _queue.put(entry["id"])


def start_worker() -> None:
    """Start the download worker, re-enqueuing any interrupted entries first."""
    global _worker
    if _worker and _worker.is_alive():
        return
    _requeue_pending()
    _worker = threading.Thread(target=_worker_loop, daemon=True, name="download-worker")
    _worker.start()
    logger.info("Download worker started")


def stop_worker() -> None:
    """Signal the worker to exit and wait briefly for it."""
    global _worker
    if _worker and _worker.is_alive():
        _queue.put(None)
        _worker.join(timeout=2)
    _worker = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_download_queue.py -v`
Expected: PASS — all seven download-queue tests pass.

- [ ] **Step 5: Wire the worker into the app lifespan**

In `main.py`, add the import alongside the scheduler import:

```python
from feeds.scheduler import setup_scheduler, shutdown_scheduler
from feeds.download_queue import start_worker, stop_worker
```

Then update the `lifespan` function so it starts the worker on startup and stops it on shutdown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    setup_scheduler(app)
    start_worker()
    yield
    stop_worker()
    shutdown_scheduler()
```

- [ ] **Step 6: Run the full suite to confirm nothing broke**

Run: `uv run pytest -q`
Expected: PASS — all tests pass. (The `client` fixture does not run the lifespan, so the worker does not start during route tests.)

- [ ] **Step 7: Commit**

```bash
git add feeds/download_queue.py main.py tests/test_download_queue.py
git commit -m "feat: add single-worker download queue with startup recovery"
```

---

### Task 4: Bulk-download endpoint

**Files:**
- Modify: `routes/entries.py`
- Test: `tests/test_routes_entries.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_routes_entries.py`:

```python
def test_download_bulk_enqueues_eligible_entries(client, source):
    from db.entries import create_entry, get_entry as db_get
    e1 = create_entry(source_id=source["id"], title="DL A", url="https://example.com/dla",
                      enclosure_url="https://cdn.example.com/dla.mp3")
    e2 = create_entry(source_id=source["id"], title="DL B", url="https://example.com/dlb",
                      enclosure_url="https://cdn.example.com/dlb.mp3")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e1["id"])["audio_status"] == "queued"
    assert db_get(e2["id"])["audio_status"] == "queued"


def test_download_bulk_skips_entry_without_enclosure_url(client, source):
    from db.entries import create_entry, get_entry as db_get
    e = create_entry(source_id=source["id"], title="No Enclosure", url="https://example.com/ne")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e["id"])["audio_status"] == "none"


def test_download_bulk_skips_already_downloaded(client, source):
    from db.entries import create_entry, get_entry as db_get
    from db.entries import update_entry_audio_path, set_audio_status
    e = create_entry(source_id=source["id"], title="Done", url="https://example.com/done",
                     enclosure_url="https://cdn.example.com/done.mp3")
    update_entry_audio_path(e["id"], "security-now/done.mp3")
    set_audio_status(e["id"], "downloaded")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e["id"])["audio_status"] == "downloaded"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_routes_entries.py -k download_bulk -v`
Expected: FAIL — the `/entries/download-bulk` route does not exist (405).

- [ ] **Step 3: Add the endpoint**

In `routes/entries.py`, add this import near the other `feeds`/`db` imports at the top:

```python
from feeds.download_queue import enqueue
```

Then add this route immediately after the `save_bulk` route:

```python
@router.post("/entries/download-bulk", response_class=HTMLResponse)
def download_bulk(
    request: Request,
    entry_ids: list[int] = Form(default=[]),
    source_id: Optional[int] = Form(None),
    saved: bool = Form(False),
    sort: str = Form("desc"),
):
    for entry_id in entry_ids:
        entry = get_entry(entry_id)
        if (
            entry
            and entry.get("enclosure_url")
            and not entry.get("audio_path")
            and entry["audio_status"] not in ("queued", "downloading")
        ):
            enqueue(entry_id)
    entries = list_entries(source_id=source_id, saved_only=saved, sort=sort)
    return templates.TemplateResponse(
        request, "_entry_list.html",
        {"entries": entries, "source_id": source_id, "saved": saved, "sort": sort},
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_routes_entries.py -v`
Expected: PASS — the three download-bulk tests pass and all existing route tests still pass.

- [ ] **Step 5: Commit**

```bash
git add routes/entries.py tests/test_routes_entries.py
git commit -m "feat: add download-bulk endpoint that enqueues selected episodes"
```

---

### Task 5: UI — Download button and per-row status indicator

**Files:**
- Modify: `templates/_entry_list.html`
- Modify: `static/style.css`
- Test: `tests/test_routes_entries.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_routes_entries.py`:

```python
def test_toolbar_has_download_button(client, entry):
    resp = client.get("/entries")
    assert 'hx-post="/entries/download-bulk"' in resp.text
    assert "Download audio" in resp.text


def test_entry_list_shows_download_status_icons(client, source):
    from db.entries import create_entry, set_audio_status
    e = create_entry(source_id=source["id"], title="Queued Ep", url="https://example.com/qe")
    set_audio_status(e["id"], "queued")
    resp = client.get("/entries")
    assert "Audio download queued" in resp.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_routes_entries.py -k "download_button or status_icons" -v`
Expected: FAIL — the download button and status icons are not in the template yet.

- [ ] **Step 3: Add the "Download audio" toolbar button**

In `templates/_entry_list.html`, the toolbar currently contains a `bulk-save-btn` button followed by the `bulk-clear` button. Add the download button between them. Find:

```html
            hx-swap="innerHTML">Save selected</button>
    <button type="button" id="bulk-clear">Clear</button>
```

Replace it with:

```html
            hx-swap="innerHTML">Save selected</button>
    <button type="button"
            class="bulk-download-btn"
            hx-post="/entries/download-bulk"
            hx-include=".entry-checkbox, #bulk-context"
            hx-target="#entry-list"
            hx-swap="innerHTML">Download audio</button>
    <button type="button" id="bulk-clear">Clear</button>
```

- [ ] **Step 4: Add the per-row status indicator**

In `templates/_entry_list.html`, the title cell currently is:

```html
        <td class="col-title">
            {{ entry.title }}
            {% if entry.audio_path %}<span class="icon-podcast" title="Podcast episode">🎙</span>{% endif %}
        </td>
```

Replace it with:

```html
        <td class="col-title">
            {{ entry.title }}
            {% if entry.audio_path %}<span class="icon-podcast" title="Podcast episode">🎙</span>
            {% elif entry.audio_status == "queued" %}<span class="icon-audio-status" title="Audio download queued">⏳</span>
            {% elif entry.audio_status == "downloading" %}<span class="icon-audio-status" title="Downloading audio">↓</span>
            {% elif entry.audio_status == "failed" %}<span class="icon-audio-status" title="Audio download failed">⚠</span>
            {% endif %}
        </td>
```

- [ ] **Step 5: Add the CSS**

In `static/style.css`, find the existing rule:

```css
.icon-podcast { font-size: 10px; margin-left: 3px; color: #888; }
```

Add this line directly after it:

```css
.icon-audio-status { font-size: 10px; margin-left: 3px; color: #888; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_routes_entries.py -v`
Expected: PASS — the toolbar/status tests pass and all existing route tests still pass.

- [ ] **Step 7: Manual verification**

Start the app (`uv run uvicorn main:app --reload`), select a source, select episodes, and click "Download audio". Confirm the rows show `⏳`, and that after the worker runs they show `🎙` (or `⚠` on failure) once the list is re-rendered (switch source or re-sort).

- [ ] **Step 8: Commit**

```bash
git add templates/_entry_list.html static/style.css tests/test_routes_entries.py
git commit -m "feat: add Download audio button and per-row audio status icons"
```

---

### Task 6: Enclosure-URL backfill script

**Files:**
- Create: `scripts/backfill_enclosure_urls.py`
- Test: `tests/test_backfill_enclosure_urls.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backfill_enclosure_urls.py`:

```python
import pytest

from db.sources import create_source
from db.entries import create_entry, get_entry


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                         feed_url="https://feeds.twit.tv/sn.xml",
                         archive_mode="full_archive", folder_name="security-now")


def _fake_feed(items):
    def _fetch(url):
        return items
    return _fetch


def test_backfill_fills_null_enclosure_url(source, monkeypatch):
    from scripts import backfill_enclosure_urls as bf
    e = create_entry(source_id=source["id"], title="Ep", url="https://example.com/ep",
                     guid="guid-ep")
    assert get_entry(e["id"])["enclosure_url"] is None
    monkeypatch.setattr(bf, "fetch_and_parse_feed", _fake_feed([
        {"guid": "guid-ep", "url": "https://example.com/ep",
         "enclosure_url": "https://cdn.example.com/ep.mp3"},
    ]))
    bf.backfill()
    assert get_entry(e["id"])["enclosure_url"] == "https://cdn.example.com/ep.mp3"


def test_backfill_leaves_existing_enclosure_url_untouched(source, monkeypatch):
    from scripts import backfill_enclosure_urls as bf
    e = create_entry(source_id=source["id"], title="Ep2", url="https://example.com/ep2",
                     guid="guid-ep2", enclosure_url="https://cdn.example.com/original.mp3")
    monkeypatch.setattr(bf, "fetch_and_parse_feed", _fake_feed([
        {"guid": "guid-ep2", "url": "https://example.com/ep2",
         "enclosure_url": "https://cdn.example.com/different.mp3"},
    ]))
    bf.backfill()
    assert get_entry(e["id"])["enclosure_url"] == "https://cdn.example.com/original.mp3"


def test_backfill_dry_run_does_not_write(source, monkeypatch):
    from scripts import backfill_enclosure_urls as bf
    e = create_entry(source_id=source["id"], title="Ep3", url="https://example.com/ep3",
                     guid="guid-ep3")
    monkeypatch.setattr(bf, "fetch_and_parse_feed", _fake_feed([
        {"guid": "guid-ep3", "url": "https://example.com/ep3",
         "enclosure_url": "https://cdn.example.com/ep3.mp3"},
    ]))
    bf.backfill(dry_run=True)
    assert get_entry(e["id"])["enclosure_url"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_backfill_enclosure_urls.py -v`
Expected: FAIL — `scripts/backfill_enclosure_urls.py` does not exist (collection error).

- [ ] **Step 3: Create the backfill script**

Create `scripts/backfill_enclosure_urls.py`:

```python
"""
One-shot backfill: populate entries.enclosure_url for existing entries by
re-fetching each source's feed and matching items on guid/url.

Does not download audio and does not create entries — it only fills in
enclosure URLs that are currently null.

Usage:
    uv run python -m scripts.backfill_enclosure_urls           # apply
    uv run python -m scripts.backfill_enclosure_urls --dry-run # preview
"""
import argparse
import logging
from typing import Optional

from db.connection import get_db
from db.entries import set_enclosure_url
from db.sources import list_sources
from feeds.fetcher import fetch_and_parse_feed

logger = logging.getLogger("backfill_enclosure_urls")


def _find_entry(guid: Optional[str], url: Optional[str]) -> Optional[dict]:
    """Find an existing entry by guid, falling back to url."""
    with get_db() as conn:
        if guid:
            row = conn.execute(
                "SELECT id, enclosure_url FROM entries WHERE guid = ?", (guid,)
            ).fetchone()
            if row:
                return dict(row)
        if url:
            row = conn.execute(
                "SELECT id, enclosure_url FROM entries WHERE url = ?", (url,)
            ).fetchone()
            if row:
                return dict(row)
    return None


def backfill(dry_run: bool = False) -> None:
    for source in list_sources():
        if source["type"] == "manual" or not source.get("feed_url"):
            continue
        try:
            items = fetch_and_parse_feed(source["feed_url"])
        except Exception as exc:
            logger.error(f"{source['name']}: feed fetch failed: {exc}")
            continue

        updated = skipped = 0
        for item in items:
            if not item.get("enclosure_url"):
                continue
            entry = _find_entry(item.get("guid"), item.get("url"))
            if not entry or entry["enclosure_url"]:
                skipped += 1
                continue
            if dry_run:
                logger.info(f"DRY-RUN set enclosure_url for entry {entry['id']}")
            else:
                set_enclosure_url(entry["id"], item["enclosure_url"])
            updated += 1
        logger.info(f"{source['name']}: updated {updated}, skipped {skipped}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned updates without touching the DB.",
    )
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_backfill_enclosure_urls.py -v`
Expected: PASS — all three backfill tests pass.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — every test passes.

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_enclosure_urls.py tests/test_backfill_enclosure_urls.py
git commit -m "feat: add one-shot enclosure-URL backfill script"
```

---

## Self-Review Notes

- **Spec coverage:** `enclosure_url`/`audio_status` columns + migration (Task 1), `create_entry`/`set_audio_status`/`set_enclosure_url`/`list_entries_by_audio_status` (Task 1), `audio_dest_path` + extensionless fix + scheduler refactor (Task 2), download queue/worker/startup-recovery + lifespan wiring (Task 3), `POST /entries/download-bulk` with eligibility filter (Task 4), toolbar button + row indicators + CSS (Task 5), backfill script (Task 6) — every spec section maps to a task.
- **Type consistency:** `audio_status` values (`none`/`queued`/`downloading`/`downloaded`/`failed`) are identical across the schema CHECK, the migration, `process_download`, the endpoint filter, and the template. `audio_dest_path`'s signature `(library, folder_name, title, pub_date, url)` is used identically in `scheduler._download_audio` and `download_queue.process_download`. The worker-stop sentinel is `None` everywhere.
- **No placeholders:** every step contains complete code and exact commands.
- **Worker safety:** the `client` test fixture does not run the app lifespan, so the worker thread never starts during route tests; `test_download_queue.py` drains the module queue around every test and the one worker-thread test stops the worker in a `finally`.
