from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db.schema import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Laeser", lifespan=lifespan)

# static/ is created in Task 1 (static/.gitkeep) — always present
app.mount("/static", StaticFiles(directory="static"), name="static")

from routes.sources import router as sources_router
app.include_router(sources_router)
