"""Market data routes (API_CONTRACT.md §Market data), paths relative to ``/api``.

GET /stream/prices   SSE, one batched event per tick
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.deps import get_price_cache
from app.market import PriceCache
from app.market.simulator import TICK_SECONDS

router = APIRouter(tags=["market"])

RETRY_MS = 2000
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def price_event(cache: PriceCache) -> str:
    """One SSE ``data:`` event carrying every priced ticker (``{}`` when none)."""
    payload = {ticker: entry.to_wire() for ticker, entry in cache.get_all().items()}
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def price_events(
    cache: PriceCache, request: Request | None = None, interval: float = TICK_SECONDS
) -> AsyncIterator[str]:
    """The first event goes out immediately with ``retry:``; then one per tick.

    Sends the cache on a fixed cadence regardless of source, so a slow-polling
    source (Massive) just repeats unchanged prices — acceptable per PLAN.md §6.
    """
    yield f"retry: {RETRY_MS}\n" + price_event(cache)
    while True:
        await asyncio.sleep(interval)
        if request is not None and await request.is_disconnected():
            return
        yield price_event(cache)


@router.get("/stream/prices")
async def stream_prices(
    request: Request, cache: Annotated[PriceCache, Depends(get_price_cache)]
) -> StreamingResponse:
    return StreamingResponse(
        price_events(cache, request), media_type="text/event-stream", headers=SSE_HEADERS
    )
