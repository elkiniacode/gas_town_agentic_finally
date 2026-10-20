"""Default seed data (PLAN.md §7): one user, ten watchlist tickers, one snapshot."""

import sqlite3

from app.storage.ids import new_id
from app.timeutil import utc_now_iso

DEFAULT_USER_ID = "default"
STARTING_CASH = 10000.0
DEFAULT_TICKERS = ("AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX")


def seed_defaults(conn: sqlite3.Connection) -> bool:
    """Seed a fresh database. Returns True if seeding happened.

    Keyed on the default user row: if it already exists the database has been
    seeded before and nothing is touched, so a user who removed default tickers
    doesn't get them back on restart. Must run inside a transaction.

    The ten watchlist rows share one ``added_at``; they are inserted in seed
    order, so ``ORDER BY added_at, rowid`` returns them in that order.
    """
    exists = conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)).fetchone()
    if exists:
        return False

    now = utc_now_iso()
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, STARTING_CASH, now),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(new_id(), DEFAULT_USER_ID, ticker, now) for ticker in DEFAULT_TICKERS],
    )
    # R21: the P&L chart has a starting point from the very first page load.
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
        " VALUES (?, ?, ?, ?)",
        (new_id(), DEFAULT_USER_ID, STARTING_CASH, now),
    )
    return True
