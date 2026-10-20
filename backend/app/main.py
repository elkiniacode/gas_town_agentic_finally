"""FastAPI application: lifespan, routers, error handlers and static frontend.

Run from ``backend/``: ``uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1``.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app.config import DEV_CORS_ORIGINS, Settings, load_settings
from app.errors import register_error_handlers
from app.routers import chat, health, market, portfolio, watchlist
from app.storage import init_database

logger = logging.getLogger(__name__)


class FrontendStaticFiles(StaticFiles):
    """Static export mounted at ``/`` that never answers for ``/api/*``.

    With ``html=True`` StaticFiles serves ``404.html`` for unknown paths; an
    unknown API route must get JSON ``{"detail": "Not Found"}`` instead.
    """

    async def get_response(self, path: str, scope: Scope):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # PLAN.md §7 startup sequence. The DB is initialized here, once, before
        # any background task starts (S2) — there is no lazy init path.
        app.state.settings = settings
        app.state.db = init_database(settings.db_path)
        app.state.trade_lock = asyncio.Lock()
        logger.info("Database ready at %s", settings.db_path)

        # Market data (fin-k90.3): build the tracked set (watchlist ∪ positions),
        # seed held tickers from their last trade price (R14), start the source.
        # Portfolio snapshots: start the 30 s snapshot task after the source.
        try:
            yield
        finally:
            # Stop background tasks here, in reverse start order.
            pass

    app = FastAPI(title="FinAlly", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)

    if settings.dev_mode:
        # R32: local `next dev` on :3000 only. Never enabled in the image.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(DEV_CORS_ORIGINS),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    for module in (health, market, portfolio, watchlist, chat):
        app.include_router(module.router, prefix="/api")

    # Must stay last: a mount at "/" matches every path (PLAN.md §8).
    if settings.static_dir.is_dir():
        app.mount("/", FrontendStaticFiles(directory=settings.static_dir, html=True), name="static")

    return app


app = create_app()
