from typing import Optional

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
from storage import write_entry_file

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/entries", response_class=HTMLResponse)
def entry_list(
    request: Request,
    source_id: Optional[int] = None,
    saved: bool = False,
):
    entries = list_entries(source_id=source_id, saved_only=saved)
    return templates.TemplateResponse(
        request, "_entry_list.html", {"entries": entries, "source_id": source_id}
    )
