"""Which tickers are priced (R9): the watchlist ∪ open positions.

Request handlers call :func:`sync_ticker` after any change to the watchlist or
positions (after the DB write has committed); it adds or removes the ticker from
the source so the priced set always matches the database.
"""

from app.market.source import MarketDataSource
from app.storage import DEFAULT_USER_ID, Database


def load_tracked_tickers(db: Database, user_id: str = DEFAULT_USER_ID) -> list[str]:
    """Watchlist tickers in display order, then any held tickers not on the watchlist."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (user_id,),
        ).fetchall()
        held = conn.execute(
            "SELECT ticker FROM positions WHERE user_id = ? ORDER BY ticker", (user_id,)
        ).fetchall()
    tickers = [row["ticker"] for row in rows]
    seen = set(tickers)
    tickers.extend(row["ticker"] for row in held if row["ticker"] not in seen)
    return tickers


def load_restart_prices(db: Database, user_id: str = DEFAULT_USER_ID) -> dict[str, float]:
    """Most recent trade price for each held ticker (R14 restart continuity)."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT p.ticker,
                   (SELECT t.price FROM trades t
                     WHERE t.user_id = p.user_id AND t.ticker = p.ticker
                     ORDER BY t.executed_at DESC, t.rowid DESC LIMIT 1) AS price
              FROM positions p
             WHERE p.user_id = ?
            """,
            (user_id,),
        ).fetchall()
    return {row["ticker"]: row["price"] for row in rows if row["price"] is not None}


def is_tracked(db: Database, ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """True if ``ticker`` is on the watchlist or has an open position."""
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?)
                OR EXISTS (SELECT 1 FROM positions WHERE user_id = ? AND ticker = ?)
            """,
            (user_id, ticker, user_id, ticker),
        ).fetchone()
    return bool(row[0])


def sync_ticker(
    db: Database, source: MarketDataSource, ticker: str, user_id: str = DEFAULT_USER_ID
) -> bool:
    """Make the source price ``ticker`` iff it is on the watchlist or held. Returns that state.

    Call after committing a watchlist add/remove or a trade. Removing a held
    ticker from the watchlist therefore keeps it priced, and a sell that closes
    a position in an unwatched ticker drops it from the source and cache.
    """
    tracked = is_tracked(db, ticker, user_id)
    if tracked:
        source.add_ticker(ticker)
    else:
        source.remove_ticker(ticker)
    return tracked
