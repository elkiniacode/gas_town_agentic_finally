"""Market data: the shared price cache, the source interface and the simulator (PLAN.md §6)."""

import logging
from collections.abc import Mapping

from app.config import Settings
from app.market.cache import PriceCache, PriceEntry
from app.market.simulator import SimulatorSource
from app.market.source import MarketDataSource
from app.market.tracking import load_restart_prices, load_tracked_tickers, sync_ticker

logger = logging.getLogger(__name__)

__all__ = [
    "MarketDataSource",
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

    The Massive client is a stretch goal (fin-k90.11); until it lands, a
    configured key falls back to the simulator with a warning.
    """
    if settings.use_massive:
        logger.warning(
            "MASSIVE_API_KEY is set but the Massive client is not built yet; using the simulator"
        )
    return SimulatorSource(cache, seed_prices=seed_prices)
