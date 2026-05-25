from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.init_db import init_db

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Post Writer Bot API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
