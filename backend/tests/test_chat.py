import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.chat as chat_service
from app.config import Settings
from app.main import create_app
from app.services.chat import MOCK_NO_ACTIONS, ParseError, mock_response, parse_response

NOT_CONFIGURED = {"detail": "LLM not configured: set OPENROUTER_API_KEY or LLM_MOCK=true"}


@pytest.fixture
def api(client: TestClient) -> Iterator[TestClient]:
    """Mock-mode client with the simulator stopped and AAPL pinned at $100."""
    client.portal.call(client.app.state.market_source.stop)
    client.app.state.price_cache.update("AAPL", 100.0, open_price=100.0)
    yield client


def _llm_client(tmp_path: Path, **overrides) -> TestClient:
    settings = Settings(
        db_path=tmp_path / "llm" / "finally.db", static_dir=tmp_path / "no-static", **overrides
    )
    return TestClient(create_app(settings))


@pytest.fixture
def llm(tmp_path: Path) -> Iterator[TestClient]:
    """Real-LLM-path client (key set, mock off); tests replace ``_complete``."""
    with _llm_client(tmp_path, openrouter_api_key="test-key") as client:
        client.portal.call(client.app.state.market_source.stop)
        client.app.state.price_cache.update("AAPL", 100.0, open_price=100.0)
        yield client


def _fake_llm(monkeypatch: pytest.MonkeyPatch, outputs: list) -> list[list[dict]]:
    """Make ``_complete`` return (or raise) ``outputs`` in order; returns the prompts sent."""
    calls: list[list[dict]] = []
    remaining = list(outputs)

    async def fake(messages, api_key):
        calls.append(messages)
        out = remaining.pop(0)
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out)

    monkeypatch.setattr(chat_service, "_complete", fake)
    return calls


def _history(client: TestClient) -> list[dict]:
    return client.get("/api/chat/history").json()["messages"]


# --- parse_response ----------------------------------------------------------


def test_parse_valid_response() -> None:
    parsed = parse_response(
        json.dumps(
            {
                "message": "Placing an order",
                "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
                "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
            }
        )
    )
    assert parsed.message == "Placing an order"
    assert parsed.trades[0].quantity == 10.0
    assert parsed.watchlist_changes[0].action == "add"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "",
        "not json",
        '{"message": "hi", "trades": []}',
        '{"message": "hi", "watchlist_changes": []}',
        '{"trades": [], "watchlist_changes": []}',
        '{"message": 5, "trades": [], "watchlist_changes": []}',
        '{"message": "hi", "trades": [{"ticker": "AAPL", "side": "hold", "quantity": 1}],'
        ' "watchlist_changes": []}',
        '{"message": "hi", "trades": [{"ticker": "AAPL", "side": "buy"}], "watchlist_changes": []}',
        '{"message": "hi", "trades": [], "watchlist_changes": [{"ticker": "X", "action": "x"}]}',
        '{"message": "hi", "trades": [], "watchlist_changes": [], "extra": 1}',
        '["message"]',
    ],
)
def test_parse_failures(content: str | None) -> None:
    with pytest.raises(ParseError):
        parse_response(content)


def test_business_invalid_values_are_not_parse_failures() -> None:
    parsed = parse_response(
        '{"message": "x", "trades": [{"ticker": "BRK.B", "side": "buy", "quantity": -1}],'
        ' "watchlist_changes": []}'
    )
    assert parsed.trades[0].ticker == "BRK.B"


# --- mock rules ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "changes", "trades", "reply"),
    [
        ("hello", [], [], MOCK_NO_ACTIONS),
        ("buy", [], [("AAPL", "buy")], "Mock response: placing a buy order for 1 AAPL."),
        ("please sell", [], [("AAPL", "sell")], "Mock response: placing a sell order for 1 AAPL."),
        ("add PYPL", [("PYPL", "add")], [], "Mock response: adding PYPL to your watchlist."),
        (
            "Add pypl and buy",
            [("PYPL", "add")],
            [("AAPL", "buy")],
            "Mock response: adding PYPL to your watchlist; placing a buy order for 1 AAPL.",
        ),
        (
            "remove NFLX",
            [("NFLX", "remove")],
            [],
            "Mock response: removing NFLX from your watchlist.",
        ),
        (
            "remove TSLA, add uber, SELL and buy, add f",
            [("UBER", "add"), ("F", "add"), ("TSLA", "remove")],
            [("AAPL", "buy"), ("AAPL", "sell")],
            "Mock response: adding UBER to your watchlist; adding F to your watchlist;"
            " removing TSLA from your watchlist; placing a buy order for 1 AAPL;"
            " placing a sell order for 1 AAPL.",
        ),
        ("buyer seller adder", [], [], MOCK_NO_ACTIONS),
        ("add TOOLONG", [], [], MOCK_NO_ACTIONS),
    ],
)
def test_mock_rules(message: str, changes: list, trades: list, reply: str) -> None:
    response = mock_response(message)
    assert response.message == reply
    assert [(c.ticker, c.action) for c in response.watchlist_changes] == changes
    assert [(t.ticker, t.side) for t in response.trades] == trades
    assert all(t.quantity == 1 for t in response.trades)


# --- POST /api/chat (mock mode) ----------------------------------------------------


def test_chat_executes_actions_and_stores_them(api: TestClient) -> None:
    response = api.post("/api/chat", json={"message": "Add pypl and buy"})
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "message": "Mock response: adding PYPL to your watchlist; placing a buy order for 1 AAPL.",
        "actions": {
            "watchlist_changes": [
                {"ticker": "PYPL", "action": "add", "status": "ok", "error": None}
            ],
            "trades": [
                {
                    "ticker": "AAPL",
                    "side": "buy",
                    "quantity": 1.0,
                    "price": 100.0,
                    "status": "ok",
                    "error": None,
                }
            ],
        },
    }
    assert "PYPL" in [w["ticker"] for w in api.get("/api/watchlist").json()["watchlist"]]
    assert api.get("/api/portfolio").json()["cash_balance"] == 9900.0

    user, assistant = _history(api)
    assert (user["role"], user["content"], user["actions"]) == ("user", "Add pypl and buy", None)
    assert assistant["role"] == "assistant"
    assert assistant["content"] == body["message"]
    assert assistant["actions"] == body["actions"]


def test_no_actions_reply(api: TestClient) -> None:
    body = api.post("/api/chat", json={"message": "  hello  "}).json()
    assert body == {"message": MOCK_NO_ACTIONS, "actions": {"watchlist_changes": [], "trades": []}}
    assert _history(api)[0]["content"] == "hello"


def test_failed_trade_is_reported_not_raised(api: TestClient) -> None:
    body = api.post("/api/chat", json={"message": "sell"}).json()
    assert body["actions"]["trades"] == [
        {
            "ticker": "AAPL",
            "side": "sell",
            "quantity": 1.0,
            "price": 100.0,
            "status": "failed",
            "error": "Insufficient shares: requested 1, held 0",
        }
    ]
    assert _history(api)[1]["actions"] == body["actions"]


def test_buy_then_sell_in_one_message(api: TestClient) -> None:
    trades = api.post("/api/chat", json={"message": "buy and sell"}).json()["actions"]["trades"]
    assert [(t["side"], t["status"]) for t in trades] == [("buy", "ok"), ("sell", "ok")]
    assert api.get("/api/portfolio").json()["positions"] == []


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"message": "   "}, "Message must not be empty"),
        ({"message": "x" * 2001}, "Message must be at most 2000 characters"),
    ],
)
def test_message_validation(api: TestClient, body: dict, detail: str) -> None:
    response = api.post("/api/chat", json=body)
    assert response.status_code == 400
    assert response.json() == {"detail": detail}
    assert _history(api) == []


@pytest.mark.parametrize("body", [{}, {"message": 5}])
def test_malformed_body(api: TestClient, body: dict) -> None:
    response = api.post("/api/chat", json=body)
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid request: message:")


def test_max_length_message_is_accepted(api: TestClient) -> None:
    assert api.post("/api/chat", json={"message": "x" * 2000}).status_code == 200


def test_not_configured_returns_503_and_stores_nothing(tmp_path: Path) -> None:
    with _llm_client(tmp_path) as client:
        response = client.post("/api/chat", json={"message": "hi"})
        assert response.status_code == 503
        assert response.json() == NOT_CONFIGURED
        assert _history(client) == []
        # The rest of the app still works (R3).
        assert client.get("/api/portfolio").status_code == 200


# --- POST /api/chat (LLM path, faked) -------------------------------------------------


def test_llm_watchlist_changes_run_before_trades(
    llm: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The trade is listed first but needs the watchlist add to price PYPL.
    _fake_llm(
        monkeypatch,
        [
            {
                "message": "Adding PYPL and placing an order for 2 PYPL.",
                "trades": [{"ticker": "pypl", "side": "buy", "quantity": 2}],
                "watchlist_changes": [{"ticker": "pypl", "action": "add"}],
            }
        ],
    )
    actions = llm.post("/api/chat", json={"message": "buy PYPL"}).json()["actions"]
    assert actions["watchlist_changes"] == [
        {"ticker": "PYPL", "action": "add", "status": "ok", "error": None}
    ]
    [trade] = actions["trades"]
    assert (trade["ticker"], trade["status"], trade["error"]) == ("PYPL", "ok", None)
    assert trade["price"] > 0


def test_llm_partial_failures_do_not_stop_other_actions(
    llm: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm.app.state.price_cache.remove("MSFT")
    _fake_llm(
        monkeypatch,
        [
            {
                "message": "Several orders",
                "trades": [
                    {"ticker": "BRK.B", "side": "buy", "quantity": 1},
                    {"ticker": "AAPL", "side": "buy", "quantity": 0.00001},
                    {"ticker": "MSFT", "side": "buy", "quantity": 1},
                    {"ticker": "AAPL", "side": "buy", "quantity": 1000},
                    {"ticker": "AAPL", "side": "buy", "quantity": 2.123456},
                ],
                "watchlist_changes": [
                    {"ticker": "TOOLONG", "action": "add"},
                    {"ticker": "aapl", "action": "add"},
                    {"ticker": "zzzz", "action": "remove"},
                ],
            }
        ],
    )
    actions = llm.post("/api/chat", json={"message": "go"}).json()["actions"]
    assert [(c["ticker"], c["status"], c["error"]) for c in actions["watchlist_changes"]] == [
        ("TOOLONG", "failed", "Invalid ticker: must be 1-5 letters A-Z"),
        ("AAPL", "ok", None),
        ("ZZZZ", "ok", None),
    ]
    assert [
        (t["ticker"], t["quantity"], t["price"], t["status"], t["error"]) for t in actions["trades"]
    ] == [
        ("BRK.B", 1.0, None, "failed", "Invalid ticker: must be 1-5 letters A-Z"),
        ("AAPL", 0.0, 100.0, "failed", "Quantity must be greater than 0"),
        ("MSFT", 1.0, None, "failed", "No price available for MSFT"),
        ("AAPL", 1000.0, 100.0, "failed", "Insufficient cash: need $100000.00, have $10000.00"),
        ("AAPL", 2.1235, 100.0, "ok", None),
    ]


def test_llm_prompt_includes_context_history_and_results(
    llm: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_llm(
        monkeypatch,
        [
            {
                "message": "Placing a sell order",
                "trades": [{"ticker": "AAPL", "side": "sell", "quantity": 1}],
                "watchlist_changes": [],
            },
            {"message": "Sorry about that", "trades": [], "watchlist_changes": []},
        ],
    )
    llm.post("/api/chat", json={"message": "sell AAPL"})
    llm.post("/api/chat", json={"message": "what happened?"})

    prompt = calls[1]
    assert prompt[0]["role"] == "system" and "FinAlly" in prompt[0]["content"]
    assert '"cash_balance": 10000.0' in prompt[1]["content"]
    assert '"ticker": "AAPL"' in prompt[1]["content"]
    assert [m["role"] for m in prompt[2:]] == ["user", "assistant", "user"]
    assert "Insufficient shares" in prompt[3]["content"]
    assert prompt[4]["content"] == "what happened?"


def test_llm_history_context_is_last_20_messages(
    llm: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reply = {"message": "ok", "trades": [], "watchlist_changes": []}
    calls = _fake_llm(monkeypatch, [reply] * 12)
    for i in range(12):
        llm.post("/api/chat", json={"message": f"msg {i}"})
    history = calls[-1][2:]
    assert len(history) == 20
    assert history[-1]["content"] == "msg 11"
    assert history[0]["role"] == "assistant"
    assert history[1]["content"] == "msg 2"


def test_llm_malformed_output_is_retried_once(
    llm: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_llm(
        monkeypatch,
        ["not json", {"message": "Second try", "trades": [], "watchlist_changes": []}],
    )
    response = llm.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 200
    assert response.json()["message"] == "Second try"
    assert len(calls) == 2


def test_llm_malformed_twice_returns_502_and_executes_nothing(
    llm: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_llm(monkeypatch, ['{"message": "x"}', "nope"])
    response = llm.post("/api/chat", json={"message": "buy AAPL"})
    assert response.status_code == 502
    assert response.json()["detail"].startswith("LLM request failed:")
    assert len(calls) == 2
    # The user message stays stored; no assistant message (R26).
    assert [(m["role"], m["content"]) for m in _history(llm)] == [("user", "buy AAPL")]
    assert llm.get("/api/portfolio").json()["cash_balance"] == 10000.0


def test_llm_provider_error_returns_502_without_retry(
    llm: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_llm(monkeypatch, [RuntimeError("boom")])
    response = llm.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 502
    assert response.json() == {"detail": "LLM request failed: RuntimeError"}
    assert len(calls) == 1


def test_llm_timeout_returns_502(llm: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_llm(monkeypatch, [TimeoutError()])
    response = llm.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 502
    assert response.json() == {"detail": "LLM request failed: timeout"}


def test_llm_request_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_complete`` passes the contract's model, schema and Cerebras routing to LiteLLM."""
    import asyncio

    import litellm

    captured: dict = {}

    class _Msg:
        content = '{"message": "hi", "trades": [], "watchlist_changes": []}'

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _Resp()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    parsed = asyncio.run(chat_service.call_llm([{"role": "user", "content": "x"}], "k"))
    assert parsed.message == "hi"
    assert captured["model"] == "openrouter/openai/gpt-oss-120b"
    assert captured["extra_body"] == {"provider": {"order": ["cerebras"]}}
    assert captured["api_key"] == "k"
    fmt = captured["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "finally_response"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["required"] == ["message", "trades", "watchlist_changes"]


# --- GET /api/chat/history ----------------------------------------------------------


def test_history_empty_on_fresh_database(api: TestClient) -> None:
    assert api.get("/api/chat/history").json() == {"messages": []}


def test_history_limit_returns_most_recent_ascending(api: TestClient) -> None:
    for i in range(3):
        api.post("/api/chat", json={"message": f"hello {i}"})
    messages = api.get("/api/chat/history", params={"limit": 3}).json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("assistant", MOCK_NO_ACTIONS),
        ("user", "hello 2"),
        ("assistant", MOCK_NO_ACTIONS),
    ]
    assert [m["created_at"] for m in messages] == sorted(m["created_at"] for m in messages)
    assert set(messages[0]) == {"id", "role", "content", "actions", "created_at"}


def test_history_default_limit_is_20(api: TestClient) -> None:
    for i in range(11):
        api.post("/api/chat", json={"message": f"hello {i}"})
    assert len(_history(api)) == 20


@pytest.mark.parametrize("limit", ["0", "101", "abc", "-1"])
def test_history_limit_out_of_range(api: TestClient, limit: str) -> None:
    response = api.get("/api/chat/history", params={"limit": limit})
    assert response.status_code == 400
    assert response.json() == {"detail": "limit must be an integer between 1 and 100"}
