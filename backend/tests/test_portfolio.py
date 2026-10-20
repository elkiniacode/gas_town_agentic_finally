import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import BadRequest
from app.main import create_app
from app.market import PriceCache, SimulatorSource
from app.services import (
    TradeError,
    execute_trade,
    get_history,
    get_portfolio,
    record_snapshot,
    run_snapshot_loop,
)
from app.services.rounding import format_quantity
from app.storage import Database, init_database
from app.timeutil import parse_iso


class Market:
    """A fresh DB plus a stopped simulator whose prices the test sets by hand."""

    def __init__(self, db_path: Path) -> None:
        self.db = init_database(db_path)
        self.cache = PriceCache()
        self.source = SimulatorSource(self.cache)
        self.lock = asyncio.Lock()

    def price(self, ticker: str, price: float) -> None:
        self.source.add_ticker(ticker)
        self.cache.update(ticker, price)

    def trade(self, ticker: str, quantity: float, side: str):
        return asyncio.run(
            execute_trade(self.db, self.cache, self.source, self.lock, ticker, quantity, side)
        )

    def portfolio(self) -> dict:
        return get_portfolio(self.db, self.cache)

    def count(self, table: str) -> int:
        with self.db.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.fixture
def market(db_path: Path) -> Market:
    return Market(db_path)


def _error(market: Market, *args) -> TradeError:
    with pytest.raises(TradeError) as info:
        market.trade(*args)
    return info.value


# --- trade execution -------------------------------------------------------


def test_buy_debits_cash_and_opens_position(market: Market) -> None:
    market.price("AAPL", 190.06)
    trade = market.trade(" aapl ", 10, "BUY")
    assert trade.to_wire() | {"id": "x", "executed_at": "t"} == {
        "id": "x",
        "ticker": "AAPL",
        "side": "buy",
        "quantity": 10.0,
        "price": 190.06,
        "total": 1900.60,
        "executed_at": "t",
    }
    parse_iso(trade.executed_at)
    assert market.portfolio() == {
        "cash_balance": 8099.40,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 10.0,
                "avg_cost": 190.06,
                "current_price": 190.06,
                "market_value": 1900.60,
                "unrealized_pnl": 0.0,
                "pnl_pct": 0.0,
            }
        ],
        "positions_value": 1900.60,
        "total_value": 10000.0,
        "total_pnl": 0.0,
        "total_pnl_pct": 0.0,
    }
    assert market.count("trades") == 1


def test_buys_use_weighted_average_cost(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 10, "buy")
    market.price("AAPL", 130.0)
    market.trade("AAPL", 5, "buy")
    (position,) = market.portfolio()["positions"]
    assert position["quantity"] == 15.0
    assert position["avg_cost"] == 110.0  # (10×100 + 5×130) / 15
    assert market.portfolio()["cash_balance"] == 10000 - 1000 - 650


def test_sell_keeps_avg_cost_and_credits_cash(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 10, "buy")
    market.price("AAPL", 120.0)
    trade = market.trade("AAPL", 4, "sell")
    assert trade.total == 480.0
    portfolio = market.portfolio()
    assert portfolio["cash_balance"] == 9000 + 480
    (position,) = portfolio["positions"]
    assert position["quantity"] == 6.0
    assert position["avg_cost"] == 100.0
    assert position["unrealized_pnl"] == 120.0
    assert position["pnl_pct"] == 20.0


def test_sell_at_a_loss(market: Market) -> None:
    market.price("TSLA", 250.0)
    market.trade("TSLA", 4, "buy")
    market.price("TSLA", 200.0)
    market.trade("TSLA", 2, "sell")
    portfolio = market.portfolio()
    assert portfolio["cash_balance"] == 10000 - 1000 + 400
    (position,) = portfolio["positions"]
    assert position["unrealized_pnl"] == -100.0
    assert position["pnl_pct"] == -20.0
    assert portfolio["total_value"] == 9800.0
    assert portfolio["total_pnl"] == -200.0
    assert portfolio["total_pnl_pct"] == -2.0


def test_full_close_deletes_position(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 2.5, "buy")
    market.trade("AAPL", 2.5, "sell")
    assert market.portfolio()["positions"] == []
    assert market.portfolio()["cash_balance"] == 10000.0
    assert market.count("positions") == 0


def test_dust_below_threshold_is_deleted(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 1.00005, "buy")  # rounds to 1.0001
    market.trade("AAPL", 1.0001, "sell")
    assert market.count("positions") == 0


def test_closing_unwatched_position_stops_pricing_it(market: Market) -> None:
    market.price("PYPL", 70.0)  # priced, but not on the watchlist
    market.trade("PYPL", 1, "buy")
    assert "PYPL" in market.source.tickers
    market.trade("PYPL", 1, "sell")
    assert "PYPL" not in market.source.tickers
    assert market.cache.get("PYPL") is None


def test_closing_watched_position_keeps_pricing_it(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 1, "buy")
    market.trade("AAPL", 1, "sell")
    assert market.cache.get("AAPL") is not None


def test_fractional_quantities_round_to_4dp_and_cash_to_2dp(market: Market) -> None:
    market.price("AAPL", 190.07)
    trade = market.trade("AAPL", 0.123456, "buy")
    assert trade.quantity == 0.1235
    assert trade.total == 23.47  # 0.1235 × 190.07 = 23.473645
    portfolio = market.portfolio()
    assert portfolio["cash_balance"] == 9976.53
    assert portfolio["positions"][0]["quantity"] == 0.1235


def test_buying_exactly_all_cash_is_allowed(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 100, "buy")
    assert market.portfolio()["cash_balance"] == 0.0


def test_insufficient_cash(market: Market) -> None:
    market.price("AAPL", 190.06)
    error = _error(market, "AAPL", 100, "buy")
    assert error.detail == "Insufficient cash: need $19006.00, have $10000.00"
    assert error.price == 190.06
    assert market.count("trades") == 0
    assert market.portfolio()["cash_balance"] == 10000.0


def test_oversell_is_rejected_not_clamped(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 2.5, "buy")
    error = _error(market, "AAPL", 5, "sell")
    assert error.detail == "Insufficient shares: requested 5, held 2.5"
    assert market.portfolio()["positions"][0]["quantity"] == 2.5


def test_sell_without_position(market: Market) -> None:
    market.price("AAPL", 100.0)
    assert _error(market, "AAPL", 1, "sell").detail == "Insufficient shares: requested 1, held 0"


def test_no_cached_price(market: Market) -> None:
    error = _error(market, "ZZZZ", 1, "buy")
    assert error.detail == "No price available for ZZZZ"
    assert error.price is None


@pytest.mark.parametrize(
    ("args", "detail"),
    [
        (("BRK.B", 1, "buy"), "Invalid ticker: must be 1-5 letters A-Z"),
        (("", 1, "buy"), "Invalid ticker: must be 1-5 letters A-Z"),
        (("AAPL", 1, "hold"), "Side must be 'buy' or 'sell'"),
        (("AAPL", 0, "buy"), "Quantity must be greater than 0"),
        (("AAPL", -1, "sell"), "Quantity must be greater than 0"),
        (("AAPL", 0.00004, "buy"), "Quantity must be greater than 0"),
        (("AAPL", float("nan"), "buy"), "Quantity must be greater than 0"),
        (("AAPL", float("inf"), "buy"), "Quantity must be greater than 0"),
        # Validation order: ticker, side, quantity, price.
        (("A1", 0, "hold"), "Invalid ticker: must be 1-5 letters A-Z"),
        (("AAPL", 0, "hold"), "Side must be 'buy' or 'sell'"),
        (("ZZZZ", 0, "buy"), "Quantity must be greater than 0"),
    ],
)
def test_validation(market: Market, args: tuple, detail: str) -> None:
    market.price("AAPL", 100.0)
    error = _error(market, *args)
    assert isinstance(error, BadRequest)
    assert error.detail == detail


def test_validation_errors_carry_cached_price(market: Market) -> None:
    market.price("AAPL", 100.0)
    assert _error(market, "AAPL", 1, "hold").price == 100.0
    assert _error(market, "BAD1", 1, "buy").price is None


def test_trade_records_snapshot(market: Market) -> None:
    market.price("AAPL", 100.0)
    before = market.count("portfolio_snapshots")
    market.trade("AAPL", 1, "buy")
    assert market.count("portfolio_snapshots") == before + 1
    _error(market, "AAPL", 1000, "buy")
    assert market.count("portfolio_snapshots") == before + 1


def test_trades_are_serialized_by_the_lock(market: Market) -> None:
    market.price("AAPL", 100.0)

    async def run() -> list:
        return await asyncio.gather(
            *(
                execute_trade(
                    market.db, market.cache, market.source, market.lock, "AAPL", 30, "buy"
                )
                for _ in range(5)
            ),
            return_exceptions=True,
        )

    results = asyncio.run(run())
    assert sum(isinstance(r, TradeError) for r in results) == 2  # 3 × $3000 fit in $10k
    assert market.portfolio()["cash_balance"] == 1000.0


@pytest.mark.parametrize(
    ("quantity", "text"), [(5, "5"), (2.5, "2.5"), (0, "0"), (1.23456, "1.2346"), (10.0, "10")]
)
def test_format_quantity(quantity: float, text: str) -> None:
    assert format_quantity(quantity) == text


# --- valuation, snapshots, history ----------------------------------------


def test_fresh_portfolio(market: Market) -> None:
    assert market.portfolio() == {
        "cash_balance": 10000.0,
        "positions": [],
        "positions_value": 0.0,
        "total_value": 10000.0,
        "total_pnl": 0.0,
        "total_pnl_pct": 0.0,
    }


def test_contract_example_valuation(market: Market) -> None:
    market.price("AAPL", 190.06)
    market.trade("AAPL", 10, "buy")
    market.cache.update("AAPL", 191.20)
    assert market.portfolio() == {
        "cash_balance": 8099.40,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 10.0,
                "avg_cost": 190.06,
                "current_price": 191.20,
                "market_value": 1912.00,
                "unrealized_pnl": 11.40,
                "pnl_pct": 0.60,
            }
        ],
        "positions_value": 1912.00,
        "total_value": 10011.40,
        "total_pnl": 11.40,
        "total_pnl_pct": 0.11,
    }


def test_positions_sorted_by_ticker_and_valued_at_avg_cost_without_price(
    market: Market,
) -> None:
    market.price("MSFT", 400.0)
    market.price("AAPL", 100.0)
    market.trade("MSFT", 1, "buy")
    market.trade("AAPL", 2, "buy")
    market.cache.remove("MSFT")  # e.g. Massive has no quote for it
    portfolio = market.portfolio()
    assert [p["ticker"] for p in portfolio["positions"]] == ["AAPL", "MSFT"]
    msft = portfolio["positions"][1]
    assert msft["current_price"] == 400.0
    assert msft["unrealized_pnl"] == 0.0
    assert portfolio["total_value"] == 10000.0


def test_record_snapshot_values_portfolio(market: Market) -> None:
    market.price("AAPL", 100.0)
    market.trade("AAPL", 10, "buy")
    market.cache.update("AAPL", 110.0)
    assert record_snapshot(market.db, market.cache) == 10100.0
    assert get_history(market.db, 1)[0]["total_value"] == 10100.0


def test_history_returns_most_recent_ascending(market: Market) -> None:
    with market.db.transaction() as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO portfolio_snapshots (id, total_value, recorded_at) VALUES (?, ?, ?)",
                (f"s{i}", 10000 + i, f"2030-01-01T00:00:0{i}.000Z"),
            )
    history = get_history(market.db, 3)
    assert history == [
        {"total_value": 10002.0, "recorded_at": "2030-01-01T00:00:02.000Z"},
        {"total_value": 10003.0, "recorded_at": "2030-01-01T00:00:03.000Z"},
        {"total_value": 10004.0, "recorded_at": "2030-01-01T00:00:04.000Z"},
    ]
    assert len(get_history(market.db)) == 6  # plus the seed snapshot


def test_snapshot_loop_records_until_cancelled(market: Market) -> None:
    async def run() -> None:
        task = asyncio.create_task(
            run_snapshot_loop(market.db, market.cache, market.lock, interval=0.01)
        )
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    before = market.count("portfolio_snapshots")
    asyncio.run(run())
    assert market.count("portfolio_snapshots") >= before + 2


def test_snapshot_loop_survives_errors(market: Market, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def flaky(db: Database, cache: PriceCache) -> float:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database is locked")
        return 0.0

    monkeypatch.setattr("app.services.portfolio.record_snapshot", flaky)

    async def run() -> None:
        task = asyncio.create_task(
            run_snapshot_loop(market.db, market.cache, market.lock, interval=0.01)
        )
        await asyncio.sleep(0.3)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 2


# --- routes ----------------------------------------------------------------


@pytest.fixture
def api(client: TestClient) -> Iterator[TestClient]:
    """The app client with the simulator stopped, so tests set prices by hand."""
    client.portal.call(client.app.state.market_source.stop)
    yield client


def _set_price(client: TestClient, ticker: str, price: float) -> None:
    client.app.state.price_cache.update(ticker, price)


def test_get_portfolio_fresh(api: TestClient) -> None:
    response = api.get("/api/portfolio")
    assert response.status_code == 200
    assert response.json() == {
        "cash_balance": 10000.0,
        "positions": [],
        "positions_value": 0.0,
        "total_value": 10000.0,
        "total_pnl": 0.0,
        "total_pnl_pct": 0.0,
    }


def test_trade_route_returns_trade_and_portfolio(api: TestClient) -> None:
    _set_price(api, "AAPL", 190.06)
    response = api.post(
        "/api/portfolio/trade", json={"ticker": "aapl", "quantity": 10, "side": "Buy"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"trade", "portfolio"}
    trade = body["trade"]
    assert set(trade) == {"id", "ticker", "side", "quantity", "price", "total", "executed_at"}
    assert (trade["ticker"], trade["side"], trade["quantity"]) == ("AAPL", "buy", 10.0)
    assert (trade["price"], trade["total"]) == (190.06, 1900.60)
    assert body["portfolio"]["cash_balance"] == 8099.40
    assert body["portfolio"] == api.get("/api/portfolio").json()


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"ticker": "AAPL", "quantity": 1}, "Invalid request: side: Field required"),
        ({"ticker": "AAPL", "quantity": "1", "side": "buy"}, "Invalid request: quantity:"),
        ({"ticker": 5, "quantity": 1, "side": "buy"}, "Invalid request: ticker:"),
        ({"ticker": "AAPL", "quantity": True, "side": "buy"}, "Invalid request: quantity:"),
        ({"ticker": "BRK.B", "quantity": 1, "side": "buy"}, "Invalid ticker"),
        ({"ticker": "AAPL", "quantity": 1, "side": "short"}, "Side must be 'buy' or 'sell'"),
        ({"ticker": "AAPL", "quantity": 0, "side": "buy"}, "Quantity must be greater than 0"),
        ({"ticker": "ZZZZ", "quantity": 1, "side": "buy"}, "No price available for ZZZZ"),
        ({"ticker": "AAPL", "quantity": 1000, "side": "buy"}, "Insufficient cash"),
        ({"ticker": "AAPL", "quantity": 1, "side": "sell"}, "Insufficient shares"),
    ],
)
def test_trade_route_errors(api: TestClient, body: dict, detail: str) -> None:
    _set_price(api, "AAPL", 190.0)
    response = api.post("/api/portfolio/trade", json=body)
    assert response.status_code == 400
    assert response.json()["detail"].startswith(detail)


def test_trade_route_rejects_nan_quantity(api: TestClient) -> None:
    response = api.post(
        "/api/portfolio/trade",
        content=b'{"ticker": "AAPL", "quantity": NaN, "side": "buy"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid request: quantity:")


def test_trade_route_records_snapshot_in_history(api: TestClient) -> None:
    _set_price(api, "AAPL", 100.0)
    api.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    _set_price(api, "AAPL", 150.0)
    api.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    snapshots = api.get("/api/portfolio/history").json()["snapshots"]
    assert [s["total_value"] for s in snapshots] == [10000.0, 10000.0, 10050.0]
    times = [s["recorded_at"] for s in snapshots]
    assert times == sorted(times)


def test_history_route(api: TestClient) -> None:
    response = api.get("/api/portfolio/history")
    assert response.status_code == 200
    (snapshot,) = response.json()["snapshots"]
    assert snapshot["total_value"] == 10000.0
    parse_iso(snapshot["recorded_at"])
    assert len(api.get("/api/portfolio/history?limit=1").json()["snapshots"]) == 1
    assert api.get("/api/portfolio/history?limit=10000").status_code == 200


@pytest.mark.parametrize("limit", ["0", "10001", "-1", "abc", "1.5", ""])
def test_history_route_bad_limit(api: TestClient, limit: str) -> None:
    response = api.get(f"/api/portfolio/history?limit={limit}")
    assert response.status_code == 400
    assert response.json() == {"detail": "limit must be an integer between 1 and 10000"}


def test_lifespan_runs_snapshot_task(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.main.run_snapshot_loop",
        lambda db, cache, lock: run_snapshot_loop(db, cache, lock, interval=0.01),
    )
    with TestClient(create_app(settings)) as client:
        client.portal.call(asyncio.sleep, 0.3)
        count = len(client.get("/api/portfolio/history").json()["snapshots"])
    assert count >= 2  # seed snapshot + at least one from the task
