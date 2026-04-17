# Obsidian Vault Compatibility — Design

**Status:** Draft
**Date:** 2026-04-17

## Purpose

Make Laeser's `library/` folder a pleasant Obsidian reading experience so the user can optionally point a dedicated Obsidian vault at it and browse saved podcasts and articles there. Laeser remains the product and the system of record; Obsidian is a viewer only.

## Direction

One-way flow: Laeser writes, Obsidian reads. Any edits made to files inside Obsidian are out of scope and will be overwritten the next time Laeser rewrites the entry. The web app reads entry content from SQLite (`entries.description`), not from the filesystem, so changes to the on-disk file format have no effect on the web reader.

## Scope

Four deliverables:

1. Convert HTML descriptions to Markdown when writing saved entries.
2. Rename downloaded MP3s to a `YYYY-MM-DD-slug.mp3` scheme that matches the entry's markdown filename.
3. Prepend an Obsidian audio embed (`![[…mp3]]`) to the body of entries that have audio.
4. Provide a one-shot migration script that upgrades entries already on disk.

Out of scope: bidirectional sync, Obsidian-side edits flowing back into Laeser, per-source index notes, Dataview scaffolding, plugin/config generation inside the vault.

## Components touched

- `storage.py` — HTML→Markdown conversion, audio embed insertion.
- `feeds/downloader.py` — use the new filename scheme when saving MP3s and storing `audio_path`.
- New `naming.py` — single source of truth for `slugify`, `date_prefix`, and the `"<date>-<slug>"` base used by both markdown and audio filenames.
- `pyproject.toml` — add `markdownify` dependency.
- New `scripts/migrate_vault.py` — one-shot upgrader for existing saved entries.
- `tests/` — new cases for conversion, naming, embed, migration.

## HTML → Markdown body

In `storage.py::write_entry_file`, run `entry["description"]` through `markdownify.markdownify(...)` before passing it as the body of the `frontmatter.Post`. Empty or missing descriptions continue to produce an empty body. Frontmatter structure (title, source, author, pub_date, url, audio_path, tags) is unchanged.

SQLite's `entries.description` is left as HTML. This is intentional: the web reader sanitizes it with `nh3.clean` and renders it as HTML; converting in the DB would regress that path. Conversion happens only at the moment we write to disk.

## Audio filename scheme

Today: `feeds/downloader.py` saves the MP3 under a name derived from the feed item (often ugly and truncated, e.g. `Thu, 01 Ap-435.mp3`) and stores that relative path in `entries.audio_path`.

New: MP3s are saved at `library/<source_folder>/<YYYY-MM-DD>-<slug>.mp3`, using the same date-prefix and slug logic as the markdown file. The `entries.audio_path` column is updated to that relative path. Both markdown and audio filenames for a given entry therefore share a base (e.g. `2026-03-14-in-our-time-voltaire.md` + `2026-03-14-in-our-time-voltaire.mp3`) so they sit next to each other in Obsidian's file explorer.

The slug + date-prefix helpers currently inlined in `storage.py` move into a shared `naming.py` module and both `storage.py` and `feeds/downloader.py` import from it. The old helper definitions in `storage.py` are removed; any call sites switch to the new import.

## Audio embed in body

In `write_entry_file`, if `entry["audio_path"]` is non-empty, prepend

```
![[<basename-of-audio-path>]]

```

to the Markdown body before constructing the `frontmatter.Post`. Obsidian renders this as an inline audio player pinned to the top of the note. The web app never reads the body and is unaffected.

The embed uses only the audio file's basename (not the `<source_folder>/` prefix) because the markdown file lives in the same folder as the audio; Obsidian's wikilink resolver finds it by filename.

## One-shot migration

`scripts/migrate_vault.py` is a CLI script that walks every row in `entries` where `is_saved = 1` and brings it into the new format:

1. Compute the new audio filename from `pub_date` (or today if missing) and `slugify(title)`.
2. If an MP3 exists at the current `audio_path`, rename it on disk to the new path. Update `entries.audio_path` to the new relative path.
3. Call `write_entry_file(...)` on the entry so the `.md` file is rewritten with Markdown body and audio embed. The old `.md` file, if named identically, is overwritten; if named differently (unlikely given existing logic), the old one is removed after the new one is written.
4. The old row's `file_path` column (if present) is updated.

Flags:

- `--dry-run`: print planned actions (file renames, file rewrites, DB updates) without touching disk or DB.
- No other flags; the script is meant to be run once.

Idempotency: running the script a second time with no intervening changes must produce no file renames, no body diffs, and no DB writes. Tests assert this.

## Testing

New tests (added to the existing `tests/` tree, following the project's existing pytest patterns):

- `write_entry_file` with HTML description → asserts body is Markdown, frontmatter preserved, file path unchanged.
- `write_entry_file` with `audio_path` set → asserts `![[…mp3]]` appears at the top of the body.
- `write_entry_file` with `audio_path` empty → asserts no embed is inserted.
- Shared `naming` helpers → unit tests for slug edge cases (unicode, very long titles, empty titles, punctuation) and date-prefix fallback when `pub_date` missing.
- Downloader → monkeypatch the HTTP fetch; assert the MP3 is written at `library/<source>/<date>-<slug>.mp3` and `entries.audio_path` is updated to that relative path.
- Migration script → fixture library with one old-format saved entry (HTML body + ugly MP3 name); run migration; assert new filenames, Markdown body, audio embed, updated DB row. Run the migration again and assert zero changes.

## Dependencies

Add `markdownify>=0.11.0` to `[project].dependencies` in `pyproject.toml`. No other dependencies are added or removed.

## Risks and mitigations

- **Markdownify produces unexpected output for some feeds.** Low impact: the web reader is unaffected, and the worst case in Obsidian is that a few entries render oddly. Mitigation: test against a handful of real feed HTML samples (BBC In Our Time, Nieman Lab) as part of the test suite.
- **Migration renames an MP3 that the web app is currently serving.** Low risk for a single-user local tool, but the migration script should be run while the web app is stopped. Document this in the script's `--help` output.
- **Existing `audio_path` values in DB may not resolve on disk** (file was moved or never downloaded). Migration script treats missing files as a no-op rename and logs a warning.
