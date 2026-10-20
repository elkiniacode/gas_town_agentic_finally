"""Built-in market simulator: correlated GBM with occasional jumps (PLAN.md §6).

Each tick every tracked ticker takes one GBM step

    S ← S · exp((μ − σ²/2)·dt + σ·√dt·ε)

where ε mixes one market shock, one shock per sector and one idiosyncratic
shock per ticker (S5), normalized to unit variance. The tunable knobs are the
module-level constants ``SIM_TIME_SCALE`` and ``EVENT_PROBABILITY`` (R15).
"""

import asyncio
import logging
import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

from app.market.cache import PriceCache
from app.market.source import BackgroundLoopSource
from app.timeutil import utc_now

logger = logging.getLogger(__name__)

TICK_SECONDS = 0.5
# Speed-up multiplier on simulated time (R15): 25× real trading time gives
# ≈0.04% per tick at σ = 30%/yr — lively but believable.
SIM_TIME_SCALE = 25.0
# Per-ticker, per-tick probability of a sudden ±2–5% jump (R15).
EVENT_PROBABILITY = 0.001
EVENT_MIN_MOVE = 0.02
EVENT_MAX_MOVE = 0.05

TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
DT = TICK_SECONDS / TRADING_SECONDS_PER_YEAR * SIM_TIME_SCALE

# Shock weights (S5). Tickers without a sector use W_SECTOR = 0.
W_MARKET = 0.5
W_SECTOR = 0.35
W_IDIOSYNCRATIC = 0.35

UNKNOWN_SEED_RANGE = (50.0, 300.0)
UNKNOWN_SIGMA = 0.35
UNKNOWN_BETA = 1.0


@dataclass(frozen=True)
class TickerProfile:
    seed_price: float
    sigma: float  # annualized volatility
    beta: float  # loading on the market shock
    sector: str | None
    mu: float = 0.0  # annualized drift


DEFAULT_PROFILES: dict[str, TickerProfile] = {
    "AAPL": TickerProfile(190.0, 0.25, 1.1, "tech"),
    "GOOGL": TickerProfile(175.0, 0.28, 1.1, "tech"),
    "MSFT": TickerProfile(420.0, 0.24, 1.0, "tech"),
    "AMZN": TickerProfile(185.0, 0.30, 1.2, "consumer"),
    "TSLA": TickerProfile(250.0, 0.55, 1.8, "consumer"),
    "NVDA": TickerProfile(120.0, 0.50, 1.7, "tech"),
    "META": TickerProfile(500.0, 0.35, 1.3, "tech"),
    "JPM": TickerProfile(200.0, 0.22, 0.9, "finance"),
    "V": TickerProfile(275.0, 0.20, 0.8, "finance"),
    "NFLX": TickerProfile(650.0, 0.38, 1.2, "consumer"),
}


def gbm_step(price: float, mu: float, sigma: float, dt: float, epsilon: float) -> float:
    """One exact GBM step for a standard-normal shock ``epsilon``."""
    return price * math.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * epsilon)


def combined_shock(
    beta: float, z_market: float, z_sector: float | None, z_idiosyncratic: float
) -> float:
    """Mix the shocks into one unit-variance ε (S5). ``z_sector=None`` means no sector."""
    w_market = beta * W_MARKET
    w_sector = 0.0 if z_sector is None else W_SECTOR
    numerator = (
        w_market * z_market + w_sector * (z_sector or 0.0) + W_IDIOSYNCRATIC * z_idiosyncratic
    )
    return numerator / math.sqrt(w_market**2 + w_sector**2 + W_IDIOSYNCRATIC**2)


class SimulatorSource(BackgroundLoopSource):
    """Default market data source; prices are available the instant a ticker is added.

    The full-precision price lives here; the cache receives it rounded to 2 dp
    so the displayed, streamed and fill prices are always the same number.
    """

    def __init__(
        self,
        cache: PriceCache,
        *,
        seed_prices: Mapping[str, float] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(cache)
        # Restart continuity (R14): seed overrides, consumed on first add.
        self._seed_overrides = dict(seed_prices or {})
        self._rng = rng or random.Random()
        self._profiles: dict[str, TickerProfile] = {}
        self._prices: dict[str, float] = {}

    @property
    def tickers(self) -> frozenset[str]:
        return frozenset(self._prices)

    def profile(self, ticker: str) -> TickerProfile | None:
        return self._profiles.get(ticker)

    def add_ticker(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        profile = DEFAULT_PROFILES.get(ticker) or TickerProfile(
            seed_price=self._rng.uniform(*UNKNOWN_SEED_RANGE),
            sigma=UNKNOWN_SIGMA,
            beta=UNKNOWN_BETA,
            sector=None,
        )
        seed = self._seed_overrides.pop(ticker, profile.seed_price)
        self._profiles[ticker] = profile
        self._prices[ticker] = seed
        # R12: priced immediately, so the ticker can be traded in the same request.
        self.cache.update(ticker, round(seed, 2))

    def remove_ticker(self, ticker: str) -> None:
        self._profiles.pop(ticker, None)
        self._prices.pop(ticker, None)
        self.cache.remove(ticker)

    def step(self) -> None:
        """Advance every tracked ticker by one tick and write the cache."""
        if not self._prices:
            return
        rng = self._rng
        z_market = rng.gauss(0.0, 1.0)
        z_sectors: dict[str, float] = {}
        now = utc_now()
        for ticker, price in self._prices.items():
            profile = self._profiles[ticker]
            z_sector = None
            if profile.sector is not None:
                if profile.sector not in z_sectors:
                    z_sectors[profile.sector] = rng.gauss(0.0, 1.0)
                z_sector = z_sectors[profile.sector]
            epsilon = combined_shock(profile.beta, z_market, z_sector, rng.gauss(0.0, 1.0))
            price = gbm_step(price, profile.mu, profile.sigma, DT, epsilon)
            if rng.random() < EVENT_PROBABILITY:
                move = rng.uniform(EVENT_MIN_MOVE, EVENT_MAX_MOVE)
                price *= 1 + move if rng.random() < 0.5 else 1 - move
            # Keep a 2 dp price strictly positive even after a run of down-moves.
            price = max(price, 0.01)
            self._prices[ticker] = price
            self.cache.update(ticker, round(price, 2), timestamp=now)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while True:
            next_tick += TICK_SECONDS
            try:
                self.step()
            except Exception:
                # One bad tick must not freeze prices for the rest of the process.
                logger.exception("Simulator tick failed")
            delay = next_tick - loop.time()
            if delay < 0:
                # Fell behind (e.g. a stalled loop): resync instead of bursting ticks.
                next_tick, delay = loop.time(), 0.0
            await asyncio.sleep(delay)
