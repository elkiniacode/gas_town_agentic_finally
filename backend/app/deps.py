"""FastAPI dependencies for objects created in the lifespan and kept on ``app.state``."""

import asyncio

from fastapi import Request

from app.config import Settings
from app.storage import Database


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_trade_lock(request: Request) -> asyncio.Lock:
    """Process-wide lock serializing every trade, manual or chat-initiated (R20)."""
    return request.app.state.trade_lock
