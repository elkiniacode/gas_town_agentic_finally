"""Ticker normalization shared by every endpoint and the chat actions (API_CONTRACT.md)."""

import re

from app.errors import BadRequest

TICKER_RE = re.compile(r"[A-Z]{1,5}")
INVALID_TICKER = "Invalid ticker: must be 1-5 letters A-Z"


def normalize_ticker(raw: str) -> str:
    """Trim and uppercase, then require ``^[A-Z]{1,5}$``; raises :class:`BadRequest` otherwise."""
    ticker = raw.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise BadRequest(INVALID_TICKER)
    return ticker
