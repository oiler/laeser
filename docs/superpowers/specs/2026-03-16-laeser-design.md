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

**Manual entry** — a URL or uploaded file added directly by the user, independent of any feed.

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
| archive_mode | TEXT | `track_only` or `full_archive` |
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
| fetch_status | TEXT | `ok`, `fetch_failed`, `pending` |
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
- **Library** below it (saved/archived entries only)
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

Unread entries are visually distinct from read ones.

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
| Manual add | Paste a URL or upload a file directly to the library |
| Refresh feed | Manually trigger a fetch for one or all sources (background, non-blocking) |
| Save entry | Promote entry to library — writes markdown file to `library/source-folder/` |
| Tag entry | Assign one or more tags to a saved entry |
| Download audio | On-demand MP3 download for any podcast entry, even on `track_only` feeds |
| Search | Keyword search across title, author, description; filter by one or more sources |

---

## Search

- Keyword search across `title`, `author`, and `description` fields in SQLite
- Multi-select filter by source name
- Results shown in the center panel, replacing the current entry list
- Implemented via HTMX — search input triggers a background query as the user types (debounced)

---

## Feed Fetching & Parsing

- Polls RSS/Atom feeds using `feedparser` (Python library)
- Deduplication by URL — fetching a feed twice never creates duplicate entries
- For `full_archive` sources: fetches all historical entries on first add, then incrementally on refresh
- Show notes extracted from `<description>` or `<content:encoded>` fields in the RSS XML
- Audio enclosures extracted from `<enclosure>` tags for podcast feeds
- Rate limiting on bulk downloads (polite delays between requests), consistent with existing Security Now scripts

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Feed fetch fails | Logged, source marked with `last_fetch_error`. UI shows warning indicator on source. Other feeds unaffected. |
| Partial audio download | Resumable via HTTP range requests. Checks for existing partial file before starting. |
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

- **HTML-to-markdown processor** — fetch full article text from a URL and convert to markdown for manually added entries
- **Full transcript download** — for shows like Security Now that publish text transcripts
- **AI-powered search / summarisation** — query the library using natural language
- **OPML import** — bulk-import existing feed subscriptions
- **Mobile-friendly layout** — responsive CSS for phone browsing
