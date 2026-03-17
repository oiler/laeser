from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db.schema import init_db
from feeds.scheduler import setup_scheduler, shutdown_scheduler
from routes.sources import router as sources_router
from routes.entries import router as entries_router
from routes.search import router as search_router
from routes.audio import router as audio_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    setup_scheduler(app)
    yield
    shutdown_scheduler()


app = FastAPI(title="Laeser", lifespan=lifespan)

Path("static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(sources_router)
app.include_router(entries_router)
app.include_router(search_router)
app.include_router(audio_router)
