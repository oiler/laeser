# Bulk Audio Download — Design

**Date:** 2026-05-18
**Status:** Approved (pending spec review)

## Goal

Let the user select multiple episodes in the entry list and download their audio
files in one action. Downloads run on a single background worker — polite to the
hosting servers and never flooding the local machine — and each row shows the
download state.

This is the feature anticipated by the "Future Extension" section of
`docs/superpowers/specs/2026-05-18-episode-bulk-selection-design.md`. The
selection layer (checkbox column, Shift+click range, select-all, toolbar) already
exists and is action-agnostic; this feature adds a second toolbar action and the
download machinery behind it.

## Scope

In scope:

- Persist the audio enclosure URL on entries (new column + migration).
- A persisted per-entry audio download status.
- A single-worker download queue with safe startup recovery.
- A `POST /entries/download-bulk` endpoint that enqueues selected episodes.
- A "Download audio" toolbar button and per-row status indicators.
- A one-shot script to backfill enclosure URLs for existing entries.
- Fix the deferred extensionless-audio-URL bug while refactoring the path logic.

Out of scope:

- Concurrent or per-host-parallel downloading (a single sequential worker is the
  chosen model).
- Live progress polling — status updates only when the entry list re-renders.
- Bulk audio *deletion*, re-download of already-downloaded audio, or a download
  history view.
- Changing how `full_archive` sources auto-download during refresh.

## Architecture

A new `feeds/download_queue.py` owns a thread-safe `queue.Queue` of entry IDs and
one daemon worker thread, started and stopped by the app lifespan alongside the
existing `BackgroundScheduler`. The bulk-download endpoint validates and enqueues
selected entries; the worker drains the queue one entry at a time, reusing the
existing `feeds/downloader.download_file` (which already enforces a polite
pre-download delay and HTTP-range resume).

Download lifecycle state is persisted in a new `audio_status` column on
`entries`, so the entry list renders the current state on every re-render with no
polling. Because state is persisted, an interrupted batch is recoverable: on
startup the worker re-enqueues every entry still marked `queued` or `downloading`.

The single worker satisfies both user constraints structurally — exactly one
download runs at a time (never floods the local machine), and the per-download
delay in `download_file` spaces out requests to any host.

## Data Model

`db/schema.py`, two new columns on `entries`, with migrations following the
existing `guid`-column pattern in `init_db()`:

- `enclosure_url TEXT` — the audio file URL from the feed enclosure. Nullable;
  entries created before this change have it null until backfilled.
- `audio_status TEXT NOT NULL DEFAULT 'none'` with
  `CHECK(audio_status IN ('none','queued','downloading','downloaded','failed'))`.
  This is the download lifecycle; `audio_path` remains the on-disk file location.
  When `audio_status='downloaded'`, `audio_path` is set.

Migration: after adding `audio_status`, run a one-time
`UPDATE entries SET audio_status='downloaded' WHERE audio_path IS NOT NULL AND audio_status='none'`
so `full_archive` episodes already on disk show the correct state. (SQLite's
`ALTER TABLE ADD COLUMN` with a non-constant default is not allowed, so the
column is added with default `'none'` and the backfill `UPDATE` runs separately —
the same shape as the existing `guid` migration.)

`db/entries.py` changes:

- `create_entry` gains an `enclosure_url: Optional[str] = None` parameter, stored
  in the `INSERT`. On the duplicate-guid/url path it still returns the existing
  row unchanged (no clobber).
- New `set_audio_status(entry_id: int, status: str) -> None`.
- New `set_enclosure_url(entry_id: int, url: str) -> None` — used by the backfill
  script.
- New `list_entries_by_audio_status(statuses: list[str]) -> list[dict]` — used at
  startup to find entries to re-enqueue.

## Components

### 1. Audio path helper — `feeds/downloader.py`

Extract the destination-path logic currently inline in
`feeds/scheduler.py:_download_audio` into a reusable function:

```python
def audio_dest_path(library: Path, folder_name: str, title: str,
                    pub_date: Optional[str], url: str) -> Path
```

It builds `library / folder_name / f"{entry_base(title, pub_date)}.{ext}"`.

**Extensionless-URL fix:** the current extension parsing
(`url.split(".")[-1].split("?")[0]`) produces a garbage extension when the URL
path has no `.` — e.g. a whole URL becomes the "extension". The helper instead
parses the URL path, takes the last path segment, and uses its suffix only when
it is a short alphanumeric token (≤5 chars); otherwise it falls back to `mp3`.

`scheduler.py:_download_audio` is updated to call this helper, so the scheduler
and the queue worker compute identical paths.

### 2. Download queue & worker — `feeds/download_queue.py` (new)

- Module-level `queue.Queue` of `int` entry IDs and a single
  `threading.Thread(daemon=True)`.
- `enqueue(entry_id: int) -> None` — sets `audio_status='queued'` via
  `set_audio_status`, then `queue.put(entry_id)`.
- `process_download(entry_id: int) -> None` — the unit of work, written as a
  plain synchronous function for testability:
  1. Load the entry. If it is gone, or has no `enclosure_url`, or already has
     `audio_path`, return without changes.
  2. `set_audio_status(entry_id, 'downloading')`.
  3. Resolve the library path and `audio_dest_path(...)`.
  4. Call `download_file(enclosure_url, dest)` (default polite delay).
  5. On success: `update_entry_audio_path` with the library-relative path, then
     `set_audio_status(entry_id, 'downloaded')`. On failure:
     `set_audio_status(entry_id, 'failed')`.
- The worker loop: `entry_id = queue.get()`; call `process_download` inside a
  `try/except` that logs and sets `audio_status='failed'` on an unexpected
  exception, so one bad entry never kills the thread; `queue.task_done()`.
- `start_worker() -> None` — re-enqueues every entry returned by
  `list_entries_by_audio_status(['queued', 'downloading'])`, then starts the
  thread (idempotent — a no-op if already running).
- `stop_worker() -> None` — signals the worker to exit (a sentinel `None` on the
  queue) and joins briefly.

### 3. App lifespan — `main.py`

`lifespan` calls `start_worker()` after `setup_scheduler(app)`, and
`stop_worker()` before `shutdown_scheduler()`.

### 4. Bulk-download endpoint — `routes/entries.py`

`POST /entries/download-bulk`, parameters mirroring `save_bulk`:
`entry_ids: list[int] = Form(default=[])`, `source_id: Optional[int] = Form(None)`,
`saved: bool = Form(False)`, `sort: str = Form("desc")`.

For each ID it enqueues only *eligible* entries — an entry is eligible when it
has a non-null `enclosure_url`, has no `audio_path`, and its `audio_status` is
not already `queued` or `downloading`. Ineligible IDs are silently skipped (the
same pattern as `save_bulk` skipping already-saved entries). It then returns the
re-rendered `_entry_list.html` via `list_entries(source_id=source_id, saved_only=saved, sort=sort)`,
so rows immediately show `queued`.

### 5. UI — `templates/_entry_list.html`, `static/style.css`

- A second toolbar button, "Download audio", beside "Save selected" in
  `#bulk-toolbar`. Same `hx-include=".entry-checkbox, #bulk-context"`,
  `hx-target="#entry-list"`, `hx-swap="innerHTML"`; `hx-post="/entries/download-bulk"`.
  No JavaScript change — the existing selection script is action-agnostic.
- A per-row download indicator in the title cell, driven by `audio_status`,
  shown after the title alongside the existing podcast icon:
  - `downloaded` (or any row with `audio_path`) → the existing `🎙`.
  - `queued` → `⏳` (title: "Audio download queued").
  - `downloading` → `↓` (title: "Downloading audio").
  - `failed` → `⚠` (title: "Audio download failed").
  - `none` → nothing.
- `style.css` gets a small `.icon-audio-status` rule for muted sizing,
  consistent with the existing `.icon-podcast` rule.

### 6. Backfill script — `scripts/backfill_enclosure_urls.py` (new)

A one-shot script mirroring `scripts/migrate_vault.py`. For every source with a
feed URL, it fetches and parses the feed (`feeds.fetcher.fetch_and_parse_feed`)
and, for each parsed item that has an `enclosure_url`, finds the matching
existing entry (by `guid`, falling back to `url`) and, if that entry's
`enclosure_url` is null, calls `set_enclosure_url`. It does **not** download
audio and does **not** create entries — purely a URL backfill. It prints a
per-source summary (entries updated, skipped) and is idempotent.

## Data Flow

1. User selects episodes and clicks "Download audio". HTMX posts the checked
   `entry_ids` plus `source_id`/`saved`/`sort` to `/entries/download-bulk`.
2. The endpoint filters to eligible entries and calls `enqueue` for each — which
   sets `audio_status='queued'` and puts the ID on the queue.
3. The endpoint re-renders `_entry_list.html`; HTMX swaps it into `#entry-list`.
   Rows now show `⏳`.
4. The worker drains the queue: each entry goes `downloading` (`↓`) then
   `downloaded` (`🎙`, `audio_path` set) or `failed` (`⚠`).
5. The user sees updated states whenever the list next re-renders (sort, search,
   source switch).

## Error Handling

- `download_file` returning `False` → `audio_status='failed'`. `download_file`
  already removes a fresh partial file and preserves a resumable one.
- An unexpected exception inside `process_download` is caught by the worker loop,
  logged, and sets `audio_status='failed'`; the worker continues to the next ID.
- An entry with no `enclosure_url` is never enqueued (endpoint filter); if one
  somehow reaches `process_download` it returns without changes.
- App restart mid-batch: `start_worker()` re-enqueues `queued`/`downloading`
  entries; `download_file` resumes any partial file on disk.
- Episodes that have aged out of their feed and were never downloaded keep
  `enclosure_url IS NULL`, are not eligible, and show no indicator — they are
  simply not downloadable. This is accepted.

## Testing

- `audio_dest_path` — path construction; extension parsing including the
  extensionless-URL fallback to `mp3` and a query-string-laden URL.
- `process_download` — tested synchronously with `feeds.downloader.download_file`
  monkeypatched (no network): success path sets `audio_path` + `downloaded`;
  failure path sets `failed`; an entry with no `enclosure_url` or with existing
  `audio_path` is left unchanged.
- `enqueue` sets `queued` and the startup re-enqueue picks up
  `queued`/`downloading` rows (`list_entries_by_audio_status`).
- `POST /entries/download-bulk` — eligible entries become `queued`, ineligible
  IDs (no URL / already downloaded / already queued) are skipped, the response
  re-renders the list. `download_file` is monkeypatched so no network I/O occurs.
- `create_entry` stores `enclosure_url`; the schema migration adds both columns
  and backfills `audio_status='downloaded'` where `audio_path` is set.
- The backfill script — tested like `tests/test_migrate_vault.py`: a fixture
  feed, assert null URLs are filled and existing URLs untouched, assert no audio
  files are written.
- The worker thread itself is exercised by the `process_download` and `enqueue`
  tests; the thread loop is thin and not separately unit-tested.
