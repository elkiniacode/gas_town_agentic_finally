"""The market data source interface shared by the simulator and Massive (R10)."""

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod

from app.market.cache import PriceCache

logger = logging.getLogger(__name__)


class MarketDataSource(ABC):
    """Writes prices for the tracked ticker set into a :class:`PriceCache`.

    ``add_ticker`` / ``remove_ticker`` are synchronous so request handlers can
    call them inline; the background loop picks up the change on its next tick.
    """

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache

    @abstractmethod
    async def start(self) -> None:
        """Begin the background loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background loop cleanly. Safe to call more than once."""

    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """Start pricing ``ticker``. Idempotent."""

    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """Stop pricing ``ticker`` and drop it from the cache. Idempotent."""

    @property
    @abstractmethod
    def tickers(self) -> frozenset[str]:
        """The tickers currently being priced."""


class BackgroundLoopSource(MarketDataSource):
    """A source driven by one asyncio task that calls :meth:`run` until cancelled."""

    def __init__(self, cache: PriceCache) -> None:
        super().__init__(cache)
        self._task: asyncio.Task[None] | None = None

    @abstractmethod
    async def run(self) -> None:
        """The loop body; runs forever until cancelled."""

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_logged(), name=type(self).__name__)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run_logged(self) -> None:
        try:
            await self.run()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s crashed; prices will stop updating", type(self).__name__)
            raise
