import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from db.sources import (
    create_source,
    delete_source,
    list_sources_with_unread_count,
)
from feeds.scheduler import refresh_source as do_refresh

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _sidebar_response(request: Request) -> HTMLResponse:
    sources = list_sources_with_unread_count()
    return templates.TemplateResponse(
        request, "_sidebar.html", {"sources": sources}
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    sources = list_sources_with_unread_count()
    return templates.TemplateResponse(request, "base.html", {"sources": sources})


@router.get("/sources/add-form", response_class=HTMLResponse)
def add_source_form(request: Request):
    return templates.TemplateResponse(request, "_add_source_form.html", {})


@router.post("/sources", response_class=HTMLResponse)
async def add_source(
    request: Request,
    feed_url: str = Form(...),
    name: str = Form(...),
    type: str = Form(...),
    archive_mode: str = Form(...),
):
    folder_name = re.sub(r"[^\w]+", "-", name.lower()).strip("-")
    source = create_source(
        name=name,
        type=type,
        feed_url=feed_url,
        archive_mode=archive_mode,
        folder_name=folder_name,
    )
    if type != "manual" and feed_url:
        await run_in_threadpool(do_refresh, source["id"], source)
    return _sidebar_response(request)


@router.delete("/sources/{source_id}", response_class=HTMLResponse)
def remove_source(request: Request, source_id: int):
    delete_source(source_id)
    return _sidebar_response(request)


@router.post("/sources/{source_id}/refresh", response_class=HTMLResponse)
async def refresh_source_route(request: Request, source_id: int):
    # run_in_threadpool offloads the sync blocking refresh_source() to a thread,
    # keeping the FastAPI event loop free during the feed fetch.
    from db.sources import get_source
    source = get_source(source_id)
    if source:
        await run_in_threadpool(do_refresh, source_id, source)
    return _sidebar_response(request)
