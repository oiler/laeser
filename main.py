from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db.schema import init_db
from routes.sources import router as sources_router
from routes.entries import router as entries_router
from routes.search import router as search_router
from routes.audio import router as audio_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Laeser", lifespan=lifespan)

# static/ is created in Task 1 (static/.gitkeep) — always present
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(sources_router)
app.include_router(entries_router)
app.include_router(search_router)
app.include_router(audio_router)
