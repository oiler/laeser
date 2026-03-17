# Laeser — Design Spec

**Date:** 2026-03-16
**Project:** Laeser (Danish: *læser*, "reader")

---

## Overview

Laeser is a local, personal hybrid RSS and podcast reader built primarily as a long-term archival system. It runs as a local web application on macOS, accessed via the browser at `localhost`. It solves two related problems:

1. **Evergreen article archival** — web links die, subscriptions lapse. Laeser saves article content locally in portable markdown files so important writing survives.
2. **Podcast library management** — most podcast apps are ephemeral. Laeser treats episodes like documents: indexed, searchable, and downloadable for permanent local storage.

The user opens it a few times per week to browse recent feed items and manage their library.

---

## Core Concepts

**Source** — a feed or publication. Equivalent concepts: a podcast show = an RSS publication. Each source has a folder in the `library/` directory.

**Entry** — an item from a source. Equivalent concepts: a podcast episode = an article. Entries are the atomic unit of the library.

**Feed modes:**
- `track_only` — fetch and index metadata (title, author, pub date, URL, show notes) for all items over time. Never auto-downloads full content or audio.
- `full_archive` — same as track_only, plus automatically downloads all content and audio for every entry.

**Manual entry** — a URL or uploaded file added directly by the user, independent of any feed. Manual entries belong to a single synthetic source row named "Manual Entries" (type `manual`, no feed_url), keeping `source_id` non-nullable throughout the data model.

---

## Architecture

Laeser is a local Python web application with three layers:

### Storage
- **SQLite database** — the query and search engine. Stores all metadata, relationships, and state.
- **`library/` directory** — human-readable archive. One folder per source, one markdown file per entry. Portable and permanent — readable without Laeser.

If the database is ever lost, it can be rebuilt by scanning the `library/` folder.

### Backend
- **FastAPI** — async Python web framework. Handles all feed fetching, RSS/podcast parsing, file writing, and library management.
- **APScheduler** — background scheduler for automatic feed refreshes (default: every 6 hours). Non-blocking — runs independently of the UI.
- **`uv`** — dependency management and script runner, consistent with existing project scripts.

### Frontend
- **Jinja2 templates** — server-rendered HTML.
- **HTMX** — dynamic interactions (live search, background feed refresh status, entry saves) via HTML fragment swaps. No npm, no build step, no JavaScript framework.
- **HTML5 `<audio>`** — native browser audio player for podcast episodes. Supports scrubbing, variable playback speed (1x, 1.5x, 2x), and volume. No external library needed.

---

## Data Model

### SQLite Tables

**`sources`**
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | Display name (e.g., "Security Now") |
| type | TEXT | `podcast`, `rss`, or `manual` |
| feed_url | TEXT | RSS/Atom feed URL |
| archive_mode | TEXT | `track_only` or `full_archive`. `NULL` for the synthetic "Manual Entries" source, which has no feed to archive. |
| folder_name | TEXT | Slug used for `library/` subdirectory |
| last_fetched_at | DATETIME | |
| last_fetch_error | TEXT | NULL if last fetch succeeded |
| created_at | DATETIME | |

**`entries`**
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| source_id | INTEGER FK | References `sources` |
| title | TEXT | |
| author | TEXT | |
| pub_date | DATETIME | |
| url | TEXT | Original URL, used for deduplication |
| description | TEXT | Show notes or article summary from feed |
| duration | TEXT | Podcast duration string (e.g., "01:23:45") |
| audio_path | TEXT | Relative path to downloaded MP3, if any |
| file_path | TEXT | Relative path to markdown file in `library/` |
| is_saved | BOOLEAN | Promoted to library (markdown file written) |
| read_at | DATETIME | NULL = unread. Set when user opens the entry in the reader panel. Used to display unread count badges and visual distinction in the entry list. |
| fetch_status | TEXT | State machine: `pending` (set on add, before fetch attempt), `ok` (fetch succeeded), `fetch_failed` (fetch failed — entry saved with available metadata only). A future `downloading` state can be added when parallel download queuing is introduced. |
| created_at | DATETIME | |

**`tags`**
| Column | Type |
|---|---|
| id | INTEGER PK |
| name | TEXT UNIQUE |

**`entry_tags`**
| Column | Type |
|---|---|
| entry_id | INTEGER FK |
| tag_id | INTEGER FK |

### Markdown File Format

Each saved entry is written as a markdown file with YAML frontmatter:

```markdown
---
title: "Security Now 1047: The XZ Backdoor"
source: "Security Now"
author: "Steve Gibson"
pub_date: 2024-04-02
url: https://twit.tv/shows/security-now/episodes/1047
audio_path: library/security-now/sn-1047.mp3
tags: []
---

Show notes and body content here...
```

### File & Folder Layout

```
library/
  security-now/
    sn-1047.md
    sn-1047.mp3        # only if downloaded
  in-our-time/
    iot-2024-03-15.md
  nytimes/
    article-slug.md
docs/
  superpowers/
    specs/
example-files/
  security-now/
    download_mp3s.py
    download_txts.py
```

---

## UI Layout

The interface has three zones:

### Left Sidebar — Source List
- **All Items** at the top (chronological feed across all sources)
- **Library** below it (all entries where `is_saved = true`, across all sources)
- All sources listed by name with unread count badge
- Add source button at the bottom

### Center Panel — Entry List
Entries for the selected source or view, sorted by pub date (newest first). Each row shows:
- Title
- Source name
- Author
- Pub date
- Save/bookmark icon (toggles `is_saved`)
- Audio indicator icon for podcast entries

Unread entries are visually distinct from read ones. There is no "mark as unread" affordance in V1 — read state is set automatically when an entry is opened and is not manually reversible.

### Right Panel — Entry Reader
- Full markdown content rendered as HTML (show notes / article body)
- Frontmatter metadata (source, author, date, tags)
- Tag editor
- For podcast entries: HTML5 audio player with scrubbing and speed controls, pinned to the bottom of the panel

---

## Key Actions

| Action | Description |
|---|---|
| Add source | Paste a feed URL, set display name, choose `track_only` or `full_archive` |
| Manual add | Paste a URL or upload a `.md` or `.txt` file directly to the library |
| Refresh feed | Manually trigger a fetch for one or all sources (background, non-blocking) |
| Save entry | Promote entry to library — writes markdown file to `library/source-folder/`. If the file already exists (e.g. re-saving after un-saving), it is overwritten. Un-saving sets `is_saved = false` in the database but does **not** delete the markdown file — the file is a permanent archive and removal is a deliberate manual action in Finder. |
| Tag entry | Assign one or more tags to a saved entry |
| Download audio | On-demand MP3 download for any podcast entry, even on `track_only` feeds |
| Search | Keyword search across title, author, description; filter by one or more sources |

---

## Search

- Keyword search across `title`, `author`, and `description` fields in SQLite (V1)
- Raw body content is **not** stored in SQLite — for deep within-source search, use macOS Finder/Spotlight or grep directly on the `library/` markdown files
- Multi-select filter by source name
- Results shown in the center panel, replacing the current entry list
- Implemented via HTMX — search input triggers a background query as the user types (debounced)

---

## Feed Fetching & Parsing

- Polls RSS/Atom feeds using `feedparser` (Python library)
- Deduplication by URL — fetching a feed twice never creates duplicate entries
- For `full_archive` sources: fetches all entries currently exposed by the feed on first add (regardless of when the user subscribes), then incrementally on each refresh. If the feed XML only exposes recent items (e.g. last 20), only those are retrievable via RSS — deeper back-catalogs require a source-specific import script. The existing Security Now scripts (`example-files/security-now/`) are the reference pattern for this.
- Show notes extracted from `<description>` or `<content:encoded>` fields in the RSS XML
- Audio enclosures extracted from `<enclosure>` tags for podcast feeds
- Rate limiting on bulk downloads (polite delays between requests), consistent with existing Security Now scripts

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Feed fetch fails | Logged, source marked with `last_fetch_error`. UI shows warning indicator on source. Other feeds unaffected. |
| Partial audio download | Resumable via HTTP range requests. Checks for existing partial file before starting. |
| Audio download fails (404, timeout, no bytes received) | Logged, `fetch_status` set to `fetch_failed`, any partial file cleaned up. |
| Duplicate entry | Silently skipped — deduplicated by URL. |
| Malformed RSS item | Bad item skipped and logged. Valid items in the same feed still processed. |
| Manual URL fetch fails | Entry saved with available metadata, `fetch_status` set to `fetch_failed`. |

---

## Testing

- **Unit tests** — feed parsing (RSS/Atom XML → entry objects), markdown file generation (frontmatter + body output)
- **Integration tests** — database CRUD operations on sources and entries
- **Manual verification** — HTMX interactions and audio playback tested in the browser

No automated UI tests. The frontend is simple enough to verify manually.

---

## Future Enhancements (Out of Scope for V1)

- **LLM enrichment** — on save, run each entry through an LLM to generate: a 2-3 sentence summary, a topic taxonomy, and key entities (people, companies, technologies). Store in SQLite as enriched metadata. Search targets this enriched data rather than raw body content — smarter than keyword search without duplicating file content. Enabled by default with a global toggle and a per-source override for high-volume or ephemeral feeds where enrichment isn't useful.
- **HTML-to-markdown processor** — fetch full article text from a URL and convert to markdown for manually added entries. Pairs with the LLM enrichment pipeline.
- **Full transcript download** — for shows like Security Now that publish text transcripts alongside episodes
- **Source-specific import scripts** — for shows with predictable URL patterns (e.g. Security Now), scripts that bypass RSS feed limits to download the full back-catalog. The existing Security Now scripts are the reference implementation.
- **OPML import** — bulk-import existing feed subscriptions
- **Mobile-friendly layout** — responsive CSS for phone browsing
