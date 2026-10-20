"""FastAPI dependencies for objects created in the lifespan and kept on ``app.state``."""

import asyncio

from fastapi import Request

from app.config import Settings
from app.market import MarketDataSource, PriceCache
from app.storage import Database


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_trade_lock(request: Request) -> asyncio.Lock:
    """Process-wide lock serializing every trade, manual or chat-initiated (R20)."""
    return request.app.state.trade_lock


def get_price_cache(request: Request) -> PriceCache:
    return request.app.state.price_cache


def get_market_source(request: Request) -> MarketDataSource:
    """The active source; pass it to ``app.market.sync_ticker`` after watchlist/trade writes."""
    return request.app.state.market_source
