import asyncio
import inspect
import json
import math
import random
import statistics
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.market import (
    MarketDataSource,
    MassiveSource,
    PriceCache,
    SimulatorSource,
    create_market_source,
    load_restart_prices,
    load_tracked_tickers,
    sync_ticker,
)
from app.market import simulator as sim
from app.routers.market import price_events
from app.storage import DEFAULT_TICKERS, Database, new_id
from app.timeutil import parse_iso, utc_now_iso

WIRE_KEYS = {"price", "previous_price", "open_price", "timestamp"}


def _source(seed: int = 7, **kwargs) -> tuple[SimulatorSource, PriceCache]:
    cache = PriceCache()
    return SimulatorSource(cache, rng=random.Random(seed), **kwargs), cache


def _log_returns(source: SimulatorSource, tickers: list[str], steps: int) -> dict[str, list[float]]:
    returns: dict[str, list[float]] = {t: [] for t in tickers}
    prev = {t: source._prices[t] for t in tickers}
    for _ in range(steps):
        source.step()
        for t in tickers:
            price = source._prices[t]
            returns[t].append(math.log(price / prev[t]))
            prev[t] = price
    return returns


def _add_position(db: Database, ticker: str, quantity: float, trade_prices: list[float]) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (new_id(), ticker, quantity, trade_prices[0], utc_now_iso()),
        )
        for i, price in enumerate(trade_prices):
            conn.execute(
                "INSERT INTO trades (id, ticker, side, quantity, price, executed_at)"
                " VALUES (?, ?, 'buy', ?, ?, ?)",
                (new_id(), ticker, quantity, price, f"2026-10-18T14:00:0{i}.000Z"),
            )


def _parse_events(lines: list[str]) -> list[dict]:
    return [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data: ")]


# --- Price cache ---------------------------------------------------------------------------


def test_cache_first_write_sets_previous_and_open_to_price() -> None:
    cache = PriceCache()
    entry = cache.update("AAPL", 190.0)
    assert (entry.price, entry.previous_price, entry.open_price) == (190.0, 190.0, 190.0)
    assert entry.timestamp.tzinfo is not None
    assert cache.get("AAPL") == entry


def test_cache_later_writes_track_previous_and_keep_open() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("AAPL", 191.0)
    entry = cache.update("AAPL", 189.5)
    assert (entry.price, entry.previous_price, entry.open_price) == (189.5, 191.0, 190.0)
    # An explicit open price (Massive's previous close) replaces it.
    assert cache.update("AAPL", 189.6, open_price=185.0).open_price == 185.0


def test_cache_get_all_is_a_copy_and_remove_is_idempotent() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    snapshot = cache.get_all()
    cache.update("MSFT", 420.0)
    assert set(snapshot) == {"AAPL"}
    cache.remove("AAPL")
    cache.remove("AAPL")
    assert cache.get("AAPL") is None
    assert set(cache.get_all()) == {"MSFT"}


def test_entry_wire_format() -> None:
    cache = PriceCache()
    ts = datetime(2026, 10, 18, 14, 3, 12, 500_000, tzinfo=UTC)
    cache.update("AAPL", 190.004, timestamp=ts)
    entry = cache.update("AAPL", 190.126, timestamp=ts)
    assert entry.to_wire() == {
        "price": 190.13,
        "previous_price": 190.0,
        "open_price": 190.0,
        "timestamp": "2026-10-18T14:03:12.500Z",
    }


# --- GBM math ------------------------------------------------------------------------------


def test_dt_matches_plan() -> None:
    assert math.isclose(sim.DT, 0.5 / (252 * 6.5 * 3600) * 25)
    # σ = 30%/yr → ≈0.04% per tick (PLAN.md §6).
    assert 0.3 * math.sqrt(sim.DT) == pytest.approx(0.00044, abs=0.00002)


def test_gbm_step_deterministic_parts() -> None:
    dt = 0.01
    assert sim.gbm_step(100.0, 0.0, 0.3, dt, 0.0) == pytest.approx(100 * math.exp(-0.5 * 0.09 * dt))
    up = sim.gbm_step(100.0, 0.0, 0.3, dt, 1.0)
    down = sim.gbm_step(100.0, 0.0, 0.3, dt, -1.0)
    assert math.log(up / 100) == pytest.approx(-0.5 * 0.09 * dt + 0.3 * math.sqrt(dt))
    assert down < 100 < up
    assert sim.gbm_step(100.0, 0.2, 0.0, 1.0, 5.0) == pytest.approx(100 * math.exp(0.2))


def test_gbm_log_returns_have_expected_mean_and_variance() -> None:
    rng = random.Random(1)
    sigma, dt, n = 0.3, 1 / 252, 20_000
    returns = [math.log(sim.gbm_step(1.0, 0.0, sigma, dt, rng.gauss(0, 1))) for _ in range(n)]
    assert statistics.fmean(returns) == pytest.approx(
        -0.5 * sigma**2 * dt, abs=4 * sigma * math.sqrt(dt / n)
    )
    assert statistics.stdev(returns) == pytest.approx(sigma * math.sqrt(dt), rel=0.03)


def test_combined_shock_is_unit_variance() -> None:
    rng = random.Random(2)
    for beta, sector in [(1.1, True), (1.8, True), (0.8, True), (1.0, False)]:
        shocks = [
            sim.combined_shock(
                beta, rng.gauss(0, 1), rng.gauss(0, 1) if sector else None, rng.gauss(0, 1)
            )
            for _ in range(20_000)
        ]
        assert statistics.pvariance(shocks) == pytest.approx(1.0, rel=0.04)


# --- Simulator behavior --------------------------------------------------------------------


def test_default_tickers_use_seed_table() -> None:
    source, cache = _source()
    for ticker in DEFAULT_TICKERS:
        source.add_ticker(ticker)
    assert set(sim.DEFAULT_PROFILES) == set(DEFAULT_TICKERS)
    for ticker in DEFAULT_TICKERS:
        entry = cache.get(ticker)
        assert entry.price == sim.DEFAULT_PROFILES[ticker].seed_price
        assert entry.previous_price == entry.open_price == entry.price
    assert sim.DEFAULT_PROFILES["NFLX"] == sim.TickerProfile(650.0, 0.38, 1.2, "consumer")


def test_unknown_ticker_is_seeded_immediately() -> None:
    source, cache = _source()
    source.add_ticker("PYPL")
    entry = cache.get("PYPL")
    assert entry is not None
    assert 50.0 <= entry.price <= 300.0
    assert entry.previous_price == entry.open_price == entry.price
    profile = source.profile("PYPL")
    assert (profile.sigma, profile.beta, profile.sector) == (0.35, 1.0, None)


def test_unknown_ticker_seeds_vary() -> None:
    source, cache = _source()
    for ticker in ("AAA", "BBB", "CCC", "DDD", "EEE"):
        source.add_ticker(ticker)
    prices = {cache.get(t).price for t in ("AAA", "BBB", "CCC", "DDD", "EEE")}
    assert len(prices) == 5


def test_seed_prices_override_table_seed() -> None:
    source, cache = _source(seed_prices={"AAPL": 201.37, "PYPL": 70.0})
    source.add_ticker("AAPL")
    source.add_ticker("PYPL")
    source.add_ticker("MSFT")
    assert cache.get("AAPL").open_price == 201.37
    assert cache.get("PYPL").price == 70.0
    assert cache.get("MSFT").price == 420.0


def test_add_ticker_is_idempotent() -> None:
    source, cache = _source()
    source.add_ticker("AAPL")
    for _ in range(10):
        source.step()
    before = cache.get("AAPL")
    source.add_ticker("AAPL")
    assert cache.get("AAPL") == before
    assert before.open_price == 190.0


def test_remove_ticker_drops_it_everywhere() -> None:
    source, cache = _source()
    source.add_ticker("AAPL")
    source.add_ticker("MSFT")
    source.remove_ticker("AAPL")
    source.remove_ticker("AAPL")
    source.step()
    assert source.tickers == frozenset({"MSFT"})
    assert cache.get("AAPL") is None
    assert set(cache.get_all()) == {"MSFT"}


def test_step_updates_previous_price_and_keeps_open() -> None:
    source, cache = _source()
    source.add_ticker("AAPL")
    first = cache.get("AAPL")
    source.step()
    second = cache.get("AAPL")
    source.step()
    third = cache.get("AAPL")
    assert second.previous_price == first.price
    assert third.previous_price == second.price
    assert third.open_price == 190.0
    assert third.timestamp >= first.timestamp


def test_prices_stay_positive_and_rounded() -> None:
    source, cache = _source(seed=3)
    for ticker in (*DEFAULT_TICKERS, "PYPL"):
        source.add_ticker(ticker)
    for _ in range(5_000):
        source.step()
        for entry in cache.get_all().values():
            assert entry.price > 0
    for entry in cache.get_all().values():
        assert entry.price == round(entry.price, 2)


def test_tick_moves_are_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sim, "EVENT_PROBABILITY", 0.0)
    source, _ = _source(seed=4)
    source.add_ticker("TSLA")
    returns = _log_returns(source, ["TSLA"], 2_000)["TSLA"]
    # σ = 0.55 → ≈0.08% per tick; no tick should move anywhere near 1%.
    assert statistics.stdev(returns) == pytest.approx(0.55 * math.sqrt(sim.DT), rel=0.1)
    assert max(abs(r) for r in returns) < 0.01


def test_correlation_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sim, "EVENT_PROBABILITY", 0.0)
    source, _ = _source(seed=5)
    tickers = ["AAPL", "GOOGL", "JPM", "V", "PYPL"]
    for ticker in tickers:
        source.add_ticker(ticker)
    r = _log_returns(source, tickers, 6_000)
    same_sector = statistics.correlation(r["AAPL"], r["GOOGL"])  # expected ≈0.78
    cross_sector = statistics.correlation(r["AAPL"], r["JPM"])  # expected ≈0.50
    no_sector = statistics.correlation(r["AAPL"], r["PYPL"])  # expected ≈0.48
    assert same_sector > 0.7
    assert 0.35 < cross_sector < 0.65
    assert 0.3 < no_sector < 0.65
    assert same_sector > cross_sector
    assert statistics.correlation(r["JPM"], r["V"]) > 0.6


def test_events_jump_two_to_five_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sim, "EVENT_PROBABILITY", 1.0)
    source, _ = _source(seed=6)
    source.add_ticker("JPM")
    returns = _log_returns(source, ["JPM"], 500)["JPM"]
    tick_noise = 5 * 0.22 * math.sqrt(sim.DT)
    for ret in returns:
        assert math.log(1 - 0.05) - tick_noise <= ret <= math.log(1 + 0.05) + tick_noise
        assert abs(ret) >= math.log(1 + 0.02) - tick_noise
    assert any(ret > 0 for ret in returns) and any(ret < 0 for ret in returns)


def test_events_are_rare_by_default() -> None:
    assert sim.EVENT_PROBABILITY == 0.001
    source, _ = _source(seed=8)
    for ticker in DEFAULT_TICKERS:
        source.add_ticker(ticker)
    r = _log_returns(source, list(DEFAULT_TICKERS), 5_000)
    jumps = sum(abs(x) > 0.015 for returns in r.values() for x in returns)
    # 50,000 ticker-ticks × 0.001 ≈ 50 events.
    assert 20 < jumps < 90


# --- Interface conformance -----------------------------------------------------------------


def test_simulator_implements_interface() -> None:
    assert issubclass(SimulatorSource, MarketDataSource)
    assert not inspect.isabstract(SimulatorSource)
    for name in ("start", "stop"):
        assert inspect.iscoroutinefunction(getattr(SimulatorSource, name))
    for name in ("add_ticker", "remove_ticker"):
        assert not inspect.iscoroutinefunction(getattr(SimulatorSource, name))
    with pytest.raises(TypeError):
        MarketDataSource(PriceCache())  # type: ignore[abstract]


def test_start_ticks_in_background_and_stop_is_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sim, "TICK_SECONDS", 0.01)

    async def scenario() -> None:
        source, cache = _source()
        source.add_ticker("AAPL")
        seeded = cache.get("AAPL")
        await source.start()
        await source.start()  # idempotent
        assert source.running
        await asyncio.sleep(0.1)
        await source.stop()
        await source.stop()  # idempotent
        assert not source.running
        stopped = cache.get("AAPL")
        assert stopped.timestamp > seeded.timestamp
        await asyncio.sleep(0.05)
        assert cache.get("AAPL") == stopped

    asyncio.run(scenario())


def test_bad_tick_does_not_kill_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sim, "TICK_SECONDS", 0.01)
    calls = 0
    original = SimulatorSource.step

    def flaky(self: SimulatorSource) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        original(self)

    monkeypatch.setattr(SimulatorSource, "step", flaky)

    async def scenario() -> None:
        source, _ = _source()
        await source.start()
        await asyncio.sleep(0.1)
        assert source.running
        await source.stop()

    asyncio.run(scenario())
    assert calls > 2


def test_massive_key_selects_massive_source(settings: Settings) -> None:
    source = create_market_source(
        replace(settings, massive_api_key="k", massive_poll_seconds=5.0), PriceCache()
    )
    assert isinstance(source, MassiveSource)
    assert source.poll_seconds == 5.0
    assert isinstance(create_market_source(settings, PriceCache()), SimulatorSource)


# --- Tracked set (R9) and restart continuity (R14) -----------------------------------------


def test_tracked_set_is_watchlist_then_unwatched_positions(db: Database) -> None:
    assert load_tracked_tickers(db) == list(DEFAULT_TICKERS)
    _add_position(db, "PYPL", 2, [70.0])
    _add_position(db, "AAPL", 1, [190.0])
    assert load_tracked_tickers(db) == [*DEFAULT_TICKERS, "PYPL"]


def test_restart_prices_use_latest_trade(db: Database) -> None:
    assert load_restart_prices(db) == {}
    _add_position(db, "AAPL", 1, [190.0, 195.5, 193.25])
    assert load_restart_prices(db) == {"AAPL": 193.25}


def test_sync_ticker_follows_watchlist_and_positions(db: Database) -> None:
    source, cache = _source()
    for ticker in load_tracked_tickers(db):
        source.add_ticker(ticker)

    # Removed from the watchlist with no position → unpriced.
    with db.transaction() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = 'NFLX'")
    assert sync_ticker(db, source, "NFLX") is False
    assert cache.get("NFLX") is None

    # Added to the watchlist → priced immediately.
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO watchlist (id, ticker, added_at) VALUES (?, 'PYPL', ?)",
            (new_id(), utc_now_iso()),
        )
    assert sync_ticker(db, source, "PYPL") is True
    assert cache.get("PYPL") is not None

    # Held but removed from the watchlist → stays priced.
    _add_position(db, "TSLA", 1, [250.0])
    with db.transaction() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = 'TSLA'")
    assert sync_ticker(db, source, "TSLA") is True
    assert cache.get("TSLA") is not None

    # Position closed and not watched → unpriced.
    with db.transaction() as conn:
        conn.execute("DELETE FROM positions WHERE ticker = 'TSLA'")
    assert sync_ticker(db, source, "TSLA") is False
    assert cache.get("TSLA") is None


def test_lifespan_prices_tracked_set(client: TestClient) -> None:
    state = client.app.state
    assert isinstance(state.market_source, SimulatorSource)
    assert state.market_source.running
    assert set(state.price_cache.get_all()) == set(DEFAULT_TICKERS)
    assert state.market_source.tickers == frozenset(DEFAULT_TICKERS)


def test_lifespan_seeds_held_tickers_from_last_trade(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        db = client.app.state.db
        _add_position(db, "AAPL", 3, [190.0, 204.17])
        _add_position(db, "PYPL", 1, [71.5])
        source = client.app.state.market_source
    assert not source.running  # stopped by the lifespan

    with TestClient(create_app(settings)) as client:
        cache = client.app.state.price_cache
        assert cache.get("AAPL").open_price == 204.17
        assert cache.get("PYPL").open_price == 71.5
        assert cache.get("MSFT").open_price == 420.0


# --- SSE -----------------------------------------------------------------------------------


def test_sse_headers_and_first_events(client: TestClient) -> None:
    with client.stream("GET", "/api/stream/prices") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        lines = []
        for line in response.iter_lines():
            lines.append(line)
            if len(_parse_events(lines)) == 2:
                break

    assert lines[0] == "retry: 2000"
    assert lines[1].startswith("data: ")
    assert lines[2] == ""
    events = _parse_events(lines)
    for event in events:
        assert set(event) == set(DEFAULT_TICKERS)
        for update in event.values():
            assert set(update) == WIRE_KEYS
            assert update["price"] > 0
            assert update["price"] == round(update["price"], 2)
            assert update["timestamp"].endswith("Z")
            parse_iso(update["timestamp"])
    assert events[1]["AAPL"]["timestamp"] >= events[0]["AAPL"]["timestamp"]


def test_sse_reflects_added_and_removed_tickers(client: TestClient) -> None:
    source = client.app.state.market_source
    with client.stream("GET", "/api/stream/prices") as response:
        lines = response.iter_lines()
        first = _parse_events([next(lines) for _ in range(2)])[0]
        assert "PYPL" not in first
        # Mutate the source on the app's event loop, as a request handler would.
        client.portal.call(source.add_ticker, "PYPL")
        client.portal.call(source.remove_ticker, "NFLX")
        while not (line := next(lines)).startswith("data: "):
            pass
        event = json.loads(line.removeprefix("data: "))
    assert "PYPL" in event
    assert "NFLX" not in event


def test_sse_empty_cache_sends_empty_object() -> None:
    async def first_two() -> list[str]:
        stream = price_events(PriceCache(), interval=0.01)
        chunks = [await anext(stream), await anext(stream)]
        await stream.aclose()
        return chunks

    first, second = asyncio.run(first_two())
    assert first == "retry: 2000\ndata: {}\n\n"
    assert second == "data: {}\n\n"
