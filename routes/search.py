from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db.entries import list_entries, search_entries

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/search", response_class=HTMLResponse)
def search(
    request: Request,
    q: str = "",
    source_id: Optional[int] = None,
):
    if not q.strip():
        entries = list_entries(source_id=source_id)
    else:
        source_ids = [source_id] if source_id else None
        entries = search_entries(query=q.strip(), source_ids=source_ids)

    return templates.TemplateResponse(
        request, "_search_results.html", {"entries": entries, "query": q, "source_id": source_id}
    )
