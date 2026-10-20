"""Trade execution (API_CONTRACT.md §POST /api/portfolio/trade, PLAN.md §8 R19, R20).

Every trade, manual or chat-initiated, goes through :func:`execute_trade`: it
validates in contract order, then runs in one DB transaction under the
process-wide trade lock, re-syncs the priced set and records a snapshot.
"""

import asyncio
import math
from dataclasses import dataclass
from typing import Any

from app.errors import BadRequest
from app.market import MarketDataSource, PriceCache, sync_ticker
from app.services.portfolio import read_cash, record_snapshot
from app.services.rounding import format_quantity, round2, round4
from app.services.tickers import normalize_ticker
from app.storage import DEFAULT_USER_ID, Database, new_id
from app.timeutil import utc_now_iso

SIDES = ("buy", "sell")
DUST_QUANTITY = 1e-6


class TradeError(BadRequest):
    """A rejected trade. ``price`` is the cached price at rejection time, if there was one.

    The chat bead reports it as the failed trade's ``price`` (API_CONTRACT.md §Chat).
    """

    def __init__(self, detail: str, price: float | None = None) -> None:
        super().__init__(detail)
        self.price = price


@dataclass(frozen=True)
class ExecutedTrade:
    id: str
    ticker: str
    side: str
    quantity: float  # 4 dp
    price: float  # fill price: the cached price at execution
    executed_at: str

    @property
    def total(self) -> float:
        return round2(self.quantity * self.price)

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": round4(self.quantity),
            "price": round2(self.price),
            "total": self.total,
            "executed_at": self.executed_at,
        }


def normalize_side(raw: str) -> str:
    side = raw.strip().lower()
    if side not in SIDES:
        raise TradeError("Side must be 'buy' or 'sell'")
    return side


def normalize_quantity(raw: float) -> float:
    """Round to 4 dp; must then be > 0 (and finite)."""
    if not math.isfinite(raw) or round4(raw) <= 0:
        raise TradeError("Quantity must be greater than 0")
    return round4(raw)


async def execute_trade(
    db: Database,
    cache: PriceCache,
    source: MarketDataSource,
    lock: asyncio.Lock,
    ticker: str,
    quantity: float,
    side: str,
    user_id: str = DEFAULT_USER_ID,
) -> ExecutedTrade:
    """Validate and execute a market order at the cached price.

    Raises :class:`TradeError` (a ``BadRequest``) with the contract's exact
    ``detail`` on the first failing rule; its ``price`` is the cached price
    whenever the ticker is valid and priced. Callers needing the normalized
    ticker/side/quantity of a failed trade can reuse :func:`normalize_ticker`,
    :func:`normalize_side` and :func:`normalize_quantity`.
    """
    try:
        ticker = normalize_ticker(ticker)
    except BadRequest as exc:
        raise TradeError(exc.detail) from None
    try:
        side = normalize_side(side)
        quantity = normalize_quantity(quantity)
    except TradeError as exc:
        entry = cache.get(ticker)
        exc.price = None if entry is None else entry.price
        raise

    async with lock:
        entry = cache.get(ticker)
        if entry is None:
            raise TradeError(f"No price available for {ticker}")
        price = entry.price
        cost = round2(quantity * price)
        trade = ExecutedTrade(
            id=new_id(),
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
            executed_at=utc_now_iso(),
        )

        with db.transaction() as conn:
            cash = read_cash(conn, user_id)
            position = conn.execute(
                "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            ).fetchone()
            held = position["quantity"] if position else 0.0

            if side == "buy":
                if cost > cash:
                    raise TradeError(
                        f"Insufficient cash: need ${cost:.2f}, have ${cash:.2f}", price
                    )
                new_cash = round2(cash - cost)
                new_qty = round4(held + quantity)
                old_cost = held * position["avg_cost"] if position else 0.0
                avg_cost = (old_cost + quantity * price) / new_qty
            else:
                if quantity > held:
                    raise TradeError(
                        f"Insufficient shares: requested {format_quantity(quantity)},"
                        f" held {format_quantity(held)}",
                        price,
                    )
                new_cash = round2(cash + cost)
                new_qty = round4(held - quantity)
                avg_cost = position["avg_cost"]

            conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (new_cash, user_id)
            )
            if new_qty < DUST_QUANTITY:
                conn.execute(
                    "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, ticker) DO UPDATE SET
                        quantity = excluded.quantity,
                        avg_cost = excluded.avg_cost,
                        updated_at = excluded.updated_at
                    """,
                    (new_id(), user_id, ticker, new_qty, avg_cost, trade.executed_at),
                )
            conn.execute(
                "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (trade.id, user_id, ticker, side, quantity, price, trade.executed_at),
            )

        # A sell that closes an unwatched position stops pricing it (R9).
        sync_ticker(db, source, ticker, user_id)
        record_snapshot(db, cache, user_id)
    return trade
