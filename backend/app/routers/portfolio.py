"""Portfolio routes (API_CONTRACT.md §Portfolio), paths relative to ``/api``.

GET  /portfolio
POST /portfolio/trade      serialized by the trade lock (R20)
GET  /portfolio/history    ?limit=1..10000 (default 1000)
"""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_db, get_market_source, get_price_cache, get_trade_lock
from app.errors import BadRequest
from app.market import MarketDataSource, PriceCache
from app.services import execute_trade, get_history, get_portfolio
from app.services.portfolio import DEFAULT_HISTORY_LIMIT, MAX_HISTORY_LIMIT
from app.storage import Database

router = APIRouter(tags=["portfolio"])

Db = Annotated[Database, Depends(get_db)]
Cache = Annotated[PriceCache, Depends(get_price_cache)]
Source = Annotated[MarketDataSource, Depends(get_market_source)]
Lock = Annotated[asyncio.Lock, Depends(get_trade_lock)]


class TradeRequest(BaseModel):
    # Strict JSON types only; values are validated by the service so the
    # contract's exact error strings are produced.
    ticker: str = Field(strict=True)
    quantity: float = Field(strict=True, allow_inf_nan=False)
    side: str = Field(strict=True)


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_HISTORY_LIMIT
    try:
        limit = int(raw)
    except ValueError:
        limit = 0
    if not 1 <= limit <= MAX_HISTORY_LIMIT:
        raise BadRequest(f"limit must be an integer between 1 and {MAX_HISTORY_LIMIT}")
    return limit


@router.get("/portfolio")
async def portfolio(db: Db, cache: Cache) -> dict[str, Any]:
    return get_portfolio(db, cache)


@router.post("/portfolio/trade")
async def trade(
    body: TradeRequest, db: Db, cache: Cache, source: Source, lock: Lock
) -> dict[str, Any]:
    executed = await execute_trade(
        db, cache, source, lock, ticker=body.ticker, quantity=body.quantity, side=body.side
    )
    return {"trade": executed.to_wire(), "portfolio": get_portfolio(db, cache)}


@router.get("/portfolio/history")
async def history(db: Db, limit: str | None = None) -> dict[str, Any]:
    return {"snapshots": get_history(db, parse_limit(limit))}
