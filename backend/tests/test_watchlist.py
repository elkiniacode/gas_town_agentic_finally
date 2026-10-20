from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.storage import DEFAULT_TICKERS
from app.timeutil import parse_iso

INVALID = {"detail": "Invalid ticker: must be 1-5 letters A-Z"}
ITEM_KEYS = {"ticker", "price", "previous_price", "open_price", "change_pct", "added_at"}


@pytest.fixture
def api(client: TestClient) -> Iterator[TestClient]:
    """The app client with the simulator stopped, so tests set prices by hand."""
    client.portal.call(client.app.state.market_source.stop)
    yield client


def _tickers(body: dict) -> list[str]:
    return [item["ticker"] for item in body["watchlist"]]


def test_get_watchlist_defaults_in_seed_order(api: TestClient) -> None:
    response = api.get("/api/watchlist")
    assert response.status_code == 200
    body = response.json()
    assert _tickers(body) == list(DEFAULT_TICKERS)
    for item in body["watchlist"]:
        assert set(item) == ITEM_KEYS
        assert item["price"] > 0
        parse_iso(item["added_at"])


def test_watchlist_prices_and_change_pct(api: TestClient) -> None:
    cache = api.app.state.price_cache
    cache.update("AAPL", 189.50, open_price=189.50)
    cache.update("AAPL", 190.05)
    cache.update("AAPL", 190.12)
    aapl = api.get("/api/watchlist").json()["watchlist"][0]
    assert aapl | {"added_at": "t"} == {
        "ticker": "AAPL",
        "price": 190.12,
        "previous_price": 190.05,
        "open_price": 189.50,
        "change_pct": 0.33,
        "added_at": "t",
    }


def test_unpriced_ticker_has_null_prices(api: TestClient) -> None:
    api.app.state.price_cache.remove("NFLX")
    nflx = api.get("/api/watchlist").json()["watchlist"][-1]
    assert nflx["ticker"] == "NFLX"
    assert [nflx[k] for k in ("price", "previous_price", "open_price", "change_pct")] == [None] * 4


def test_add_ticker_is_normalized_appended_and_priced(api: TestClient) -> None:
    response = api.post("/api/watchlist", json={"ticker": " pypl "})
    assert response.status_code == 200
    body = response.json()
    assert _tickers(body) == [*DEFAULT_TICKERS, "PYPL"]
    pypl = body["watchlist"][-1]
    assert pypl["price"] == pypl["previous_price"] == pypl["open_price"]
    assert pypl["change_pct"] == 0.0
    assert "PYPL" in api.app.state.market_source.tickers


def test_add_existing_is_idempotent(api: TestClient) -> None:
    before = api.get("/api/watchlist").json()
    response = api.post("/api/watchlist", json={"ticker": "aapl"})
    assert response.status_code == 200
    assert response.json() == before


def test_remove_ticker_stops_pricing_it(api: TestClient) -> None:
    response = api.delete("/api/watchlist/nflx")
    assert response.status_code == 200
    assert "NFLX" not in _tickers(response.json())
    assert "NFLX" not in api.app.state.market_source.tickers
    assert api.app.state.price_cache.get("NFLX") is None


def test_remove_absent_is_idempotent(api: TestClient) -> None:
    before = api.get("/api/watchlist").json()
    response = api.delete("/api/watchlist/PYPL")
    assert response.status_code == 200
    assert response.json() == before


def test_removing_held_ticker_keeps_it_priced(api: TestClient) -> None:
    trade = {"ticker": "AAPL", "quantity": 1, "side": "buy"}
    assert api.post("/api/portfolio/trade", json=trade).status_code == 200
    response = api.delete("/api/watchlist/AAPL")
    assert "AAPL" not in _tickers(response.json())
    assert "AAPL" in api.app.state.market_source.tickers
    assert api.app.state.price_cache.get("AAPL") is not None


def test_add_then_buy_new_ticker(api: TestClient) -> None:
    api.post("/api/watchlist", json={"ticker": "PYPL"})
    trade = api.post("/api/portfolio/trade", json={"ticker": "PYPL", "quantity": 1, "side": "buy"})
    assert trade.status_code == 200


@pytest.mark.parametrize("ticker", ["BRK.B", "TOOLONG", "A1", "", "   "])
def test_add_invalid_ticker(api: TestClient, ticker: str) -> None:
    response = api.post("/api/watchlist", json={"ticker": ticker})
    assert response.status_code == 400
    assert response.json() == INVALID


@pytest.mark.parametrize("ticker", ["BRK.B", "TOOLONG", "A1"])
def test_remove_invalid_ticker(api: TestClient, ticker: str) -> None:
    response = api.delete(f"/api/watchlist/{ticker}")
    assert response.status_code == 400
    assert response.json() == INVALID


@pytest.mark.parametrize("body", [{}, {"ticker": 5}, {"symbol": "AAPL"}, {"ticker": None}])
def test_add_malformed_body(api: TestClient, body: dict) -> None:
    response = api.post("/api/watchlist", json=body)
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid request: ticker: ")
