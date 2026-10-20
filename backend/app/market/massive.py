"""Massive (formerly Polygon.io) REST market data source (PLAN.md §6, S6, R12, R16).

Polls once every ``MASSIVE_POLL_SECONDS``, making at most one HTTP call per
poll, in one of two modes:

* **snapshot** — the multi-ticker snapshot endpoint for the whole tracked set.
  Needs a paid plan (Stocks Starter or above; 15-minute delayed or real time).
* **eod** — the free Stocks Basic plan gets ``403 NOT_AUTHORIZED`` from the
  snapshot endpoint (R16, see planning/MASSIVE_FREE_TIER.md). The source then
  switches, for the rest of the process, to the grouped daily bars endpoint,
  which returns every US ticker's end-of-day bar for one date in one call.
  Prices move at most once per trading day.

Either way ``open_price`` is the previous trading day's close (R11). A symbol
the API does not return is left unpriced (``price: null``) and never removed
(R12). Rate limits and network errors back the poll interval off
exponentially; nothing here raises out of the loop.
"""

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.market.cache import PriceCache
from app.market.source import BackgroundLoopSource
from app.timeutil import utc_now

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.massive.com"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
GROUPED_DAILY_PATH = "/v2/aggs/grouped/locale/us/market/stocks/{day}"

REQUEST_TIMEOUT_SECONDS = 10.0
MAX_BACKOFF_SECONDS = 300.0
# How far back eod mode looks for trading days (covers long weekends + holidays).
EOD_LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: Any  # parsed JSON, or None when the body was not JSON


# (path, query params) -> response. Raises OSError on network failure.
Fetch = Callable[[str, Mapping[str, str]], Awaitable[HttpResponse]]


def make_http_fetch(
    api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = REQUEST_TIMEOUT_SECONDS
) -> Fetch:
    """A stdlib-only fetch that runs the blocking request in a worker thread.

    The key goes in the ``Authorization`` header, never the URL, so it cannot
    leak into logs.
    """

    def get(path: str, params: Mapping[str, str]) -> HttpResponse:
        url = base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(response.status, _parse_json(response.read()))
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code, _parse_json(exc.read()))

    async def fetch(path: str, params: Mapping[str, str]) -> HttpResponse:
        return await asyncio.to_thread(get, path, params)

    return fetch


def _parse_json(raw: bytes) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _positive(value: Any) -> float | None:
    """``value`` as a float if it is a positive number (the API uses 0 for "no data")."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def _field(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else None


def parse_snapshot(body: Any) -> dict[str, tuple[float, float | None]]:
    """``{ticker: (price, previous_close)}`` from a snapshot response.

    Price is the most recent of last trade, minute bar close, day close, and —
    before the day's first trade, after the 3:30 AM ET reset — the previous
    close. Tickers with no usable price are omitted.
    """
    parsed: dict[str, tuple[float, float | None]] = {}
    for item in _field(body, "tickers") or []:
        ticker = _field(item, "ticker")
        if not isinstance(ticker, str):
            continue
        previous_close = _positive(_field(_field(item, "prevDay"), "c"))
        price = (
            _positive(_field(_field(item, "lastTrade"), "p"))
            or _positive(_field(_field(item, "min"), "c"))
            or _positive(_field(_field(item, "day"), "c"))
            or previous_close
        )
        if price is not None:
            parsed[ticker] = (price, previous_close)
    return parsed


def parse_grouped_daily(body: Any) -> dict[str, float]:
    """``{ticker: close}`` from a grouped daily response; empty on a non-trading day."""
    closes: dict[str, float] = {}
    for bar in _field(body, "results") or []:
        ticker = _field(bar, "T")
        close = _positive(_field(bar, "c"))
        if isinstance(ticker, str) and close is not None:
            closes[ticker] = close
    return closes


class MassiveSource(BackgroundLoopSource):
    """Real market data via Massive REST polling.

    ``add_ticker`` cannot price immediately: a new ticker gets its price on the
    next poll (PLAN.md §6). Prices go into the cache rounded to 2 dp, like the
    simulator's, so displayed, streamed and fill prices are the same number.
    """

    def __init__(
        self,
        cache: PriceCache,
        api_key: str,
        *,
        poll_seconds: float,
        fetch: Fetch | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        super().__init__(cache)
        self.poll_seconds = poll_seconds
        self._fetch = fetch or make_http_fetch(api_key)
        self._today = today or (lambda: utc_now().date())
        self._tickers: dict[str, None] = {}  # insertion-ordered set
        self.mode = "snapshot"
        self._failures = 0
        self._problem: str | None = None  # last logged problem, to avoid log spam
        # eod mode: the UTC day the bars were loaded for, the next date to try,
        # and the trading days found so far, newest first.
        self._eod_anchor: date | None = None
        self._eod_cursor: date | None = None
        self._eod_days: list[dict[str, float]] = []

    @property
    def tickers(self) -> frozenset[str]:
        return frozenset(self._tickers)

    def add_ticker(self, ticker: str) -> None:
        self._tickers.setdefault(ticker, None)

    def remove_ticker(self, ticker: str) -> None:
        self._tickers.pop(ticker, None)
        self.cache.remove(ticker)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(await self.poll_once())

    async def poll_once(self) -> float:
        """Make at most one API call, update the cache, return seconds until the next poll."""
        try:
            if self.mode == "snapshot":
                ok = await self._poll_snapshot()
            else:
                ok = await self._poll_eod()
        except Exception as exc:  # network errors, timeouts, unexpected payloads
            ok = self._report(f"request failed: {exc!r}")
        if ok:
            self._failures = 0
            return self.poll_seconds
        self._failures += 1
        return min(self.poll_seconds * 2**self._failures, MAX_BACKOFF_SECONDS)

    async def _poll_snapshot(self) -> bool:
        if not self._tickers:
            # An empty ``tickers`` param would return the entire market.
            return True
        response = await self._fetch(SNAPSHOT_PATH, {"tickers": ",".join(self._tickers)})
        if response.status == 403:
            logger.warning(
                "Massive snapshot endpoint not available on this plan (%s); "
                "falling back to end-of-day grouped daily bars",
                _message(response),
            )
            self.mode = "eod"
            return True
        if response.status != 200:
            return self._report_status(response)
        self._clear_problem()
        now = utc_now()
        for ticker, (price, previous_close) in parse_snapshot(response.body).items():
            if ticker in self._tickers:  # skip tickers removed while the request ran
                self.cache.update(
                    ticker,
                    round(price, 2),
                    open_price=None if previous_close is None else round(previous_close, 2),
                    timestamp=now,
                )
        return True

    async def _poll_eod(self) -> bool:
        today = self._today()
        if today != self._eod_anchor:
            # New UTC day: look for fresh bars, keeping the old ones in the cache meanwhile.
            self._eod_anchor, self._eod_cursor, self._eod_days = today, today, []
        ok = True
        if len(self._eod_days) < 2:
            if self._eod_cursor >= today - timedelta(EOD_LOOKBACK_DAYS):
                ok = await self._fetch_eod_day(self._eod_cursor)
            elif not self._eod_days:
                ok = self._report(f"no end-of-day bars in the last {EOD_LOOKBACK_DAYS} days")
        self._write_eod()
        return ok

    async def _fetch_eod_day(self, day: date) -> bool:
        response = await self._fetch(
            GROUPED_DAILY_PATH.format(day=day.isoformat()), {"adjusted": "true"}
        )
        if response.status == 403:
            # Basic plans cannot read a day before it has closed; try the day before.
            self._eod_cursor = day - timedelta(1)
            return True
        if response.status != 200:
            return self._report_status(response)
        self._clear_problem()
        closes = parse_grouped_daily(response.body)
        if closes:
            self._eod_days.append(closes)
        self._eod_cursor = day - timedelta(1)
        return True

    def _write_eod(self) -> None:
        """Price every tracked ticker from the latest bars, every poll (covers new tickers)."""
        if not self._eod_days:
            return
        latest = self._eod_days[0]
        previous = self._eod_days[1] if len(self._eod_days) > 1 else {}
        now = utc_now()
        for ticker in self._tickers:
            close = latest.get(ticker)
            if close is None:
                continue
            previous_close = previous.get(ticker)
            self.cache.update(
                ticker,
                round(close, 2),
                open_price=None if previous_close is None else round(previous_close, 2),
                timestamp=now,
            )

    def _report_status(self, response: HttpResponse) -> bool:
        if response.status == 401:
            return self._report(f"API key rejected (HTTP 401: {_message(response)})")
        if response.status == 429:
            return self._report("rate limited (HTTP 429); backing off")
        return self._report(f"HTTP {response.status}: {_message(response)}")

    def _report(self, problem: str) -> bool:
        """Log a poll failure once per distinct problem. Always returns False."""
        if problem != self._problem:
            logger.warning("Massive poll failed: %s", problem)
            self._problem = problem
        return False

    def _clear_problem(self) -> None:
        if self._problem is not None:
            logger.info("Massive polling recovered")
            self._problem = None


def _message(response: HttpResponse) -> str:
    body = response.body
    for key in ("message", "error", "status"):
        value = _field(body, key)
        if isinstance(value, str) and value:
            return value
    return "no details"
