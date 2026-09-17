"""FastAPI app."""

from pathlib import Path

import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from dockhand import __version__
from dockhand.config import get_settings
from dockhand.db.engine import check_db
from dockhand.web.pages import router as pages_router

STATIC_DIR = Path(__file__).resolve().parent / "static"


def check_redis() -> bool:
    try:
        client = redis.from_url(
            get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        return bool(client.ping())
    except Exception:
        return False


def create_app() -> FastAPI:
    app = FastAPI(title="Dockhand", version=__version__)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(pages_router)

    @app.get("/health")
    def health():
        redis_ok = check_redis()
        db_ok = check_db()
        body = {"ok": redis_ok and db_ok, "redis": redis_ok, "db": db_ok, "version": __version__}
        return JSONResponse(body, status_code=200 if body["ok"] else 503)

    return app


app = create_app()
