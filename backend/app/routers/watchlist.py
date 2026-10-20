"""Watchlist routes (API_CONTRACT.md §Watchlist), paths relative to ``/api``.

GET    /watchlist
POST   /watchlist             idempotent: already present → 200, unchanged list
DELETE /watchlist/{ticker}    idempotent: absent → 200, unchanged list
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_db, get_market_source, get_price_cache
from app.market import MarketDataSource, PriceCache
from app.services import add_to_watchlist, get_watchlist, remove_from_watchlist
from app.storage import Database

router = APIRouter(tags=["watchlist"])

Db = Annotated[Database, Depends(get_db)]
Cache = Annotated[PriceCache, Depends(get_price_cache)]
Source = Annotated[MarketDataSource, Depends(get_market_source)]


class WatchlistAdd(BaseModel):
    ticker: str = Field(strict=True)


# Handlers are async so price cache reads stay on the event loop with the source.
@router.get("/watchlist")
async def list_watchlist(db: Db, cache: Cache) -> dict[str, Any]:
    return {"watchlist": get_watchlist(db, cache)}


@router.post("/watchlist")
async def add_watchlist_ticker(
    body: WatchlistAdd, db: Db, cache: Cache, source: Source
) -> dict[str, Any]:
    add_to_watchlist(db, source, body.ticker)
    return {"watchlist": get_watchlist(db, cache)}


@router.delete("/watchlist/{ticker}")
async def remove_watchlist_ticker(
    ticker: str, db: Db, cache: Cache, source: Source
) -> dict[str, Any]:
    remove_from_watchlist(db, source, ticker)
    return {"watchlist": get_watchlist(db, cache)}
