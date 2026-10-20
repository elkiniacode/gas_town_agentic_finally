"""Massive REST source (S6, R12, R16) against recorded responses — never the live API."""

import asyncio
import io
import json
import logging
import urllib.error
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.market import MarketDataSource, MassiveSource, PriceCache
from app.market import massive as m

FIXTURES = Path(__file__).parent / "fixtures" / "massive"
SUNDAY = date(2026, 10, 18)


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


class FakeFetch:
    """Scripted ``Fetch``: pops one response (or exception) per call and records the request."""

    def __init__(self, *responses: m.HttpResponse | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def __call__(self, path: str, params: Mapping[str, str]) -> m.HttpResponse:
        self.calls.append((path, dict(params)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def ok(name: str) -> m.HttpResponse:
    return m.HttpResponse(200, fixture(name))


def status(code: int, name: str) -> m.HttpResponse:
    return m.HttpResponse(code, fixture(name))


def _source(
    fetch: FakeFetch, *tickers: str, today: date = SUNDAY, poll_seconds: float = 15.0
) -> tuple[MassiveSource, PriceCache]:
    cache = PriceCache()
    source = MassiveSource(
        cache, "key", poll_seconds=poll_seconds, fetch=fetch, today=lambda: today
    )
    for ticker in tickers:
        source.add_ticker(ticker)
    return source, cache


def poll(source: MassiveSource) -> float:
    return asyncio.run(source.poll_once())


# --- Parsing ---------------------------------------------------------------------------------


def test_parse_snapshot_price_fallback_chain() -> None:
    parsed = m.parse_snapshot(fixture("snapshot_ok.json"))
    assert parsed == {
        "AAPL": (229.35, 227.786),  # last trade
        "MSFT": (418.12, 420.23),  # no trades on the plan: minute bar close
        "NVDA": (133.476, 133.476),  # after the daily reset: previous close
    }


@pytest.mark.parametrize(
    "body",
    [None, [], {}, {"tickers": None}, {"tickers": [{"ticker": "X"}, {"day": {"c": 5}}, "junk"]}],
)
def test_parse_snapshot_tolerates_junk(body: Any) -> None:
    assert m.parse_snapshot(body) == {}


def test_parse_grouped_daily() -> None:
    closes = m.parse_grouped_daily(fixture("grouped_daily_2026-10-16.json"))
    assert closes["AAPL"] == 227.786
    assert len(closes) == 4
    assert m.parse_grouped_daily(fixture("grouped_daily_empty.json")) == {}
    assert m.parse_grouped_daily({"results": [{"T": "A", "c": 0}, {"c": 3}, {"T": "B"}]}) == {}


# --- Snapshot mode (paid plans) ---------------------------------------------------------------


def test_massive_conforms_to_interface() -> None:
    assert issubclass(MassiveSource, MarketDataSource)


def test_snapshot_poll_updates_cache_with_previous_close_as_open() -> None:
    fetch = FakeFetch(ok("snapshot_ok.json"))
    source, cache = _source(fetch, "AAPL", "MSFT", "NVDA", "ZZZZ")
    assert poll(source) == 15.0
    assert fetch.calls == [(m.SNAPSHOT_PATH, {"tickers": "AAPL,MSFT,NVDA,ZZZZ"})]
    aapl = cache.get("AAPL")
    assert (aapl.price, aapl.previous_price, aapl.open_price) == (229.35, 229.35, 227.79)
    assert cache.get("MSFT").open_price == 420.23
    assert cache.get("NVDA").price == cache.get("NVDA").open_price == 133.48


def test_invalid_symbol_stays_tracked_without_price() -> None:
    # R12: absent from the response -> no cache entry, still tracked, not removed.
    source, cache = _source(FakeFetch(ok("snapshot_ok.json")), "AAPL", "ZZZZ")
    poll(source)
    assert "ZZZZ" not in cache
    assert "ZZZZ" in source.tickers


def test_add_ticker_is_unpriced_until_next_poll() -> None:
    fetch = FakeFetch(ok("snapshot_ok.json"), ok("snapshot_ok.json"))
    source, cache = _source(fetch, "AAPL")
    poll(source)
    source.add_ticker("MSFT")
    source.add_ticker("MSFT")  # idempotent
    assert "MSFT" not in cache
    poll(source)
    assert fetch.calls[1][1] == {"tickers": "AAPL,MSFT"}
    assert cache.get("MSFT").price == 418.12


def test_unchanged_price_between_polls_is_not_an_error() -> None:
    # Market closed / delayed data: same numbers each poll, previous_price == price.
    source, cache = _source(FakeFetch(ok("snapshot_ok.json"), ok("snapshot_ok.json")), "AAPL")
    poll(source)
    first = cache.get("AAPL")
    assert poll(source) == 15.0
    second = cache.get("AAPL")
    assert second.price == second.previous_price == first.price
    assert second.timestamp >= first.timestamp


def test_remove_ticker_drops_cache_and_skips_in_flight_results() -> None:
    source, cache = _source(FakeFetch(ok("snapshot_ok.json")), "AAPL", "MSFT")

    async def scenario() -> None:
        # Remove MSFT while the request is "in flight": the response must not re-add it.
        real_fetch = source._fetch

        async def slow_fetch(path: str, params: Mapping[str, str]) -> m.HttpResponse:
            source.remove_ticker("MSFT")
            return await real_fetch(path, params)

        source._fetch = slow_fetch
        await source.poll_once()

    asyncio.run(scenario())
    assert "MSFT" not in cache
    assert "AAPL" in cache
    source.remove_ticker("AAPL")
    source.remove_ticker("AAPL")  # idempotent
    assert "AAPL" not in cache
    assert source.tickers == frozenset()


def test_no_tickers_makes_no_request() -> None:
    # An empty ``tickers`` param would return the whole market.
    fetch = FakeFetch()
    source, _ = _source(fetch)
    assert poll(source) == 15.0
    assert fetch.calls == []


# --- Errors and backoff -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        status(429, "rate_limited.json"),
        status(401, "unauthorized.json"),
        m.HttpResponse(502, None),
        OSError("connection refused"),
        TimeoutError("timed out"),
    ],
)
def test_failures_back_off_then_recover(failure: m.HttpResponse | Exception) -> None:
    fetch = FakeFetch(failure, failure, failure, ok("snapshot_ok.json"), ok("snapshot_ok.json"))
    source, cache = _source(fetch, "AAPL", poll_seconds=10.0)
    assert [poll(source) for _ in range(3)] == [20.0, 40.0, 80.0]
    assert "AAPL" not in cache
    assert poll(source) == 10.0
    assert cache.get("AAPL").price == 229.35
    assert source.mode == "snapshot"


def test_backoff_is_capped() -> None:
    failures = [m.HttpResponse(500, None)] * 12
    source, _ = _source(FakeFetch(*failures), "AAPL")
    delays = [poll(source) for _ in range(12)]
    assert max(delays) == m.MAX_BACKOFF_SECONDS
    assert delays[-1] == m.MAX_BACKOFF_SECONDS


def test_failure_keeps_last_good_prices() -> None:
    fetch = FakeFetch(ok("snapshot_ok.json"), OSError("network down"))
    source, cache = _source(fetch, "AAPL")
    poll(source)
    poll(source)
    assert cache.get("AAPL").price == 229.35


def test_repeated_failure_logs_once(caplog: pytest.LogCaptureFixture) -> None:
    failures = [status(429, "rate_limited.json")] * 3
    source, _ = _source(FakeFetch(*failures, ok("snapshot_ok.json")), "AAPL")
    with caplog.at_level(logging.INFO, logger="app.market.massive"):
        for _ in range(4):
            poll(source)
    messages = [r.getMessage() for r in caplog.records]
    assert sum("rate limited" in msg for msg in messages) == 1
    assert any("recovered" in msg for msg in messages)


def test_loop_survives_failures_and_stops_cleanly() -> None:
    fetch = FakeFetch(ValueError("bad payload"), *[ok("snapshot_ok.json")] * 50)
    source, cache = _source(fetch, "AAPL", poll_seconds=0.005)

    async def scenario() -> None:
        await source.start()
        await asyncio.sleep(0.1)
        assert source.running
        await source.stop()
        await source.stop()  # safe twice
        assert not source.running

    asyncio.run(scenario())
    assert cache.get("AAPL").price == 229.35


# --- End-of-day fallback (free Stocks Basic plan, R16) --------------------------------------


def _eod_fetch(*rest: m.HttpResponse) -> FakeFetch:
    return FakeFetch(
        status(403, "snapshot_not_authorized.json"),  # snapshot: not on this plan
        status(403, "grouped_daily_before_close.json"),  # Sun 10-18
        ok("grouped_daily_empty.json"),  # Sat 10-17
        ok("grouped_daily_2026-10-16.json"),  # Fri
        ok("grouped_daily_2026-10-15.json"),  # Thu
        *rest,
    )


def test_not_authorized_switches_to_eod_and_walks_back_to_trading_days() -> None:
    fetch = _eod_fetch()
    source, cache = _source(fetch, "AAPL", "MSFT", "NVDA", "ZZZZ")
    assert poll(source) == 15.0
    assert source.mode == "eod"
    assert cache.get_all() == {}

    poll(source)  # Sun: 403 before close
    poll(source)  # Sat: no trading
    assert cache.get_all() == {}
    poll(source)  # Fri: priced, no previous close yet -> open = price
    assert cache.get("AAPL").price == cache.get("AAPL").open_price == 227.79
    poll(source)  # Thu: previous close becomes open_price
    assert [path for path, _ in fetch.calls[1:]] == [
        m.GROUPED_DAILY_PATH.format(day=d)
        for d in ("2026-10-18", "2026-10-17", "2026-10-16", "2026-10-15")
    ]
    assert all(params == {"adjusted": "true"} for _, params in fetch.calls[1:])
    aapl, msft, nvda = cache.get("AAPL"), cache.get("MSFT"), cache.get("NVDA")
    assert (aapl.price, aapl.open_price) == (227.79, 225.0)
    assert (msft.price, msft.open_price) == (420.23, 421.0)
    assert (nvda.price, nvda.open_price) == (133.48, 133.48)  # missing Thu: keeps first open
    assert "ZZZZ" not in cache


def test_eod_makes_no_more_calls_once_loaded_and_prices_new_tickers() -> None:
    fetch = _eod_fetch()
    source, cache = _source(fetch, "AAPL")
    for _ in range(5):
        poll(source)
    calls = len(fetch.calls)
    source.add_ticker("KIMpL")
    assert poll(source) == 15.0
    assert len(fetch.calls) == calls  # served from the stored bars
    assert cache.get("KIMpL").price == 25.91
    assert cache.get("KIMpL").open_price == 25.8


def test_eod_reloads_on_a_new_day_keeping_old_prices_meanwhile() -> None:
    fetch = _eod_fetch(OSError("network down"), ok("grouped_daily_2026-10-16.json"))
    day = [SUNDAY]
    cache = PriceCache()
    source = MassiveSource(cache, "k", poll_seconds=15.0, fetch=fetch, today=lambda: day[0])
    source.add_ticker("AAPL")
    for _ in range(5):
        poll(source)
    day[0] = date(2026, 10, 19)
    assert poll(source) == 30.0  # network error on the Monday fetch: back off
    assert cache.get("AAPL").price == 227.79  # still showing the old close
    poll(source)
    assert fetch.calls[-1][0] == m.GROUPED_DAILY_PATH.format(day="2026-10-19")


def test_eod_gives_up_after_lookback_window(caplog: pytest.LogCaptureFixture) -> None:
    empties = [ok("grouped_daily_empty.json")] * (m.EOD_LOOKBACK_DAYS + 1)
    fetch = FakeFetch(status(403, "snapshot_not_authorized.json"), *empties)
    source, cache = _source(fetch, "AAPL")
    for _ in range(len(empties) + 1):
        poll(source)
    calls = len(fetch.calls)
    with caplog.at_level(logging.WARNING, logger="app.market.massive"):
        assert poll(source) > 15.0
    assert len(fetch.calls) == calls  # no more requests until the next day
    assert "no end-of-day bars" in caplog.text
    assert cache.get_all() == {}


# --- HTTP layer (urlopen is patched; no sockets) --------------------------------------------


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_http_fetch_sends_key_in_header_not_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeResponse:
        seen["url"], seen["auth"], seen["timeout"] = (
            request.full_url,
            request.get_header("Authorization"),
            timeout,
        )
        return _FakeResponse((FIXTURES / "snapshot_ok.json").read_bytes())

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    fetch = m.make_http_fetch("secret-key", base_url="https://api.example.test")
    response = asyncio.run(fetch(m.SNAPSHOT_PATH, {"tickers": "AAPL,MSFT"}))
    assert response.status == 200
    assert response.body["count"] == 3
    assert seen["url"] == (
        "https://api.example.test/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL%2CMSFT"
    )
    assert seen["auth"] == "Bearer secret-key"
    assert "secret-key" not in seen["url"]
    assert seen["timeout"] == m.REQUEST_TIMEOUT_SECONDS


def test_http_fetch_maps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> None:
        body = io.BytesIO((FIXTURES / "rate_limited.json").read_bytes())
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, body)

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    response = asyncio.run(m.make_http_fetch("k")(m.SNAPSHOT_PATH, {}))
    assert response.status == 429
    assert response.body["status"] == "ERROR"


def test_http_fetch_non_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> None:
        body = io.BytesIO(b"<html>Bad Gateway</html>")
        raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", {}, body)

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    assert asyncio.run(m.make_http_fetch("k")(m.SNAPSHOT_PATH, {})) == m.HttpResponse(502, None)
