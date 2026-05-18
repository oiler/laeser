# Episode Bulk Selection & Bulk Save Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user select multiple episodes in the entry list (per-row, Shift+click range, select-all) and save them all to the Obsidian vault in one action, with a clear row-level indicator for already-saved episodes.

**Architecture:** Selection state is client-side (a small inline `<script>` in the entry-list partial, re-executed by HTMX on every table re-render). A "Save selected" toolbar button submits the checked entry IDs via an HTMX `POST` to a new `/entries/save-bulk` endpoint, which reuses the existing per-entry save logic and returns the re-rendered table.

**Tech Stack:** FastAPI, Jinja2, HTMX 2.0, SQLite, vanilla JavaScript, pytest.

---

## File Structure

- `routes/entries.py` — add `_save_one` helper (extracted from `save_entry_route`) and the `POST /entries/save-bulk` route.
- `templates/_entry_list.html` — add the checkbox column, select-all header checkbox, bulk-action toolbar, `saved` row class, and the inline selection `<script>`.
- `static/style.css` — styles for the checkbox column, the toolbar, and the saved-row tint.
- `tests/test_routes_entries.py` — tests for the bulk-save endpoint and the saved-row indicator.

---

### Task 1: Backend — `_save_one` helper and bulk-save endpoint

**Files:**
- Modify: `routes/entries.py`
- Test: `tests/test_routes_entries.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_routes_entries.py`:

```python
def test_save_bulk_saves_multiple(client, source):
    from db.entries import create_entry, get_entry as db_get
    e1 = create_entry(source_id=source["id"], title="Bulk A",
                      url="https://example.com/a", description="A")
    e2 = create_entry(source_id=source["id"], title="Bulk B",
                      url="https://example.com/b", description="B")
    resp = client.post("/entries/save-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert "Bulk A" in resp.text and "Bulk B" in resp.text
    assert db_get(e1["id"])["is_saved"] == 1
    assert db_get(e2["id"])["is_saved"] == 1


def test_save_bulk_skips_already_saved(client, source):
    from db.entries import create_entry, get_entry as db_get
    e1 = create_entry(source_id=source["id"], title="Already",
                      url="https://example.com/c", description="C")
    client.post(f"/entries/{e1['id']}/save")
    saved_path = db_get(e1["id"])["file_path"]
    # Bulk-saving an already-saved entry must not change it.
    resp = client.post("/entries/save-bulk",
                       data={"entry_ids": [e1["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e1["id"])["file_path"] == saved_path


def test_save_bulk_empty_selection(client, entry):
    resp = client.post("/entries/save-bulk", data={"sort": "desc"})
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text  # list still renders
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_routes_entries.py -k save_bulk -v`
Expected: FAIL — 404/405, the `/entries/save-bulk` route does not exist yet.

- [ ] **Step 3: Add the `_save_one` helper and refactor the single-save route**

In `routes/entries.py`, add the import `Form` is already imported. Add this helper directly above `save_entry_route` (after `_save_button_response`):

```python
def _save_one(entry_id: int) -> None:
    """Save a single entry to the vault. No-ops on missing or already-saved entries."""
    entry = get_entry(entry_id)
    if entry and not entry["is_saved"]:
        path = write_entry_file({
            "title": entry["title"],
            "source_name": entry["source_name"],
            "source_folder": entry["source_folder"],
            "author": entry.get("author") or "",
            "pub_date": entry.get("pub_date") or "",
            "url": entry.get("url") or "",
            "audio_path": entry.get("audio_path") or "",
            "description": entry.get("description") or "",
            "tags": [t["name"] for t in get_entry_tags(entry_id)],
        })
        save_entry(entry_id, file_path=str(path))
```

Then replace the body of `save_entry_route` so it delegates to the helper:

```python
@router.post("/entries/{entry_id}/save", response_class=HTMLResponse)
def save_entry_route(request: Request, entry_id: int):
    _save_one(entry_id)
    return _save_button_response(request, entry_id)
```

- [ ] **Step 4: Add the bulk-save route**

In `routes/entries.py`, add this route immediately after `entry_list` (the `GET /entries` route):

```python
@router.post("/entries/save-bulk", response_class=HTMLResponse)
def save_bulk(
    request: Request,
    entry_ids: list[int] = Form(default=[]),
    source_id: Optional[int] = Form(None),
    sort: str = Form("desc"),
):
    for entry_id in entry_ids:
        _save_one(entry_id)
    entries = list_entries(source_id=source_id, sort=sort)
    return templates.TemplateResponse(
        request, "_entry_list.html", {"entries": entries, "source_id": source_id, "sort": sort}
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_routes_entries.py -v`
Expected: PASS — all bulk tests pass and the existing `test_save_entry` / `test_unsave_entry` still pass.

- [ ] **Step 6: Commit**

```bash
git add routes/entries.py tests/test_routes_entries.py
git commit -m "feat: add bulk save-bulk endpoint for episodes"
```

---

### Task 2: Template — checkbox column, select-all, toolbar, saved-row class

**Files:**
- Modify: `templates/_entry_list.html`
- Test: `tests/test_routes_entries.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_routes_entries.py`:

```python
def test_entry_list_has_checkboxes(client, entry):
    resp = client.get("/entries")
    assert 'class="entry-checkbox"' in resp.text
    assert 'id="select-all"' in resp.text


def test_saved_entry_row_has_saved_class(client, entry):
    resp = client.get("/entries")
    assert "entry-row unread" in resp.text  # unsaved, no saved class
    client.post(f"/entries/{entry['id']}/save")
    resp = client.get("/entries")
    assert "saved" in resp.text  # row now carries the saved class
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_routes_entries.py -k "checkboxes or saved_class" -v`
Expected: FAIL — `entry-checkbox` / `select-all` not in the rendered list.

- [ ] **Step 3: Add the toolbar above the table**

In `templates/_entry_list.html`, replace the line `<table class="entry-list">` with the toolbar plus the table opening tag:

```html
<div id="bulk-toolbar" class="bulk-toolbar hidden">
    <span id="bulk-count">0 selected</span>
    <button type="button"
            class="bulk-save-btn"
            hx-post="/entries/save-bulk"
            hx-include=".entry-checkbox, #bulk-context"
            hx-target="#entry-list"
            hx-swap="innerHTML">Save selected</button>
    <a id="bulk-clear" href="#">Clear</a>
    <span id="bulk-context" hidden>
        {% if source_id %}<input type="hidden" name="source_id" value="{{ source_id }}">{% endif %}
        {% if saved %}<input type="hidden" name="saved" value="1">{% endif %}
        <input type="hidden" name="sort" value="{{ sort }}">
    </span>
</div>
<table class="entry-list">
```

- [ ] **Step 4: Add the select-all header cell**

In `templates/_entry_list.html`, replace the header line `<th class="col-save"></th>` with:

```html
<th class="col-select"><input type="checkbox" id="select-all" title="Select all"></th>
<th class="col-save"></th>
```

- [ ] **Step 5: Add the checkbox cell and `saved` row class**

In `templates/_entry_list.html`, replace the row opening tag and save cell. The current markup is:

```html
<tr class="entry-row {% if not entry.read_at %}unread{% endif %}"
    hx-get="/entries/{{ entry.id }}"
    hx-target="#entry-reader"
    hx-push-url="false">
    <td class="col-save" onclick="event.stopPropagation()">{% include "_save_button.html" %}</td>
```

Replace it with:

```html
<tr class="entry-row {% if not entry.read_at %}unread{% endif %}{% if entry.is_saved %} saved{% endif %}"
    hx-get="/entries/{{ entry.id }}"
    hx-target="#entry-reader"
    hx-push-url="false">
    <td class="col-select" onclick="event.stopPropagation()">
        <input type="checkbox" class="entry-checkbox" name="entry_ids"
               value="{{ entry.id }}" data-index="{{ loop.index0 }}">
    </td>
    <td class="col-save" onclick="event.stopPropagation()">{% include "_save_button.html" %}</td>
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_routes_entries.py -v`
Expected: PASS — checkbox/select-all/saved-class tests pass, all earlier tests still pass.

- [ ] **Step 7: Commit**

```bash
git add templates/_entry_list.html tests/test_routes_entries.py
git commit -m "feat: add checkbox column, bulk toolbar, and saved-row class to entry list"
```

---

### Task 3: Selection JavaScript

**Files:**
- Modify: `templates/_entry_list.html`

This task adds client-side selection behavior. It is plain DOM scripting with no unit
test — verified by the manual check in Step 3.

- [ ] **Step 1: Add the inline selection script**

In `templates/_entry_list.html`, add this block immediately before the final `{% endif %}`
(the one that closes the `{% if entries %}` block, after `</table>`):

```html
<script>
(function () {
    const checkboxes = Array.from(document.querySelectorAll('#entry-list .entry-checkbox'));
    if (!checkboxes.length) return;
    const selectAll = document.getElementById('select-all');
    const toolbar = document.getElementById('bulk-toolbar');
    const count = document.getElementById('bulk-count');
    const clearBtn = document.getElementById('bulk-clear');
    let lastIndex = null;

    function updateToolbar() {
        const n = checkboxes.filter(cb => cb.checked).length;
        count.textContent = n + ' selected';
        toolbar.classList.toggle('hidden', n === 0);
        selectAll.checked = n === checkboxes.length;
    }

    checkboxes.forEach((cb, i) => {
        cb.addEventListener('click', (e) => {
            if (e.shiftKey && lastIndex !== null) {
                const lo = Math.min(lastIndex, i);
                const hi = Math.max(lastIndex, i);
                for (let j = lo; j <= hi; j++) checkboxes[j].checked = cb.checked;
            }
            lastIndex = i;
            updateToolbar();
        });
    });

    selectAll.addEventListener('click', () => {
        checkboxes.forEach(cb => { cb.checked = selectAll.checked; });
        lastIndex = null;
        updateToolbar();
    });

    clearBtn.addEventListener('click', () => {
        checkboxes.forEach(cb => { cb.checked = false; });
        selectAll.checked = false;
        lastIndex = null;
        updateToolbar();
    });

    updateToolbar();
})();
</script>
```

- [ ] **Step 2: Run the existing test suite to confirm nothing broke**

Run: `uv run pytest tests/test_routes_entries.py -v`
Expected: PASS — the script is inert markup to the server-side tests; all tests still pass.

- [ ] **Step 3: Manual verification**

Start the app (`uv run uvicorn main:app --reload`), open it, and select a source so the
entry list renders. Verify:
- Clicking a checkbox shows the toolbar with the correct "N selected" count.
- Shift+clicking a second checkbox selects the whole range between them.
- The select-all header checkbox toggles every row.
- "Clear" deselects everything and hides the toolbar.
- "Save selected" saves the checked rows; after the table re-renders, their stars
  are filled, their rows are tinted, and the toolbar is gone.
- Re-sorting or searching clears the selection (the table re-renders fresh).

- [ ] **Step 4: Commit**

```bash
git add templates/_entry_list.html
git commit -m "feat: add client-side episode selection (toggle, shift-range, select-all)"
```

---

### Task 4: Styling — checkbox column, toolbar, saved-row tint

**Files:**
- Modify: `static/style.css`

CSS-only task; no test (per project convention, trivial style changes skip TDD).

- [ ] **Step 1: Add the styles**

In `static/style.css`, add the following at the end of the `/* Entry list */` section
(immediately after the `.empty-state` rule on line 38):

```css
.col-select { width: 28px; text-align: center; }
.col-select input { cursor: pointer; }
.entry-row.saved { background: #fff8e8; }
.entry-row.saved:hover { background: #fdf0d4; }

/* Bulk-action toolbar */
.bulk-toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 14px; border-bottom: 1px solid #eee; background: #f0f4ff; position: sticky; top: 0; z-index: 9; }
.bulk-toolbar.hidden { display: none; }
.bulk-toolbar #bulk-count { font-size: 12px; color: #555; font-weight: 600; }
.bulk-save-btn { padding: 4px 12px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
.bulk-save-btn:hover { background: #0055aa; }
.bulk-toolbar #bulk-clear { background: none; border: none; padding: 0; font-size: 12px; color: #0066cc; cursor: pointer; }
```

- [ ] **Step 2: Manual verification**

Reload the app. Confirm the toolbar appears below the search bar with a light-blue
background when rows are selected, that saved rows show a pale-amber tint, and that the
checkbox column aligns cleanly with the star column.

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "style: add styling for bulk toolbar, checkbox column, and saved rows"
```

---

## Self-Review Notes

- **Spec coverage:** checkbox column (Task 2), Shift+click range (Task 3), select-all (Tasks 2+3), bulk toolbar (Tasks 2+3+4), `POST /entries/save-bulk` (Task 1), saved-row indicator (Tasks 2+4) — all spec components mapped.
- **`_save_one`** is defined once in Task 1 and referenced consistently by both `save_entry_route` and `save_bulk`.
- **No placeholders:** every code and test step contains complete content.
- **Toolbar `hx-include`** uses `.entry-checkbox` (only checked boxes submit `entry_ids`) and `#bulk-context` (contributes `source_id`/`sort`); `source_id` is rendered only when set, so the endpoint's `Optional[int]` never receives an empty string.
