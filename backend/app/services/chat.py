"""LLM chat (PLAN.md §9, API_CONTRACT.md §Chat, §LLM structured output, §LLM mock mode).

One LLM call per message (S7). The structured response is parsed (retry once
on a parse failure, then 502 — R26); watchlist changes run before trades (R25)
through the same service functions as the REST routes; each action's result is
returned and stored with the assistant message (R22, R23).
"""

import asyncio
import json
import math
import re
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings
from app.errors import BadRequest
from app.market import MarketDataSource, PriceCache
from app.services.portfolio import load_portfolio
from app.services.rounding import round2, round4
from app.services.trading import TradeError, execute_trade
from app.services.watchlist import add_to_watchlist, get_watchlist, remove_from_watchlist
from app.storage import DEFAULT_USER_ID, Database, new_id
from app.timeutil import utc_now_iso

MODEL = "openrouter/openai/gpt-oss-120b"
PROVIDER_ROUTING = {"provider": {"order": ["cerebras"]}}
LLM_TIMEOUT_SECONDS = 30.0
HISTORY_CONTEXT_MESSAGES = 20
MAX_MESSAGE_LENGTH = 2000
NOT_CONFIGURED = "LLM not configured: set OPENROUTER_API_KEY or LLM_MOCK=true"

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "trades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "quantity": {"type": "number"},
                },
                "required": ["ticker", "side", "quantity"],
                "additionalProperties": False,
            },
        },
        "watchlist_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "remove"]},
                },
                "required": ["ticker", "action"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["message", "trades", "watchlist_changes"],
    "additionalProperties": False,
}
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "finally_response", "strict": True, "schema": RESPONSE_SCHEMA},
}

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation.
- Analyze portfolio composition, risk concentration and P&L.
- Suggest trades with reasoning; execute trades when the user asks or agrees.
- Manage the watchlist proactively.
- Be concise and data-driven.
- Describe trades as intent ("Placing an order for 10 AAPL"), never in the past tense:
  results are only known after execution and are reported to the user separately.
- When the user gives a dollar amount, use a fractional quantity: dollars / price,
  rounded down to 4 decimal places.
- Earlier assistant turns include the results of their actions; acknowledge failures.
- Always respond with JSON matching the schema; use empty arrays when there are no actions."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LLMTrade(_Strict):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class LLMWatchlistChange(_Strict):
    ticker: str
    action: Literal["add", "remove"]


class LLMResponse(_Strict):
    message: str
    trades: list[LLMTrade]
    watchlist_changes: list[LLMWatchlistChange]


class ParseError(Exception):
    """The model's output is not valid JSON or doesn't match the schema."""


def parse_response(content: str | None) -> LLMResponse:
    if not content:
        raise ParseError("empty response")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg}") from None
    try:
        # Python-mode validation so JSON integers are accepted as numbers.
        return LLMResponse.model_validate(data, strict=False)
    except ValidationError as exc:
        raise ParseError(f"schema mismatch: {exc.errors()[0]['msg']}") from None


# --- Mock mode (R27) ---------------------------------------------------------

_ADD_RE = re.compile(r"\badd\s+([A-Za-z]{1,5})\b", re.IGNORECASE)
_REMOVE_RE = re.compile(r"\bremove\s+([A-Za-z]{1,5})\b", re.IGNORECASE)
_BUY_RE = re.compile(r"\bbuy\b", re.IGNORECASE)
_SELL_RE = re.compile(r"\bsell\b", re.IGNORECASE)
MOCK_NO_ACTIONS = (
    'This is a mock response from FinAlly. Try "buy", "sell", "add XYZ" or "remove XYZ".'
)


def mock_response(message: str) -> LLMResponse:
    adds = [m.group(1).upper() for m in _ADD_RE.finditer(message)]
    removes = [m.group(1).upper() for m in _REMOVE_RE.finditer(message)]
    sides = [s for s, rx in (("buy", _BUY_RE), ("sell", _SELL_RE)) if rx.search(message)]
    phrases = [f"adding {t} to your watchlist" for t in adds]
    phrases += [f"removing {t} from your watchlist" for t in removes]
    phrases += [f"placing a {side} order for 1 AAPL" for side in sides]
    return LLMResponse(
        message=f"Mock response: {'; '.join(phrases)}." if phrases else MOCK_NO_ACTIONS,
        watchlist_changes=[LLMWatchlistChange(ticker=t, action="add") for t in adds]
        + [LLMWatchlistChange(ticker=t, action="remove") for t in removes],
        trades=[LLMTrade(ticker="AAPL", side=side, quantity=1) for side in sides],
    )


# --- Real LLM call ------------------------------------------------------------


async def _complete(messages: list[dict[str, str]], api_key: str) -> str | None:
    import litellm  # imported lazily: heavy, and unused in mock mode

    response = await litellm.acompletion(
        model=MODEL,
        messages=messages,
        response_format=RESPONSE_FORMAT,
        extra_body=PROVIDER_ROUTING,
        api_key=api_key,
        timeout=LLM_TIMEOUT_SECONDS,
    )
    return response.choices[0].message.content


async def call_llm(messages: list[dict[str, str]], api_key: str) -> LLMResponse:
    """One call, retried once on a parse failure; any failure becomes ``502`` (R26)."""
    reason = "unknown error"
    for _ in range(2):
        try:
            content = await asyncio.wait_for(
                _complete(messages, api_key), timeout=LLM_TIMEOUT_SECONDS
            )
        except TimeoutError:
            reason = "timeout"
            break
        except Exception as exc:  # provider/network errors are not retried
            reason = type(exc).__name__
            break
        try:
            return parse_response(content)
        except ParseError as exc:
            reason = f"invalid structured output ({exc})"
    raise HTTPException(status_code=502, detail=f"LLM request failed: {reason}")


# --- Context, storage, execution ---------------------------------------------


def build_context(db: Database, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> str:
    portfolio = load_portfolio(db, cache, user_id).to_wire()
    watchlist = [
        {k: item[k] for k in ("ticker", "price", "change_pct")}
        for item in get_watchlist(db, cache, user_id)
    ]
    return "Current portfolio and watchlist (JSON):\n" + json.dumps(
        {"portfolio": portfolio, "watchlist": watchlist}
    )


def store_message(
    db: Database,
    role: str,
    content: str,
    actions: dict[str, Any] | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                new_id(),
                user_id,
                role,
                content,
                None if actions is None else json.dumps(actions),
                utc_now_iso(),
            ),
        )


def get_chat_history(
    db: Database, limit: int = HISTORY_CONTEXT_MESSAGES, user_id: str = DEFAULT_USER_ID
) -> list[dict[str, Any]]:
    """The most recent ``limit`` messages in ascending ``created_at`` order."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, actions, created_at FROM (
                SELECT *, rowid AS rid FROM chat_messages WHERE user_id = ?
                 ORDER BY created_at DESC, rowid DESC LIMIT ?
            ) ORDER BY created_at, rid
            """,
            (user_id, limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "actions": None if row["actions"] is None else json.loads(row["actions"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _history_for_llm(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages = []
    for item in history:
        content = item["content"]
        if item["actions"] is not None:
            content += "\n[Action results: " + json.dumps(item["actions"]) + "]"
        messages.append({"role": item["role"], "content": content})
    return messages


async def execute_actions(
    response: LLMResponse,
    db: Database,
    cache: PriceCache,
    source: MarketDataSource,
    lock: asyncio.Lock,
) -> dict[str, list[dict[str, Any]]]:
    """Watchlist changes first, then trades, each in array order (R25). Failures don't stop."""
    changes = []
    for change in response.watchlist_changes:
        apply = add_to_watchlist if change.action == "add" else remove_from_watchlist
        result = {"ticker": change.ticker.strip().upper(), "action": change.action}
        try:
            result["ticker"] = apply(db, source, change.ticker)
            changes.append(result | {"status": "ok", "error": None})
        except BadRequest as exc:
            changes.append(result | {"status": "failed", "error": exc.detail})

    trades = []
    for trade in response.trades:
        quantity = round4(trade.quantity) if math.isfinite(trade.quantity) else trade.quantity
        result = {"ticker": trade.ticker.strip().upper(), "side": trade.side, "quantity": quantity}
        try:
            executed = await execute_trade(
                db, cache, source, lock, trade.ticker, trade.quantity, trade.side
            )
            trades.append(
                result
                | {
                    "ticker": executed.ticker,
                    "quantity": round4(executed.quantity),
                    "price": round2(executed.price),
                    "status": "ok",
                    "error": None,
                }
            )
        except TradeError as exc:
            price = None if exc.price is None else round2(exc.price)
            trades.append(result | {"price": price, "status": "failed", "error": exc.detail})
    return {"watchlist_changes": changes, "trades": trades}


def validate_message(raw: str) -> str:
    message = raw.strip()
    if not message:
        raise BadRequest("Message must not be empty")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise BadRequest(f"Message must be at most {MAX_MESSAGE_LENGTH} characters")
    return message


async def handle_chat(
    raw_message: str,
    settings: Settings,
    db: Database,
    cache: PriceCache,
    source: MarketDataSource,
    lock: asyncio.Lock,
) -> dict[str, Any]:
    """The ``POST /api/chat`` flow (PLAN.md §9 steps 1–10)."""
    message = validate_message(raw_message)
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)

    store_message(db, "user", message)
    if settings.llm_mock:
        response = mock_response(message)
    else:
        prompt = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": build_context(db, cache)},
            *_history_for_llm(get_chat_history(db, HISTORY_CONTEXT_MESSAGES)),
        ]
        response = await call_llm(prompt, settings.openrouter_api_key or "")

    actions = await execute_actions(response, db, cache, source, lock)
    store_message(db, "assistant", response.message, actions)
    return {"message": response.message, "actions": actions}
