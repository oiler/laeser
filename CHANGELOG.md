# Changelog

## v1.1.0 — Local Service (2026-05-20)

Adds a way to run Laeser as a persistent always-on service on your Mac, plus README polish and a proper favicon.

### Added

**Always-on local service**
- macOS launchd LaunchAgent supervises a no-reload `uvicorn` process on `127.0.0.1:8473`, reachable at `http://app.laeser.org:8473` after a one-line `/etc/hosts` entry
- `deploy/install.sh` — idempotent setup that locates `uv`, advises on the hosts entry, renders the plist into the repo, and migrates away from any earlier broken install
- `deploy/laeserctl` — `start` / `stop` / `restart` / `status` / `logs` wrapper around `launchctl`, controlling the service by load state rather than signals so a clean stop actually stays stopped
- Survives closing the terminal; restarts automatically on crash; does not auto-start on reboot

**Polish**
- `## Example` section in the README with a screenshot of the reader
- Favicon (`favicon.ico`), modern SVG favicon, and Apple touch icon — served from a new `/assets` mount and wired into the base layout
- `## Running as a service` section in the README, including how to change the service port

## v1.0.0 — First Stable Release (2026-05-19)

First stable release. Adds Obsidian vault compatibility, bulk episode selection,
and bulk audio downloading on top of the v0.1 reader.

### Added

**Obsidian vault compatibility**
- Saved entries are written as Markdown notes with an audio player embedded at the top
- Audio files and their Markdown notes share a `YYYY-MM-DD-slug` basename so Obsidian `![[ ]]` embeds resolve
- One-shot vault migration script (`scripts/migrate_vault.py`) to upgrade pre-existing saved entries

**Bulk episode selection**
- Checkbox column in the entry list with select-all, Shift+click range selection, and a live selection count
- Bulk-action toolbar with "Save selected" — saves many episodes to the vault in one action
- Saved episodes are visually tinted in the list

**Bulk audio download**
- "Download audio" toolbar action — downloads audio for the selected episodes
- A single sequential background worker drains a download queue: polite to hosts, never floods the machine; interrupted batches resume on restart
- Per-row audio status icons (queued / downloading / downloaded / failed)
- One-shot enclosure-URL backfill script (`scripts/backfill_enclosure_urls.py`) for episodes downloaded before URLs were stored

### Changed
- Entry HTML descriptions are converted to Markdown when saved to the vault
- Downloaded audio filenames use the shared `YYYY-MM-DD-slug` basename

### Fixed
- Entries are deduplicated by `guid`, handling feeds with rotating access-token URLs
- Audio URLs with no file extension no longer produce malformed filenames

## v0.1 — Initial Release (2026-03-17)

Built from the implementation plan in `docs/superpowers/plans/2026-03-16-laeser-implementation.md`.

### Added during integration (beyond original spec)

**Feed handling**
- Auto-refresh feed on source creation — no need to click ↻ after adding a source
- Refresh button (↻) in sidebar for on-demand feed fetches
- Tolerant bozo handling — feeds with minor encoding declaration mismatches (e.g. us-ascii declared but utf-8 parsed) are no longer rejected if entries were successfully parsed
- `pub_date` normalized to `YYYY-MM-DD` at parse time using feedparser's `published_parsed`

**Entry list**
- Sortable date column — click "Date ↑/↓" header to toggle sort order
- Source column hidden when browsing a single source (shown only in All Items view)
- Date column always displays as `YYYY-MM-DD`

**Search**
- Search bar persists across results (was disappearing after first search)
- Replaced live autocomplete with explicit Search button and ✕ clear button

**Entry reader**
- Episode notes rendered as HTML using `nh3` sanitizer (was showing raw HTML as escaped text)

**Source management**
- Source settings panel (⚙ per source in sidebar) — shows feed URL, type, archive mode, last fetch time and errors
- Remove source with confirmation checkbox — prevents accidental deletion

**Bug fixes**
- Fixed sidebar `hx-swap="outerHTML"` bug that caused `#sidebar` id to be lost after the first HTMX swap
