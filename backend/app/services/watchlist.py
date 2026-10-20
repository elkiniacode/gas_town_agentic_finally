"""Watchlist service (API_CONTRACT.md §Watchlist), used by the REST routes and chat actions.

Adds and removes are idempotent. After every committed change the ticker's
priced state is re-synced (R9): an added ticker is priced immediately (R12); a
removed ticker that is still held keeps streaming.
"""

from typing import Any

from app.market import MarketDataSource, PriceCache, sync_ticker
from app.services.rounding import pct, round2
from app.services.tickers import normalize_ticker
from app.storage import DEFAULT_USER_ID, Database, new_id
from app.timeutil import utc_now_iso


def get_watchlist(
    db: Database, cache: PriceCache, user_id: str = DEFAULT_USER_ID
) -> list[dict[str, Any]]:
    """Watchlist items ordered by ``added_at`` (seed rows share it, so rowid breaks ties)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (user_id,),
        ).fetchall()
    items = []
    for row in rows:
        entry = cache.get(row["ticker"])
        if entry is None:
            prices: dict[str, float | None] = dict.fromkeys(
                ("price", "previous_price", "open_price", "change_pct")
            )
        else:
            prices = {
                "price": round2(entry.price),
                "previous_price": round2(entry.previous_price),
                "open_price": round2(entry.open_price),
                "change_pct": pct(entry.price - entry.open_price, entry.open_price),
            }
        items.append({"ticker": row["ticker"], **prices, "added_at": row["added_at"]})
    return items


def add_to_watchlist(
    db: Database, source: MarketDataSource, raw_ticker: str, user_id: str = DEFAULT_USER_ID
) -> str:
    """Add a ticker (no-op if present) and start pricing it. Returns the normalized ticker.

    Raises :class:`app.errors.BadRequest` for an invalid ticker.
    """
    ticker = normalize_ticker(raw_ticker)
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (new_id(), user_id, ticker, utc_now_iso()),
        )
    sync_ticker(db, source, ticker, user_id)
    return ticker


def remove_from_watchlist(
    db: Database, source: MarketDataSource, raw_ticker: str, user_id: str = DEFAULT_USER_ID
) -> str:
    """Remove a ticker (no-op if absent); it stays priced while held. Returns the normalized ticker.

    Raises :class:`app.errors.BadRequest` for an invalid ticker.
    """
    ticker = normalize_ticker(raw_ticker)
    with db.transaction() as conn:
        conn.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    sync_ticker(db, source, ticker, user_id)
    return ticker
