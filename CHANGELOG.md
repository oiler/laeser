# Changelog

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
