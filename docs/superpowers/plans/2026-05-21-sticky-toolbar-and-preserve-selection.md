# Sticky Bulk Toolbar & Preserve Selection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bulk action toolbar visibly sticky in the entry list, and preserve checkbox selection across bulk-action re-renders.

**Architecture:** Two independent, surgical fixes in the entry-list pane. Bug 1 is CSS-only: stack the toolbar below the existing sticky search bar. Bug 2 is server-driven: the bulk endpoints (already receiving `entry_ids`) pass a `selected_ids` set into the template, and the checkbox renders `checked` when its id is in that set.

**Tech Stack:** FastAPI + Jinja2, HTMX, vanilla CSS, pytest with FastAPI `TestClient`.

**Spec:** `docs/superpowers/specs/2026-05-21-sticky-toolbar-and-preserve-selection-design.md`

---

## File Structure

- **Modify** `routes/entries.py` — add `selected_ids` to the template context in `entry_list`, `save_bulk`, `download_bulk`.
- **Modify** `templates/_entry_list.html` — render checkboxes with `checked` when their entry id is in `selected_ids`.
- **Modify** `static/style.css` — bump `.bulk-toolbar` `top` so it stacks under the search bar.
- **Modify** `tests/test_routes_entries.py` — add tests covering pre-checked initial render, bulk-save preservation, and bulk-download preservation.

No new files. No new JS — the existing init script in `_entry_list.html` (lines 74–119) already calls `updateToolbar()` on load, so pre-checked boxes will populate the count and reveal the toolbar automatically.

---

## Task 1: Preserve selection after bulk actions (server-side)

**Files:**
- Modify: `routes/entries.py:28-79`
- Modify: `templates/_entry_list.html:56-57`
- Test: `tests/test_routes_entries.py` (add three new tests near the other `save_bulk` / `download_bulk` tests)

### Test design notes

The HTMX response is the rendered HTML of `_entry_list.html`. To detect "preserved selection," assert that the checkbox row for a given entry id contains `checked` inside its `<input>` tag. The cleanest signal is a substring match: the rendered checkbox looks like

```html
<input type="checkbox" class="entry-checkbox" name="entry_ids"
       value="42" data-index="0" checked>
```

So the substring `value="<id>" data-index="0" checked` (or similar) is fragile to attribute reordering. Use a slightly looser test: that `value="<id>"` and `checked` appear within the same `<input ...>` element. A small helper makes this readable.

- [ ] **Step 1.1: Write the failing test for plain GET — no boxes pre-checked**

Add to `tests/test_routes_entries.py`, after `test_save_bulk_preserves_source_id`:

```python
import re


def _checkbox_is_checked(html: str, entry_id: int) -> bool:
    """True iff the <input> for this entry id includes the `checked` attribute."""
    pattern = re.compile(
        r'<input[^>]*\bvalue="' + str(entry_id) + r'"[^>]*>',
        re.IGNORECASE,
    )
    match = pattern.search(html)
    if not match:
        return False
    return "checked" in match.group(0)


def test_entry_list_get_renders_checkboxes_unchecked(client, source):
    from db.entries import create_entry
    e1 = create_entry(source_id=source["id"], title="Plain A",
                      url="https://example.com/plain-a", description="A")
    resp = client.get("/entries")
    assert resp.status_code == 200
    assert not _checkbox_is_checked(resp.text, e1["id"])
```

- [ ] **Step 1.2: Run the test — expect FAIL**

Run: `uv run pytest tests/test_routes_entries.py::test_entry_list_get_renders_checkboxes_unchecked -v`
Expected: PASS (this is the baseline; current behavior already renders unchecked).

If it fails, stop — the helper has a bug; fix it before continuing.

- [ ] **Step 1.3: Write the failing test for save-bulk preserving selection**

Add immediately below the previous test:

```python
def test_save_bulk_preserves_selection_in_response(client, source):
    from db.entries import create_entry
    e1 = create_entry(source_id=source["id"], title="Sel A",
                      url="https://example.com/sel-a", description="A")
    e2 = create_entry(source_id=source["id"], title="Sel B",
                      url="https://example.com/sel-b", description="B")
    resp = client.post("/entries/save-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert _checkbox_is_checked(resp.text, e1["id"])
    assert _checkbox_is_checked(resp.text, e2["id"])
```

- [ ] **Step 1.4: Write the failing test for download-bulk preserving selection**

Add immediately below:

```python
def test_download_bulk_preserves_selection_in_response(client, source):
    from db.entries import create_entry
    e1 = create_entry(source_id=source["id"], title="Pod A",
                      url="https://example.com/pod-a", description="A",
                      enclosure_url="https://example.com/a.mp3")
    e2 = create_entry(source_id=source["id"], title="Pod B",
                      url="https://example.com/pod-b", description="B",
                      enclosure_url="https://example.com/b.mp3")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert _checkbox_is_checked(resp.text, e1["id"])
    assert _checkbox_is_checked(resp.text, e2["id"])
```

If `create_entry` does not accept `enclosure_url` as a kwarg, fall back to whatever pattern `test_download_bulk_enqueues_eligible_entries` (around `test_routes_entries.py:138`) uses to seed enclosure-bearing entries, and mirror that.

- [ ] **Step 1.5: Run the two new bulk tests — expect FAIL**

Run:

```bash
uv run pytest tests/test_routes_entries.py::test_save_bulk_preserves_selection_in_response \
              tests/test_routes_entries.py::test_download_bulk_preserves_selection_in_response -v
```

Expected: both FAIL — the assertions on `_checkbox_is_checked` will be `False` because the template currently never emits `checked`.

- [ ] **Step 1.6: Update the three handlers in `routes/entries.py` to pass `selected_ids`**

Edit `routes/entries.py`. In `entry_list` (around line 36-38) change the return to:

```python
    return templates.TemplateResponse(
        request, "_entry_list.html",
        {"entries": entries, "source_id": source_id, "saved": saved, "sort": sort,
         "selected_ids": set()},
    )
```

In `save_bulk` (around line 51-55) change the return to:

```python
    entries = list_entries(source_id=source_id, saved_only=saved, sort=sort)
    return templates.TemplateResponse(
        request, "_entry_list.html",
        {"entries": entries, "source_id": source_id, "saved": saved, "sort": sort,
         "selected_ids": set(entry_ids)},
    )
```

In `download_bulk` (around line 75-79) change the return to:

```python
    entries = list_entries(source_id=source_id, saved_only=saved, sort=sort)
    return templates.TemplateResponse(
        request, "_entry_list.html",
        {"entries": entries, "source_id": source_id, "saved": saved, "sort": sort,
         "selected_ids": set(entry_ids)},
    )
```

- [ ] **Step 1.7: Update the checkbox markup in `templates/_entry_list.html`**

Change the checkbox `<input>` at `_entry_list.html:56-57` from:

```jinja
            <input type="checkbox" class="entry-checkbox" name="entry_ids"
                   value="{{ entry.id }}" data-index="{{ loop.index0 }}">
```

to:

```jinja
            <input type="checkbox" class="entry-checkbox" name="entry_ids"
                   value="{{ entry.id }}" data-index="{{ loop.index0 }}"
                   {% if entry.id in selected_ids %}checked{% endif %}>
```

- [ ] **Step 1.8: Run the three new tests — expect PASS**

Run:

```bash
uv run pytest tests/test_routes_entries.py::test_entry_list_get_renders_checkboxes_unchecked \
              tests/test_routes_entries.py::test_save_bulk_preserves_selection_in_response \
              tests/test_routes_entries.py::test_download_bulk_preserves_selection_in_response -v
```

Expected: 3 passed.

- [ ] **Step 1.9: Run the full entry-routes test file as a regression check**

Run: `uv run pytest tests/test_routes_entries.py -v`
Expected: all tests pass. Existing tests rely on `_entry_list.html` rendering; they should be unaffected because `selected_ids` defaults to an empty set in `entry_list` and the template's `{% if entry.id in selected_ids %}` evaluates to false everywhere it isn't pre-populated.

- [ ] **Step 1.10: Commit**

```bash
git add routes/entries.py templates/_entry_list.html tests/test_routes_entries.py
git commit -m "fix: preserve checkbox selection across bulk action re-renders"
```

---

## Task 2: Make the bulk action toolbar visibly sticky

**Files:**
- Modify: `static/style.css:46`

CSS-only, no test. Per the project's no-test-for-trivial-CSS convention.

### Background

`<main id="entry-list">` is the scroll container (`overflow-y: auto`, `style.css:22`). The search bar (`style.css:54`) and the bulk toolbar (`style.css:46`) are both `position: sticky; top: 0` inside it. Search bar's z-index is 10, toolbar's is 9 — the toolbar is sticking at offset 0 but being painted under the search bar.

The search bar's actual rendered height is approximately:
- 10px top padding + 6px input top padding + ~16px line-height + ~2px input border + 6px input bottom padding + 10px bottom padding + 1px border-bottom = ~51px.

Use `top: 50px` as a clean baseline. If a sliver of the underlying list peeks between the two bars when scrolling, bump by 1–2px; if the toolbar visibly overlaps the search input, drop by 1–2px.

- [ ] **Step 2.1: Edit `static/style.css:46`**

Change:

```css
.bulk-toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 14px; border-bottom: 1px solid #eee; background: #f0f4ff; position: sticky; top: 0; z-index: 9; }
```

to:

```css
.bulk-toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 14px; border-bottom: 1px solid #eee; background: #f0f4ff; position: sticky; top: 50px; z-index: 9; }
```

- [ ] **Step 2.2: Manually verify in the running app**

Start (or restart) the dev server, then in a browser:

1. Open the app, pick a source with many episodes (a podcast feed is ideal).
2. Check at least one row's checkbox — confirm the toolbar appears just below the search bar.
3. Scroll the entry list down. Confirm BOTH bars stay pinned: search bar at the top, toolbar immediately below it.
4. Scroll back up. Confirm no visual jump, gap, or overlap between the two bars at rest.
5. Uncheck everything (or click `Clear`). Confirm the toolbar hides cleanly and the search bar still sticks correctly.

If the gap or overlap is more than a hairline, adjust `top` by 1–2 px and reload.

If you cannot run the app interactively, say so explicitly in the task summary rather than claiming the visual was verified.

- [ ] **Step 2.3: Run the full test suite as a sanity check**

Run: `uv run pytest -q`
Expected: all tests pass. (No tests should be touched by a CSS-only change; this is just a safety net.)

- [ ] **Step 2.4: Commit**

```bash
git add static/style.css
git commit -m "fix: stack bulk toolbar below sticky search bar in entry list"
```

---

## Self-review notes

- **Spec coverage:** Bug 1 → Task 2. Bug 2 → Task 1. Out-of-scope items in the spec (cross-reload persistence, toast confirmations, header refactor) are not in the plan, as intended.
- **No placeholders:** Every step has either the exact code change or the exact command + expected output.
- **Type/name consistency:** `selected_ids` is consistently a `set` of `int` in routes; the template uses `entry.id in selected_ids`, which works for sets of ints. The helper function is named `_checkbox_is_checked` in all three new tests.
- **Edge cases addressed:** Empty-selection POST → `set()` → no checkboxes rendered checked (existing `test_save_bulk_empty_selection` continues to pass). Plain GET → `set()` → no regression in existing tests. Saved-only filter after save → preserved IDs remain in the list because saving never removes them. Download → list is unfiltered, so preserved IDs remain.
