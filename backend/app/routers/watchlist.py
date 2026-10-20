"""Watchlist routes — implemented by the watchlist bead.

Endpoints (API_CONTRACT.md §Watchlist), paths relative to ``/api``:
    GET    /watchlist          ORDER BY added_at, rowid (seed rows share added_at)
    POST   /watchlist
    DELETE /watchlist/{ticker}
"""

from fastapi import APIRouter

router = APIRouter(tags=["watchlist"])
