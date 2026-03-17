from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db.sources import (
    create_source,
    delete_source,
    list_sources_with_unread_count,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _sidebar_response(request: Request) -> HTMLResponse:
    sources = list_sources_with_unread_count()
    return templates.TemplateResponse(
        "_sidebar.html", {"request": request, "sources": sources}
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    sources = list_sources_with_unread_count()
    return templates.TemplateResponse("base.html", {"request": request, "sources": sources})


@router.get("/sources/add-form", response_class=HTMLResponse)
def add_source_form(request: Request):
    return templates.TemplateResponse("_add_source_form.html", {"request": request})


@router.post("/sources", response_class=HTMLResponse)
def add_source(
    request: Request,
    feed_url: str = Form(...),
    name: str = Form(...),
    type: str = Form(...),
    archive_mode: str = Form(...),
):
    import re
    folder_name = re.sub(r"[^\w]+", "-", name.lower()).strip("-")
    create_source(
        name=name,
        type=type,
        feed_url=feed_url,
        archive_mode=archive_mode,
        folder_name=folder_name,
    )
    return _sidebar_response(request)


@router.delete("/sources/{source_id}", response_class=HTMLResponse)
def remove_source(request: Request, source_id: int):
    delete_source(source_id)
    return _sidebar_response(request)
