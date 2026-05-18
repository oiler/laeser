# Episode Bulk Selection & Bulk Save — Design

**Date:** 2026-05-18
**Status:** Approved (pending spec review)

## Goal

Let the user select multiple episodes in the entry list and save them all in one
action. Add a clearer visual indicator for episodes already saved.

"Save" means the existing star action: write the entry as a Markdown file to the
Obsidian vault and set `is_saved = 1`. There is exactly one bulk action — bulk
save. No separate "download audio" or "read later" action is in scope.

## Scope

In scope:

- A checkbox column in the entry list with per-row selection.
- Shift+click range selection between the last-clicked checkbox and the current one.
- A select-all checkbox in the table header.
- A bulk-action toolbar that appears when at least one row is selected.
- A `POST /entries/save-bulk` endpoint that saves all selected episodes.
- A stronger row-level indicator for already-saved episodes.

Out of scope:

- Bulk audio download, bulk tagging, bulk unsave.
- Persisting selection across re-renders (sort, search, source switch). Selection
  is client-side and resets whenever the table partial is re-rendered.
- A separate "save for later" / read-later flag distinct from `is_saved`.

## Architecture

The app is server-rendered with HTMX and has no JavaScript today. Selection state
(checkbox state, last-clicked index, live count) is inherently client-side, and
Shift+click range selection cannot be done without JS. Selection therefore lives
in a small inline `<script>` inside `_entry_list.html`. HTMX re-executes scripts
in swapped-in fragments, so the script re-initializes every time the table
re-renders — which also means selection state resets on re-render, as intended.

The bulk save itself is a normal server round-trip: an HTMX `POST` that returns the
re-rendered entry list.

## Components

### 1. Checkbox column — `templates/_entry_list.html`

- New leftmost column. Final column order: checkbox, save, title, [source], date.
- Header cell (`<th class="col-select">`) holds the select-all checkbox.
- Each row's cell holds `<input type="checkbox" class="entry-checkbox"
  name="entry_ids" value="{{ entry.id }}" data-index="{{ loop.index0 }}">`.
- The checkbox cell uses `onclick="event.stopPropagation()"` so clicking it does
  not open the reader — the same pattern the existing `col-save` cell uses.

### 2. Selection behavior — inline `<script>` in `_entry_list.html`

- Plain checkbox click → toggles that one checkbox (native behavior).
- Shift+click on a checkbox → sets every checkbox between the last-clicked index
  and the current index to the current checkbox's checked state.
- The last-clicked index is tracked in a script-scoped variable, updated on every
  checkbox click.
- Select-all checkbox → sets every row checkbox to its checked state. It selects
  **every** visible row, including already-saved rows (re-saving is a harmless
  no-op server-side).
- After any change, the script updates the toolbar: the selected count and
  whether the toolbar is visible.

### 3. Bulk-action toolbar — `templates/_entry_list.html`

- A bar rendered above the `<table>`, hidden by a CSS class when the selected
  count is zero.
- Contents: "*N* selected" text, a "Save selected" button, a "Clear" link.
- "Save selected" is an HTMX `POST /entries/save-bulk`:
  - `hx-include=".entry-checkbox"` so all checked `entry_ids` are submitted.
  - Hidden `source_id` and `sort` inputs are included so the endpoint can
    re-render the list with the same context.
  - `hx-target="#entry-list"`, `hx-swap="innerHTML"` (or equivalent) so the whole
    table re-renders — stars and saved-row styling update, selection clears.
- "Clear" deselects all checkboxes client-side (no server call).

### 4. Bulk save endpoint — `routes/entries.py`

- `POST /entries/save-bulk`, parameters: `entry_ids: list[int] = Form(default=[])`,
  `source_id: Optional[int] = Form(None)`, `sort: str = Form("desc")`.
- The per-entry save logic currently inline in `save_entry_route` is extracted
  into a helper `_save_one(entry_id: int) -> None` that no-ops on missing or
  already-saved entries. Both `save_entry_route` and the bulk route call it.
- The bulk route calls `_save_one` for each id, then returns the re-rendered
  `_entry_list.html` via `list_entries(source_id=source_id, sort=sort)`.

### 5. Saved-row indicator — `templates/_entry_list.html`, `static/style.css`

- The `<tr>` gets a `saved` class when `entry.is_saved` is truthy, alongside the
  existing `unread` class.
- `static/style.css` styles `tr.entry-row.saved` with a subtle tinted background
  so saved episodes stand out at a glance. The filled ★ in the save column stays.

## Data Flow

1. User checks rows (plain or Shift+click) or the select-all box. Inline JS
   updates checkbox state and the toolbar count.
2. User clicks "Save selected". HTMX posts the checked `entry_ids` plus
   `source_id` and `sort` to `/entries/save-bulk`.
3. The endpoint calls `_save_one` per id (each writes a vault file and sets
   `is_saved`; already-saved ids are skipped).
4. The endpoint re-renders `_entry_list.html` and HTMX swaps it into `#entry-list`.
5. The fresh table shows updated stars and saved-row styling; the inline script
   re-runs, so selection is empty and the toolbar is hidden.

## Error Handling

- Empty submission (`entry_ids` empty): the endpoint simply re-renders the list
  unchanged. The toolbar is hidden when nothing is selected, so this is an edge
  case rather than a normal path.
- A missing or already-saved entry id: `_save_one` no-ops, consistent with the
  current single-save route's guard.
- File-write failures inside `write_entry_file` are not specially handled here —
  this design does not change the existing single-save error behavior.

## Future Extension

The selection mechanics are deliberately action-agnostic: the checkbox column,
Shift+click range, select-all, and toolbar produce a set of selected `entry_ids`
and know nothing about what is done with them. The toolbar is built to host
multiple action buttons, not just "Save selected".

A future bulk audio download feature is therefore an additive change, not a
refactor: add a "Download audio" button to the toolbar (reusing the same
selection JS and `entry_ids`) plus a new endpoint. That endpoint differs in kind
from bulk save — audio downloads are long-running, so it must *enqueue* download
jobs and return immediately rather than blocking on a synchronous re-render. The
batching/rate-limiting plumbing for that already exists (`downloader.py`'s
`DEFAULT_DELAY_SECONDS`, `feeds/scheduler.py`). The job-queue infrastructure is
intentionally **not** designed here — it belongs to that separate feature.

## Testing

- `tests/test_routes_entries.py`: add tests for `POST /entries/save-bulk` —
  multiple ids saved, mix of saved/unsaved ids (already-saved skipped), empty
  `entry_ids`, and that the response re-renders the list with correct
  `source_id`/`sort` context.
- The `_save_one` helper is exercised through the route tests; the existing
  single-save route tests continue to pass unchanged after the extraction.
- Selection JavaScript (checkbox toggling, Shift+click range, select-all) is not
  unit-tested — it is straightforward DOM behavior verified by manual check.
