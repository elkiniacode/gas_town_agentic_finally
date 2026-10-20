"""Portfolio valuation, snapshots and history (API_CONTRACT.md §Portfolio, §Metric formulas).

Valuation uses the cached price, falling back to ``avg_cost`` when a ticker has
none (R17). Values are computed at full precision and rounded only on output.
"""

import asyncio
import contextlib
import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from app.market import PriceCache
from app.services.rounding import pct, round2, round4
from app.storage import DEFAULT_USER_ID, STARTING_CASH, Database, new_id
from app.timeutil import utc_now_iso

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30.0
DEFAULT_HISTORY_LIMIT = 1000
MAX_HISTORY_LIMIT = 10000


@dataclass(frozen=True)
class Holding:
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float  # cached price, or avg_cost when none

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_cost) * self.quantity

    def to_wire(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "quantity": round4(self.quantity),
            "avg_cost": round2(self.avg_cost),
            "current_price": round2(self.current_price),
            "market_value": round2(self.market_value),
            "unrealized_pnl": round2(self.unrealized_pnl),
            "pnl_pct": pct(self.current_price - self.avg_cost, self.avg_cost),
        }


@dataclass(frozen=True)
class Portfolio:
    cash_balance: float
    holdings: list[Holding]  # ordered by ticker

    @property
    def positions_value(self) -> float:
        return sum(h.market_value for h in self.holdings)

    @property
    def total_value(self) -> float:
        return self.cash_balance + self.positions_value

    def to_wire(self) -> dict[str, Any]:
        total_pnl = self.total_value - STARTING_CASH
        return {
            "cash_balance": round2(self.cash_balance),
            "positions": [h.to_wire() for h in self.holdings],
            "positions_value": round2(self.positions_value),
            "total_value": round2(self.total_value),
            "total_pnl": round2(total_pnl),
            "total_pnl_pct": pct(total_pnl, STARTING_CASH),
        }


def read_cash(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> float:
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise LookupError(f"No user profile for {user_id!r}")
    return row["cash_balance"]


def load_portfolio(db: Database, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> Portfolio:
    """Cash and positions valued at current cached prices."""
    with db.connect() as conn:
        cash = read_cash(conn, user_id)
        rows = conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
            (user_id,),
        ).fetchall()
    holdings = []
    for row in rows:
        entry = cache.get(row["ticker"])
        holdings.append(
            Holding(
                ticker=row["ticker"],
                quantity=row["quantity"],
                avg_cost=row["avg_cost"],
                current_price=row["avg_cost"] if entry is None else entry.price,
            )
        )
    return Portfolio(cash_balance=cash, holdings=holdings)


def get_portfolio(db: Database, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> dict:
    """The ``GET /api/portfolio`` body."""
    return load_portfolio(db, cache, user_id).to_wire()


def record_snapshot(db: Database, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> float:
    """Store the current total value in ``portfolio_snapshots``; returns it (2 dp)."""
    total_value = round2(load_portfolio(db, cache, user_id).total_value)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
            " VALUES (?, ?, ?, ?)",
            (new_id(), user_id, total_value, utc_now_iso()),
        )
    return total_value


def get_history(
    db: Database, limit: int = DEFAULT_HISTORY_LIMIT, user_id: str = DEFAULT_USER_ID
) -> list[dict[str, Any]]:
    """The most recent ``limit`` snapshots, in ascending ``recorded_at`` order."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT total_value, recorded_at FROM (
                SELECT total_value, recorded_at, rowid AS rid FROM portfolio_snapshots
                 WHERE user_id = ?
                 ORDER BY recorded_at DESC, rowid DESC
                 LIMIT ?
            ) ORDER BY recorded_at, rid
            """,
            (user_id, limit),
        ).fetchall()
    return [
        {"total_value": round2(row["total_value"]), "recorded_at": row["recorded_at"]}
        for row in rows
    ]


async def run_snapshot_loop(
    db: Database,
    cache: PriceCache,
    lock: asyncio.Lock,
    interval: float = SNAPSHOT_INTERVAL_SECONDS,
) -> None:
    """Record a snapshot every ``interval`` seconds until cancelled.

    Takes the trade lock so a snapshot never lands between a trade's commit and
    its own post-trade snapshot. A failed snapshot is logged and skipped.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            async with lock:
                record_snapshot(db, cache)
        except Exception:
            logger.exception("Portfolio snapshot failed; retrying next interval")


async def stop_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
