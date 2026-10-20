"""Chat routes (API_CONTRACT.md §Chat), paths relative to ``/api``.

POST /chat            one LLM call; actions executed and stored (R22–R27)
GET  /chat/history    ?limit=1..100 (default 20), ascending
"""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings
from app.deps import get_db, get_market_source, get_price_cache, get_settings, get_trade_lock
from app.errors import BadRequest
from app.market import MarketDataSource, PriceCache
from app.services.chat import get_chat_history, handle_chat
from app.storage import Database

router = APIRouter(tags=["chat"])

Db = Annotated[Database, Depends(get_db)]
Cache = Annotated[PriceCache, Depends(get_price_cache)]
Source = Annotated[MarketDataSource, Depends(get_market_source)]
Lock = Annotated[asyncio.Lock, Depends(get_trade_lock)]
Config = Annotated[Settings, Depends(get_settings)]

DEFAULT_CHAT_HISTORY_LIMIT = 20
MAX_CHAT_HISTORY_LIMIT = 100


class ChatRequest(BaseModel):
    message: str = Field(strict=True)


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_CHAT_HISTORY_LIMIT
    try:
        limit = int(raw)
    except ValueError:
        limit = 0
    if not 1 <= limit <= MAX_CHAT_HISTORY_LIMIT:
        raise BadRequest(f"limit must be an integer between 1 and {MAX_CHAT_HISTORY_LIMIT}")
    return limit


@router.post("/chat")
async def chat(
    body: ChatRequest, settings: Config, db: Db, cache: Cache, source: Source, lock: Lock
) -> dict[str, Any]:
    return await handle_chat(body.message, settings, db, cache, source, lock)


@router.get("/chat/history")
async def chat_history(db: Db, limit: str | None = None) -> dict[str, Any]:
    return {"messages": get_chat_history(db, parse_limit(limit))}
