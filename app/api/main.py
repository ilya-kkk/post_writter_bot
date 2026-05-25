from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="Post Writer Bot API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
