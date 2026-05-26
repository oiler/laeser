# Sticky Bulk Toolbar & Preserve Selection — Design

Date: 2026-05-21
Scope: Two small UX bugs in the entry-list pane.

## Bug 1 — Bulk toolbar is not visibly sticky

### Symptom

When the user scrolls a long episode list, the search bar stays pinned at the top of the entry-list pane (correct), but the bulk action toolbar (`Save selected`, `Download audio`, `Clear`) scrolls away with the list.

### Root cause

In `static/style.css`, both `.search-bar` and `.bulk-toolbar` are declared `position: sticky; top: 0` inside the same scroll container (`<main id="entry-list">`, which has `overflow-y: auto`). The search bar has `z-index: 10`; the toolbar has `z-index: 9`. The toolbar *is* sticking — it is just sitting at the same offset as the search bar and being painted underneath it.

### Fix

CSS-only. Change `.bulk-toolbar` so it sticks just below the search bar instead of at the same offset:

```css
.bulk-toolbar { ... position: sticky; top: 45px; z-index: 9; ... }
```

The search bar measures ~45px tall in current styling (10px vertical padding × 2 + ~25px input row including border). If visual tuning shows a gap or overlap, adjust by a pixel or two. No markup change required.

Rejected alternative: wrap both elements in a shared `<header>` so they sit naturally without sticky math. Larger refactor for no real gain, since the toolbar is conditionally rendered and the search bar is always present.

## Bug 2 — Selection lost after bulk action

### Symptom

User multi-selects rows, clicks `Save selected` or `Download audio`. The action succeeds, the list re-renders, but every row is unchecked. To act on the same selection again the user has to re-select from scratch.

### Root cause

`POST /entries/save-bulk` and `POST /entries/download-bulk` both re-render `_entry_list.html` with `hx-swap="innerHTML"` on `#entry-list`. The fresh DOM has no memory of which checkboxes were checked before the swap.

### Fix

Server-side: have the action endpoints tell the template which IDs were just acted on, and have the template mark those checkboxes `checked`. Three small additions, all extending existing code paths.

1. **`routes/entries.py` — `save_bulk` and `download_bulk`**

   Add `selected_ids=set(entry_ids)` to the template context.

   In the plain `entry_list` GET handler, pass `selected_ids=set()` so the template can rely on the key always existing.

2. **`templates/_entry_list.html` — checkbox markup**

   ```jinja
   <input type="checkbox" class="entry-checkbox" name="entry_ids"
          value="{{ entry.id }}" data-index="{{ loop.index0 }}"
          {% if entry.id in selected_ids %}checked{% endif %}>
   ```

3. **No new JS.** The existing toolbar-init script already calls `updateToolbar()` on load, so the "N selected" pill and toolbar visibility will reflect any pre-checked boxes automatically.

### Edge cases

- **Saved-only view after Save:** A bulk save can only add saved-state, never remove it, so every preserved ID is still present in the re-rendered list.
- **Audio download:** Does not filter the visible list. Preserved IDs remain present.
- **Empty selection POST:** Already a no-op in both endpoints. `selected_ids` will be an empty set; template falls through to unchecked.
- **Toolbar count on first render of a filtered list:** `selected_ids` is empty for normal GETs, so the toolbar stays hidden as today.

## Out of scope

- Persisting selection across full page reloads or HTMX navigation between source filters.
- Showing a toast / confirmation summary of what was acted on.
- Refactoring the entry-list header into a shared container.
