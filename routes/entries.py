from typing import Optional

import nh3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# NOTE: Imports below include functions used in Tasks 15 and 16 (reader route, save/tag
# routes). They are pre-staged here so this file does not need re-editing each task.
# Linters may flag some as unused until those steps are complete — this is expected.
from db.entries import (
    create_entry,
    get_entry,
    list_entries,
    mark_read,
    save_entry,
    search_entries,
    unsave_entry,
)
from db.tags import add_tag_to_entry, create_tag, get_entry_tags, remove_tag_from_entry
from feeds.download_queue import enqueue
from storage import write_entry_file

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/entries", response_class=HTMLResponse)
def entry_list(
    request: Request,
    source_id: Optional[int] = None,
    saved: bool = False,
    sort: str = "desc",
):
    entries = list_entries(source_id=source_id, saved_only=saved, sort=sort)
    return templates.TemplateResponse(
        request, "_entry_list.html",
        {"entries": entries, "source_id": source_id, "saved": saved, "sort": sort,
         "selected_ids": set()},
    )


@router.post("/entries/save-bulk", response_class=HTMLResponse)
def save_bulk(
    request: Request,
    entry_ids: list[int] = Form(default=[]),
    source_id: Optional[int] = Form(None),
    saved: bool = Form(False),
    sort: str = Form("desc"),
):
    for entry_id in entry_ids:
        _save_one(entry_id)
    entries = list_entries(source_id=source_id, saved_only=saved, sort=sort)
    return templates.TemplateResponse(
        request, "_entry_list.html",
        {"entries": entries, "source_id": source_id, "saved": saved, "sort": sort,
         "selected_ids": set(entry_ids)},
    )


@router.post("/entries/download-bulk", response_class=HTMLResponse)
def download_bulk(
    request: Request,
    entry_ids: list[int] = Form(default=[]),
    source_id: Optional[int] = Form(None),
    saved: bool = Form(False),
    sort: str = Form("desc"),
):
    for entry_id in entry_ids:
        entry = get_entry(entry_id)
        if (
            entry
            and entry.get("enclosure_url")
            and not entry.get("audio_path")
            and entry["audio_status"] not in ("queued", "downloading")
        ):
            enqueue(entry_id)
    entries = list_entries(source_id=source_id, saved_only=saved, sort=sort)
    return templates.TemplateResponse(
        request, "_entry_list.html",
        {"entries": entries, "source_id": source_id, "saved": saved, "sort": sort,
         "selected_ids": set(entry_ids)},
    )


@router.get("/entries/{entry_id}", response_class=HTMLResponse)
def entry_reader(request: Request, entry_id: int):
    entry = get_entry(entry_id)
    if not entry:
        return HTMLResponse("Entry not found", status_code=404)
    mark_read(entry_id)
    tags = get_entry_tags(entry_id)
    safe_description = nh3.clean(entry["description"] or "") or None
    return templates.TemplateResponse(
        request, "_entry_reader.html", {"entry": entry, "tags": tags, "description": safe_description}
    )


def _tags_response(request: Request, entry_id: int) -> HTMLResponse:
    entry = get_entry(entry_id)
    tags = get_entry_tags(entry_id)
    return templates.TemplateResponse(
        request, "_entry_tags.html", {"entry": entry, "tags": tags}
    )


def _save_button_response(request: Request, entry_id: int) -> HTMLResponse:
    entry = get_entry(entry_id)
    return templates.TemplateResponse(
        request, "_save_button.html", {"entry": entry}
    )


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


@router.post("/entries/{entry_id}/save", response_class=HTMLResponse)
def save_entry_route(request: Request, entry_id: int):
    _save_one(entry_id)
    return _save_button_response(request, entry_id)


@router.post("/entries/{entry_id}/unsave", response_class=HTMLResponse)
def unsave_entry_route(request: Request, entry_id: int):
    unsave_entry(entry_id)
    return _save_button_response(request, entry_id)


@router.post("/entries/{entry_id}/tags", response_class=HTMLResponse)
def add_tag(request: Request, entry_id: int, tag_name: str = Form(...)):
    tag = create_tag(tag_name.strip().lower())
    add_tag_to_entry(entry_id, tag["id"])
    return _tags_response(request, entry_id)


@router.delete("/entries/{entry_id}/tags/{tag_id}", response_class=HTMLResponse)
def remove_tag(request: Request, entry_id: int, tag_id: int):
    remove_tag_from_entry(entry_id, tag_id)
    return _tags_response(request, entry_id)
