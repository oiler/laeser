# Obsidian Vault Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Laeser's `library/` folder pleasant to browse in an Obsidian vault by writing Markdown bodies, naming audio files with the same date-slug base as their markdown notes, and embedding an inline audio player at the top of episodes — plus a one-shot migration for entries already on disk.

**Architecture:** One-way flow — Laeser remains the source of truth; Obsidian only reads files. SQLite entry descriptions stay as HTML (the web reader sanitises and renders them); HTML→Markdown conversion happens at file-write time only. A new `naming.py` module owns the date-slug naming convention shared by markdown and audio files. The audio embed (`![[…mp3]]`) is prepended to the body at write time so Obsidian can play audio inline.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, `python-frontmatter`, `markdownify` (new), pytest.

**Reference spec:** `docs/superpowers/specs/2026-04-17-obsidian-vault-compatibility-design.md`

---

## File Structure

**New files:**
- `naming.py` — slug + date-prefix + entry-base helpers (shared by `storage.py` and `feeds/scheduler.py`).
- `scripts/__init__.py` — empty package marker.
- `scripts/migrate_vault.py` — one-shot CLI script.
- `tests/test_naming.py` — unit tests for the naming helpers.
- `tests/test_migrate_vault.py` — integration test for the migration script.

**Modified files:**
- `pyproject.toml` — add `markdownify` dependency.
- `storage.py` — remove local `slugify`; import from `naming`; convert HTML body to Markdown; prepend audio embed.
- `feeds/scheduler.py` — compute audio filename via `naming.entry_base` instead of `pub_date-id` scheme.
- `tests/test_storage.py` — update import of `slugify` (moves to `naming`), add tests for Markdown conversion and audio embed.
- `tests/test_feeds_downloader.py` — add a scheduler-level test for the new audio filename scheme (no change to existing downloader tests).

---

## Task 1: Add `markdownify` and create the `naming` module

**Files:**
- Modify: `pyproject.toml`
- Create: `naming.py`
- Create: `tests/test_naming.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_naming.py`:

```python
from naming import slugify, date_prefix, entry_base


def test_slugify_basic():
    assert slugify("Hello World!") == "hello-world"


def test_slugify_punctuation_and_parens():
    assert slugify("The XZ Backdoor (2024)") == "the-xz-backdoor-2024"


def test_slugify_truncates_to_80_chars():
    long = "A" * 100
    assert len(slugify(long)) == 80


def test_slugify_collapses_whitespace_and_underscores():
    assert slugify("foo___bar   baz") == "foo-bar-baz"


def test_slugify_strips_unicode_punctuation():
    assert slugify("Café — bonjour") == "café-bonjour"


def test_slugify_empty_string():
    assert slugify("") == ""


def test_date_prefix_uses_pub_date_prefix():
    assert date_prefix("2024-04-02T10:00:00Z") == "2024-04-02"


def test_date_prefix_empty_falls_back_to_today():
    out = date_prefix("")
    assert len(out) == 10
    assert out[4] == "-" and out[7] == "-"


def test_date_prefix_none_falls_back_to_today():
    out = date_prefix(None)
    assert len(out) == 10


def test_entry_base_combines_date_and_slug():
    assert entry_base("Hello World!", "2024-04-02") == "2024-04-02-hello-world"


def test_entry_base_with_missing_date_uses_today():
    out = entry_base("Hello World!", None)
    assert out.endswith("-hello-world")
    assert len(out) == len("YYYY-MM-DD-hello-world")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'naming'`

- [ ] **Step 3: Create `naming.py`**

Create `naming.py` at the project root:

```python
import re
from datetime import datetime, timezone
from typing import Optional


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug, max 80 chars."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:80]


def date_prefix(pub_date: Optional[str]) -> str:
    """
    Return a YYYY-MM-DD prefix from a pub_date string.
    Falls back to today's UTC date if pub_date is missing or empty.
    """
    if pub_date:
        return pub_date[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def entry_base(title: str, pub_date: Optional[str]) -> str:
    """
    Return the shared base name '<YYYY-MM-DD>-<slug>' used for both the
    markdown file and the audio file of an entry.
    """
    return f"{date_prefix(pub_date)}-{slugify(title)}"
```

- [ ] **Step 4: Add `markdownify` to `pyproject.toml`**

Open `pyproject.toml` and add `"markdownify>=0.11.0"` to the `[project].dependencies` list. After:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.9",
    "feedparser>=6.0.11",
    "apscheduler>=3.10.0",
    "requests>=2.31.0",
    "python-frontmatter>=1.1.0",
    "nh3>=0.3.3",
    "markdownify>=0.11.0",
]
```

Then run `uv sync` to install it:

Run: `uv sync`
Expected: Resolves and installs `markdownify`. No error output.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_naming.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock naming.py tests/test_naming.py
git commit -m "feat: add naming module and markdownify dependency"
```

---

## Task 2: Refactor `storage.py` to use the `naming` module

**Files:**
- Modify: `storage.py`
- Modify: `tests/test_storage.py:4` (import)

- [ ] **Step 1: Update `tests/test_storage.py` import**

Change line 4 of `tests/test_storage.py` from:

```python
from storage import write_entry_file, slugify
```

to:

```python
from storage import write_entry_file
from naming import slugify
```

- [ ] **Step 2: Run the existing storage tests to confirm they still pass after the import change is the only refactor**

Run: `uv run pytest tests/test_storage.py -v`
Expected: All 4 existing tests still PASS (slugify, write_entry_file_creates_file, write_entry_file_frontmatter, write_entry_file_overwrites_on_resave).

(If this fails because `storage.py` still exports `slugify`, that's fine — the next step removes it.)

- [ ] **Step 3: Refactor `storage.py`**

Replace `storage.py` with:

```python
import os
from pathlib import Path

import frontmatter

from naming import entry_base


def get_library_path() -> Path:
    """Return library path. Override with LAESER_LIBRARY_PATH env var for testing."""
    return Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))


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

    base = entry_base(entry["title"], entry.get("pub_date"))
    file_path = source_folder / f"{base}.md"

    post = frontmatter.Post(
        entry.get("description") or "",
        title=entry["title"],
        source=entry["source_name"],
        author=entry.get("author") or "",
        pub_date=entry.get("pub_date") or "",
        url=entry.get("url") or "",
        audio_path=entry.get("audio_path") or "",
        tags=entry.get("tags") or [],
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    return file_path
```

(Removed: top-level `re`, `slugify`, manual date_prefix construction. Slug + date logic now lives in `naming.entry_base`.)

- [ ] **Step 4: Run the existing storage tests to confirm the refactor is behaviour-preserving**

Run: `uv run pytest tests/test_storage.py -v`
Expected: All 4 existing tests PASS.

- [ ] **Step 5: Run the full test suite to catch any other callers**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "refactor: move slug/date helpers from storage to naming module"
```

---

## Task 3: HTML → Markdown body conversion in `write_entry_file`

**Files:**
- Modify: `storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
def test_write_entry_file_converts_html_description_to_markdown(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "HTML Body Test",
        "source_name": "My Show",
        "source_folder": "my-show",
        "author": "",
        "pub_date": "2024-05-01",
        "url": "",
        "audio_path": "",
        "description": "<p>This is <strong>bold</strong> and <a href=\"https://example.com\">a link</a>.</p>",
        "tags": [],
    }
    path = write_entry_file(entry)
    post = frontmatter.load(str(path))
    body = post.content
    # No raw HTML tags should remain
    assert "<p>" not in body
    assert "<strong>" not in body
    assert "<a href" not in body
    # Markdown equivalents should be present
    assert "**bold**" in body
    assert "[a link](https://example.com)" in body


def test_write_entry_file_empty_description_stays_empty(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "No Description",
        "source_name": "My Show",
        "source_folder": "my-show",
        "author": "",
        "pub_date": "2024-05-01",
        "url": "",
        "audio_path": "",
        "description": "",
        "tags": [],
    }
    path = write_entry_file(entry)
    post = frontmatter.load(str(path))
    assert post.content.strip() == ""
```

Also update the existing `test_write_entry_file_frontmatter` test — its `description` is plain text (no HTML), so `markdownify` will pass it through unchanged but may add a trailing newline. Replace the assertion on line 54 from:

```python
    assert post.content == "Episode description."
```

to:

```python
    assert post.content.strip() == "Episode description."
```

Apply the same loosening to `test_write_entry_file_overwrites_on_resave` (line 69):

```python
    assert post.content.strip() == "Updated save."
```

- [ ] **Step 2: Run the failing tests**

Run: `uv run pytest tests/test_storage.py -v`
Expected: The two new tests FAIL (the HTML one because tags remain; the empty one likely passes). Existing tests still pass.

- [ ] **Step 3: Add Markdown conversion to `write_entry_file`**

In `storage.py`, add at the top:

```python
from markdownify import markdownify
```

In `write_entry_file`, change the `post = frontmatter.Post(...)` construction so the body is converted:

```python
    description = entry.get("description") or ""
    body = markdownify(description) if description else ""

    post = frontmatter.Post(
        body,
        title=entry["title"],
        source=entry["source_name"],
        author=entry.get("author") or "",
        pub_date=entry.get("pub_date") or "",
        url=entry.get("url") or "",
        audio_path=entry.get("audio_path") or "",
        tags=entry.get("tags") or [],
    )
```

- [ ] **Step 4: Run the storage tests**

Run: `uv run pytest tests/test_storage.py -v`
Expected: All tests PASS, including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "feat: convert entry HTML descriptions to Markdown on save"
```

---

## Task 4: Audio embed in body

**Files:**
- Modify: `storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
def test_write_entry_file_prepends_audio_embed_when_audio_path_set(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Audio Episode",
        "source_name": "My Show",
        "source_folder": "my-show",
        "author": "",
        "pub_date": "2024-05-01",
        "url": "",
        "audio_path": "my-show/2024-05-01-audio-episode.mp3",
        "description": "Show notes.",
        "tags": [],
    }
    path = write_entry_file(entry)
    post = frontmatter.load(str(path))
    body = post.content
    # Embed must use only the basename, not the full relative path
    assert body.startswith("![[2024-05-01-audio-episode.mp3]]")
    assert "Show notes." in body


def test_write_entry_file_no_embed_when_audio_path_empty(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Text Only",
        "source_name": "My Show",
        "source_folder": "my-show",
        "author": "",
        "pub_date": "2024-05-01",
        "url": "",
        "audio_path": "",
        "description": "Just text.",
        "tags": [],
    }
    path = write_entry_file(entry)
    post = frontmatter.load(str(path))
    assert "![[" not in post.content
```

- [ ] **Step 2: Run the failing tests**

Run: `uv run pytest tests/test_storage.py -v`
Expected: New audio-embed test FAILS (no embed in body yet). Empty-audio test passes (already correct).

- [ ] **Step 3: Add the embed prepend in `write_entry_file`**

In `storage.py`, after computing `body` and before constructing `post`, add:

```python
    audio_path = entry.get("audio_path") or ""
    if audio_path:
        audio_basename = Path(audio_path).name
        body = f"![[{audio_basename}]]\n\n{body}"
```

(Requires `Path` from `pathlib` — already imported.)

- [ ] **Step 4: Run the storage tests**

Run: `uv run pytest tests/test_storage.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run the full suite to ensure nothing else regressed**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add storage.py tests/test_storage.py
git commit -m "feat: embed audio player at top of saved entries for Obsidian"
```

---

## Task 5: Audio filename uses `entry_base` in the scheduler

**Files:**
- Modify: `feeds/scheduler.py:49-65`
- Modify: `tests/test_feeds_downloader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_feeds_downloader.py`:

```python
from unittest.mock import patch
from pathlib import Path
import os

from feeds.scheduler import _download_audio


def test_download_audio_uses_date_slug_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("LAESER_LIBRARY_PATH", str(tmp_path))
    entry = {
        "id": 42,
        "title": "The XZ Backdoor (2024)",
        "pub_date": "2024-04-02",
    }
    captured = {}

    def fake_download(url, dest, delay_seconds=0):
        captured["dest"] = dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"audio")
        return True

    with patch("feeds.scheduler.download_file", side_effect=fake_download), \
         patch("feeds.scheduler.update_entry_audio_path") as mock_update:
        _download_audio(entry, "https://example.com/ep.mp3", "my-show")

    expected = tmp_path / "my-show" / "2024-04-02-the-xz-backdoor-2024.mp3"
    assert captured["dest"] == expected
    mock_update.assert_called_once_with(42, "my-show/2024-04-02-the-xz-backdoor-2024.mp3")


def test_download_audio_preserves_non_mp3_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("LAESER_LIBRARY_PATH", str(tmp_path))
    entry = {"id": 7, "title": "Some Episode", "pub_date": "2024-04-02"}
    captured = {}

    def fake_download(url, dest, delay_seconds=0):
        captured["dest"] = dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"a")
        return True

    with patch("feeds.scheduler.download_file", side_effect=fake_download), \
         patch("feeds.scheduler.update_entry_audio_path"):
        _download_audio(entry, "https://example.com/ep.m4a", "my-show")

    assert captured["dest"].suffix == ".m4a"
    assert captured["dest"].name == "2024-04-02-some-episode.m4a"
```

- [ ] **Step 2: Run the failing tests**

Run: `uv run pytest tests/test_feeds_downloader.py -v`
Expected: The two new tests FAIL — current filename scheme is `<date>-<id>.<ext>`, not `<date>-<slug>.<ext>`.

- [ ] **Step 3: Update `_download_audio` to use `entry_base`**

In `feeds/scheduler.py`, replace lines 49-65 with:

```python
def _download_audio(entry: dict, url: str, folder_name: str) -> None:
    """Download audio for an entry if not already present."""
    library = Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))
    ext = url.split(".")[-1].split("?")[0] or "mp3"
    base = entry_base(entry["title"], entry.get("pub_date"))
    filename = f"{base}.{ext}"
    dest = library / folder_name / filename

    if dest.exists():
        return  # already downloaded

    success = download_file(url, dest, delay_seconds=3)
    if success:
        audio_path = str(dest.relative_to(library))
        update_entry_audio_path(entry["id"], audio_path)
        logger.info(f"Audio saved: {audio_path}")
```

And add the import near the top of `feeds/scheduler.py`:

```python
from naming import entry_base
```

- [ ] **Step 4: Run the failing tests**

Run: `uv run pytest tests/test_feeds_downloader.py -v`
Expected: All tests PASS (including the two new ones).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add feeds/scheduler.py tests/test_feeds_downloader.py
git commit -m "feat: name downloaded audio files with date-slug base"
```

---

## Task 6: One-shot vault migration script

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/migrate_vault.py`
- Create: `tests/test_migrate_vault.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_migrate_vault.py`:

```python
import os
from pathlib import Path

import frontmatter

from db.connection import get_db
from db.entries import create_entry, save_entry, update_entry_audio_path
from db.sources import create_source
from scripts.migrate_vault import migrate


def _make_saved_entry_with_old_format(library: Path) -> dict:
    """Create a source + saved entry in the old format (HTML body, ugly mp3 name)."""
    source = create_source(
        name="My Show",
        type="podcast",
        feed_url="https://example.com/feed",
        archive_mode="full_archive",
        folder_name="my-show",
    )
    entry = create_entry(
        source_id=source["id"],
        title="The XZ Backdoor",
        url="https://example.com/ep",
        guid="ep-1",
        author="Steve",
        description="<p>Show notes with <strong>HTML</strong>.</p>",
        pub_date="2024-04-02",
    )
    # Old-format MP3 on disk
    old_audio_rel = "my-show/2024-04-02-1.mp3"
    (library / "my-show").mkdir(parents=True, exist_ok=True)
    (library / old_audio_rel).write_bytes(b"FAKEAUDIO")
    update_entry_audio_path(entry["id"], old_audio_rel)
    # Old-format markdown file on disk
    old_md = library / "my-show" / "2024-04-02-the-xz-backdoor.md"
    old_md.write_text("---\ntitle: stale\n---\nstale body", encoding="utf-8")
    save_entry(entry["id"], file_path=str(old_md))
    return {
        "entry_id": entry["id"],
        "old_audio_rel": old_audio_rel,
        "old_md": old_md,
    }


def test_migrate_renames_audio_and_rewrites_markdown(tmp_path):
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    info = _make_saved_entry_with_old_format(library)

    migrate(dry_run=False)

    new_audio = library / "my-show" / "2024-04-02-the-xz-backdoor.mp3"
    new_md = library / "my-show" / "2024-04-02-the-xz-backdoor.md"
    assert new_audio.exists()
    assert not (library / info["old_audio_rel"]).exists()

    with get_db() as conn:
        row = conn.execute(
            "SELECT audio_path, file_path FROM entries WHERE id = ?",
            (info["entry_id"],),
        ).fetchone()
    assert row["audio_path"] == "my-show/2024-04-02-the-xz-backdoor.mp3"
    assert row["file_path"] == str(new_md)

    post = frontmatter.load(str(new_md))
    assert post["title"] == "The XZ Backdoor"
    assert post.content.startswith("![[2024-04-02-the-xz-backdoor.mp3]]")
    assert "**HTML**" in post.content
    assert "<p>" not in post.content


def test_migrate_is_idempotent(tmp_path):
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    _make_saved_entry_with_old_format(library)

    migrate(dry_run=False)

    new_md = library / "my-show" / "2024-04-02-the-xz-backdoor.md"
    first_content = new_md.read_text(encoding="utf-8")
    first_mtime = new_md.stat().st_mtime_ns

    migrate(dry_run=False)

    assert new_md.read_text(encoding="utf-8") == first_content
    # Second run may rewrite identical content; what matters is no DB churn and stable filename
    assert new_md.exists()


def test_migrate_dry_run_changes_nothing(tmp_path):
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    info = _make_saved_entry_with_old_format(library)

    migrate(dry_run=True)

    # Old paths still present, no new paths created
    assert (library / info["old_audio_rel"]).exists()
    assert not (library / "my-show" / "2024-04-02-the-xz-backdoor.mp3").exists()

    with get_db() as conn:
        row = conn.execute(
            "SELECT audio_path FROM entries WHERE id = ?",
            (info["entry_id"],),
        ).fetchone()
    assert row["audio_path"] == info["old_audio_rel"]


def test_migrate_skips_entries_with_missing_audio_file(tmp_path):
    """Entry's audio_path points to a file that doesn't exist on disk — log and continue."""
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    source = create_source(
        name="My Show",
        type="podcast",
        feed_url="https://example.com/feed",
        archive_mode="full_archive",
        folder_name="my-show",
    )
    entry = create_entry(
        source_id=source["id"],
        title="Lost Audio",
        url="https://example.com/lost",
        guid="lost-1",
        author="",
        description="No audio on disk.",
        pub_date="2024-04-02",
    )
    update_entry_audio_path(entry["id"], "my-show/nonexistent.mp3")
    save_entry(entry["id"], file_path="ignored")

    migrate(dry_run=False)

    new_md = library / "my-show" / "2024-04-02-lost-audio.md"
    assert new_md.exists()
    # Audio embed should still be written because audio_path was updated to the new name
    # even though the source file was missing — script logs a warning and continues
    with get_db() as conn:
        row = conn.execute(
            "SELECT audio_path FROM entries WHERE id = ?",
            (entry["id"],),
        ).fetchone()
    # Missing-source-file policy: audio_path still gets normalised to the new name,
    # even though no file was renamed. A warning is logged.
    assert row["audio_path"] == "my-show/2024-04-02-lost-audio.mp3"
```

- [ ] **Step 2: Run the failing tests**

Run: `uv run pytest tests/test_migrate_vault.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_vault'`.

- [ ] **Step 3: Create `scripts/__init__.py`**

Create `scripts/__init__.py` as an empty file (so `scripts` is a Python package).

- [ ] **Step 4: Create `scripts/migrate_vault.py`**

```python
"""
One-shot migration: upgrade existing saved entries to the Obsidian-friendly
format introduced in May 2026 — Markdown bodies, date-slug audio filenames,
and inline audio embeds.

Run with the web app stopped to avoid serving an audio file that's mid-rename.

Usage:
    uv run python -m scripts.migrate_vault           # apply
    uv run python -m scripts.migrate_vault --dry-run # preview
"""
import argparse
import logging
import os
from pathlib import Path

from db.connection import get_db
from db.entries import update_entry_audio_path, save_entry
from naming import entry_base
from storage import get_library_path, write_entry_file

logger = logging.getLogger("migrate_vault")


def _saved_entries() -> list[dict]:
    sql = """
        SELECT e.*, s.name AS source_name, s.folder_name AS source_folder
        FROM entries e
        JOIN sources s ON s.id = e.source_id
        WHERE e.is_saved = 1
    """
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def _entry_tags(entry_id: int) -> list[str]:
    sql = """
        SELECT t.name FROM tags t
        JOIN entry_tags et ON et.tag_id = t.id
        WHERE et.entry_id = ?
        ORDER BY t.name
    """
    with get_db() as conn:
        return [r["name"] for r in conn.execute(sql, (entry_id,)).fetchall()]


def _migrate_one(row: dict, library: Path, dry_run: bool) -> None:
    base = entry_base(row["title"], row.get("pub_date"))
    source_folder = row["source_folder"]

    # ---- audio ----
    current_audio_rel = row.get("audio_path") or ""
    new_audio_rel = ""
    if current_audio_rel:
        ext = Path(current_audio_rel).suffix.lstrip(".") or "mp3"
        new_audio_rel = f"{source_folder}/{base}.{ext}"
        current_audio_abs = library / current_audio_rel
        new_audio_abs = library / new_audio_rel

        if current_audio_rel != new_audio_rel:
            if current_audio_abs.exists():
                if dry_run:
                    logger.info(f"DRY-RUN rename: {current_audio_rel} -> {new_audio_rel}")
                else:
                    new_audio_abs.parent.mkdir(parents=True, exist_ok=True)
                    current_audio_abs.rename(new_audio_abs)
                    logger.info(f"renamed: {current_audio_rel} -> {new_audio_rel}")
            else:
                logger.warning(
                    f"audio file missing for entry {row['id']}: {current_audio_rel}"
                )
        if not dry_run:
            update_entry_audio_path(row["id"], new_audio_rel)

    # ---- markdown ----
    new_md_rel = f"{source_folder}/{base}.md"
    new_md_abs = library / new_md_rel
    old_md_abs = Path(row["file_path"]) if row.get("file_path") else None

    entry_dict = {
        "title": row["title"],
        "source_name": row["source_name"],
        "source_folder": source_folder,
        "author": row.get("author") or "",
        "pub_date": row.get("pub_date") or "",
        "url": row.get("url") or "",
        "audio_path": new_audio_rel,
        "description": row.get("description") or "",
        "tags": _entry_tags(row["id"]),
    }

    if dry_run:
        logger.info(f"DRY-RUN rewrite: {new_md_rel}")
        if old_md_abs and old_md_abs.exists() and old_md_abs != new_md_abs:
            logger.info(f"DRY-RUN delete stale: {old_md_abs}")
        return

    written = write_entry_file(entry_dict)
    save_entry(row["id"], file_path=str(written))
    logger.info(f"wrote: {new_md_rel}")

    if old_md_abs and old_md_abs.exists() and old_md_abs != written:
        old_md_abs.unlink()
        logger.info(f"deleted stale: {old_md_abs}")


def migrate(dry_run: bool = False) -> None:
    library = get_library_path()
    rows = _saved_entries()
    logger.info(f"Migrating {len(rows)} saved entries (dry_run={dry_run})")
    for row in rows:
        try:
            _migrate_one(row, library, dry_run)
        except Exception as exc:
            logger.error(f"entry {row['id']} failed: {exc}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without touching disk or DB.",
    )
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the migration tests**

Run: `uv run pytest tests/test_migrate_vault.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/__init__.py scripts/migrate_vault.py tests/test_migrate_vault.py
git commit -m "feat: add one-shot vault migration script"
```

---

## Final verification

- [ ] **Step 1: Run the full test suite one last time**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 2: Manually smoke-test the web app**

Run: `uv run uvicorn main:app --reload`
Visit http://127.0.0.1:8000 in a browser. Confirm:
- Sources load.
- An entry's reader pane renders HTML correctly (sanitised by `nh3`, unchanged by this work).
- Saving an entry creates a `.md` file under `library/<source>/`.
- Open that file and verify: Markdown body, `![[…mp3]]` embed at the top if there's audio.

Kill the server with Ctrl+C.

- [ ] **Step 3: Optional — run the migration against the real library**

If the user wants to upgrade existing saved entries:

```bash
uv run python -m scripts.migrate_vault --dry-run   # preview
uv run python -m scripts.migrate_vault             # apply
```

- [ ] **Step 4: Open the library in Obsidian (manual, optional)**

Point a new Obsidian vault at `library/`. Confirm:
- Each source is a folder.
- Saved entries render as Markdown.
- Episodes with audio show an inline player.
