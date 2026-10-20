"""Shared in-memory price cache (PLAN.md §6, R10, R11).

Written only by the active market data source; read by the SSE stream, trade
execution, portfolio valuation, snapshots and the LLM context. Everything runs
on the single asyncio event loop, so plain dict access needs no locking.
"""

from dataclasses import dataclass
from datetime import datetime

from app.timeutil import to_iso, utc_now


@dataclass(frozen=True)
class PriceEntry:
    price: float
    previous_price: float
    open_price: float  # reference for daily change % (R11)
    timestamp: datetime  # UTC, when ``price`` was set

    def to_wire(self) -> dict[str, float | str]:
        """The per-ticker object of the SSE payload (API_CONTRACT.md §SSE)."""
        return {
            "price": round(self.price, 2),
            "previous_price": round(self.previous_price, 2),
            "open_price": round(self.open_price, 2),
            "timestamp": to_iso(self.timestamp),
        }


class PriceCache:
    def __init__(self) -> None:
        self._entries: dict[str, PriceEntry] = {}

    def get(self, ticker: str) -> PriceEntry | None:
        return self._entries.get(ticker)

    def get_all(self) -> dict[str, PriceEntry]:
        """A snapshot copy; safe to iterate while the source keeps writing."""
        return dict(self._entries)

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._entries

    def update(
        self,
        ticker: str,
        price: float,
        *,
        open_price: float | None = None,
        timestamp: datetime | None = None,
    ) -> PriceEntry:
        """Record a new price. Used only by the active source.

        On a ticker's first write ``previous_price = price`` and ``open_price``
        defaults to ``price``. Later writes keep the existing ``open_price``
        unless one is passed (Massive supplies the previous close).
        """
        timestamp = timestamp or utc_now()
        current = self._entries.get(ticker)
        if current is None:
            entry = PriceEntry(
                price=price,
                previous_price=price,
                open_price=price if open_price is None else open_price,
                timestamp=timestamp,
            )
        else:
            entry = PriceEntry(
                price=price,
                previous_price=current.price,
                open_price=current.open_price if open_price is None else open_price,
                timestamp=timestamp,
            )
        self._entries[ticker] = entry
        return entry

    def remove(self, ticker: str) -> None:
        self._entries.pop(ticker, None)
