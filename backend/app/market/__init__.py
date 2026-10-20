"""Market data: price cache, source interface, simulator and Massive client (PLAN.md §6)."""

from collections.abc import Mapping

from app.config import Settings
from app.market.cache import PriceCache, PriceEntry
from app.market.massive import MassiveSource
from app.market.simulator import SimulatorSource
from app.market.source import MarketDataSource
from app.market.tracking import load_restart_prices, load_tracked_tickers, sync_ticker

__all__ = [
    "MarketDataSource",
    "MassiveSource",
    "PriceCache",
    "PriceEntry",
    "SimulatorSource",
    "create_market_source",
    "load_restart_prices",
    "load_tracked_tickers",
    "sync_ticker",
]


def create_market_source(
    settings: Settings, cache: PriceCache, seed_prices: Mapping[str, float] | None = None
) -> MarketDataSource:
    """Pick the source from ``MASSIVE_API_KEY`` (PLAN.md §5).

    ``seed_prices`` (restart continuity, R14) only apply to the simulator:
    Massive serves real prices, so held tickers wait for the first poll.
    """
    if settings.massive_api_key is not None:
        return MassiveSource(
            cache, settings.massive_api_key, poll_seconds=settings.massive_poll_seconds
        )
    return SimulatorSource(cache, seed_prices=seed_prices)
