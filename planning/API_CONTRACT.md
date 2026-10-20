# FinAlly — API Contract

Authoritative wire formats for every endpoint, the SSE stream, errors, the LLM structured-output schema and LLM mock mode. Frontend and backend build against this file in parallel. Design rationale lives in [`PLAN.md`](PLAN.md); if the two disagree on a wire format, this file wins — fix the other in the same change.

## Conventions

- **Keys**: snake_case everywhere.
- **Timestamps**: ISO-8601 UTC with milliseconds and `Z`, e.g. `"2026-10-18T14:03:12.500Z"`.
- **Rounding in responses**: money and prices 2 dp; quantities 4 dp; percentages are percentage points, 2 dp (`0.33` = 0.33%).
- **Status codes**: every successful call returns `200`. No `201`/`204`.
- **Content type**: `application/json` for all REST endpoints; `text/event-stream` for SSE.
- **Errors**: `{"detail": "<string>"}` — `detail` is always a string, never a list (see [Errors](#errors)).
- **Base URL**: same origin in production. In dev the frontend prefixes `NEXT_PUBLIC_API_BASE` (e.g. `http://localhost:8000`).
- **Collections** are wrapped in an object with a named array (`{"watchlist": [...]}`), never a bare array.

### Ticker format

```
^[A-Z]{1,5}$
```

Every ticker in any request (body or path) is **trimmed and uppercased first**, then validated against the regex. `" pypl "` → `"PYPL"` (valid). `"BRK.B"`, `"TOOLONG"`, `"A1"`, `""` → `400`.

---

## System

### `GET /api/health`

`200`
```json
{"status": "ok"}
```

---

## Market data

### `GET /api/stream/prices` (SSE)

Response headers:
```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

- One event per tick (~500 ms) containing **all** currently priced tickers (watchlist ∪ open positions).
- The first event is sent **immediately** on connect, preceded by `retry: 2000`.
- Default (unnamed) event — the client listens with `EventSource.onmessage`.
- `data` is a JSON object keyed by ticker. No `direction` field: up/down = `price` vs `previous_price`.
- A ticker with no cached price (Massive, invalid symbol) is simply absent. If nothing is priced, `data: {}`.

Wire example (first event after connect; events are separated by a blank line):
```
retry: 2000
data: {"AAPL": {"price": 190.12, "previous_price": 190.05, "open_price": 189.50, "timestamp": "2026-10-18T14:03:12.500Z"}, "GOOGL": {"price": 175.31, "previous_price": 175.40, "open_price": 175.00, "timestamp": "2026-10-18T14:03:12.500Z"}}

data: {"AAPL": {"price": 190.20, "previous_price": 190.12, "open_price": 189.50, "timestamp": "2026-10-18T14:03:13.000Z"}, "GOOGL": {"price": 175.29, "previous_price": 175.31, "open_price": 175.00, "timestamp": "2026-10-18T14:03:13.000Z"}}

```

Per-ticker object:

| Field | Type | Meaning |
|---|---|---|
| `price` | number | Latest price |
| `previous_price` | number | Price at the prior tick (equals `price` on a ticker's first tick) |
| `open_price` | number | Reference for daily change % (simulator: price when the ticker entered the cache; Massive: previous close) |
| `timestamp` | string | When `price` was set (UTC) |

TypeScript shape:
```ts
type PriceUpdate = { price: number; previous_price: number; open_price: number; timestamp: string };
type PriceEvent = Record<string, PriceUpdate>;
```

---

## Watchlist

### Watchlist item

| Field | Type | Notes |
|---|---|---|
| `ticker` | string | |
| `price` | number \| null | `null` when no cached price |
| `previous_price` | number \| null | |
| `open_price` | number \| null | |
| `change_pct` | number \| null | Daily change % (see [formulas](#metric-formulas)) |
| `added_at` | string | |

Items are ordered by `added_at` ascending (seed order for the defaults).

### `GET /api/watchlist`

`200`
```json
{
  "watchlist": [
    {"ticker": "AAPL", "price": 190.12, "previous_price": 190.05, "open_price": 189.50, "change_pct": 0.33, "added_at": "2026-10-18T14:00:00.000Z"},
    {"ticker": "GOOGL", "price": 175.31, "previous_price": 175.40, "open_price": 175.00, "change_pct": 0.18, "added_at": "2026-10-18T14:00:00.000Z"}
  ]
}
```
(Fresh database: the 10 default tickers AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX.)

### `POST /api/watchlist`

Request:
```json
{"ticker": "pypl"}
```

`200` — the full updated watchlist, same shape as `GET`. With the simulator, the new ticker is priced immediately; with Massive, its price fields are `null` until the next poll.
```json
{
  "watchlist": [
    {"ticker": "AAPL", "price": 190.12, "previous_price": 190.05, "open_price": 189.50, "change_pct": 0.33, "added_at": "2026-10-18T14:00:00.000Z"},
    {"ticker": "PYPL", "price": 72.40, "previous_price": 72.40, "open_price": 72.40, "change_pct": 0.00, "added_at": "2026-10-18T14:05:41.250Z"}
  ]
}
```

- Already on the watchlist → `200`, unchanged list (idempotent).
- Invalid ticker → `400 {"detail": "Invalid ticker: must be 1-5 letters A-Z"}`.

### `DELETE /api/watchlist/{ticker}`

`DELETE /api/watchlist/pypl` → `200`, the full updated watchlist (same shape as `GET`).

- Not on the watchlist → `200`, unchanged list (idempotent).
- Invalid ticker → `400 {"detail": "Invalid ticker: must be 1-5 letters A-Z"}`.
- If the user holds a position in the ticker, it leaves the watchlist but **stays priced** (still in SSE, still valued).

---

## Portfolio

### Portfolio object

| Field | Type | Notes |
|---|---|---|
| `cash_balance` | number | 2 dp |
| `positions` | Position[] | Ordered by `ticker` ascending; empty array when none |
| `positions_value` | number | Σ `market_value` |
| `total_value` | number | `cash_balance + positions_value` |
| `total_pnl` | number | `total_value − 10000` |
| `total_pnl_pct` | number | `total_pnl / 10000 × 100` |

Position:

| Field | Type | Notes |
|---|---|---|
| `ticker` | string | |
| `quantity` | number | 4 dp |
| `avg_cost` | number | 2 dp |
| `current_price` | number | Cached price at request time; falls back to `avg_cost` if none |
| `market_value` | number | `quantity × current_price` |
| `unrealized_pnl` | number | `(current_price − avg_cost) × quantity` |
| `pnl_pct` | number | `(current_price − avg_cost) / avg_cost × 100` |

The valuation fields are a **point-in-time snapshot**. The frontend recomputes them live from SSE prices with the same formulas; the authoritative inputs are `cash_balance`, `quantity` and `avg_cost`.

### `GET /api/portfolio`

`200`
```json
{
  "cash_balance": 8099.40,
  "positions": [
    {"ticker": "AAPL", "quantity": 10.0, "avg_cost": 190.06, "current_price": 191.20, "market_value": 1912.00, "unrealized_pnl": 11.40, "pnl_pct": 0.60}
  ],
  "positions_value": 1912.00,
  "total_value": 10011.40,
  "total_pnl": 11.40,
  "total_pnl_pct": 0.11
}
```

Fresh database:
```json
{"cash_balance": 10000.00, "positions": [], "positions_value": 0.00, "total_value": 10000.00, "total_pnl": 0.00, "total_pnl_pct": 0.00}
```

### `POST /api/portfolio/trade`

Request (`quantity` may be fractional; `ticker` and `side` are case-insensitive):
```json
{"ticker": "AAPL", "quantity": 10, "side": "buy"}
```

`200` — the executed trade **and** the updated portfolio:
```json
{
  "trade": {
    "id": "6f1c2a9e-3b7d-4e1a-9c55-2d8f0b7a4e11",
    "ticker": "AAPL",
    "side": "buy",
    "quantity": 10.0,
    "price": 190.06,
    "total": 1900.60,
    "executed_at": "2026-10-18T14:04:02.000Z"
  },
  "portfolio": {
    "cash_balance": 8099.40,
    "positions": [
      {"ticker": "AAPL", "quantity": 10.0, "avg_cost": 190.06, "current_price": 190.06, "market_value": 1900.60, "unrealized_pnl": 0.00, "pnl_pct": 0.00}
    ],
    "positions_value": 1900.60,
    "total_value": 10000.00,
    "total_pnl": 0.00,
    "total_pnl_pct": 0.00
  }
}
```

`trade.total` = `quantity × price`, 2 dp. A successful trade also records a portfolio snapshot.

Validation, applied in this order (first failure wins):

| Condition | Status | `detail` |
|---|---|---|
| Body missing a field / wrong JSON type | 400 | `Invalid request: <field>: <reason>` |
| Ticker fails the regex (after trim + uppercase) | 400 | `Invalid ticker: must be 1-5 letters A-Z` |
| `side` not `buy`/`sell` (case-insensitive) | 400 | `Side must be 'buy' or 'sell'` |
| `quantity` ≤ 0 after rounding to 4 dp | 400 | `Quantity must be greater than 0` |
| No cached price for ticker | 400 | `No price available for AAPL` |
| Buy: `round(quantity × price, 2)` > cash | 400 | `Insufficient cash: need $1900.60, have $500.00` |
| Sell: `quantity` > held quantity (no position = 0 held) | 400 | `Insufficient shares: requested 5, held 2.5` |

The backend validates `ticker`, `side` and `quantity` values itself (accepting them as string/string/number) so these exact strings are produced; only missing fields and wrong JSON types go through the generic `Invalid request:` path. Quantities in messages print with trailing zeros stripped. **Tests match on the text before the first colon** (`Insufficient cash`, `Insufficient shares`, `Invalid ticker`, …) or the full string where there is no colon.

### `GET /api/portfolio/history`

Query: `limit` (optional, integer 1–10000, default 1000). Returns the **most recent** `limit` snapshots in **ascending** `recorded_at` order.

`GET /api/portfolio/history?limit=3` → `200`
```json
{
  "snapshots": [
    {"total_value": 10000.00, "recorded_at": "2026-10-18T14:00:00.000Z"},
    {"total_value": 10000.00, "recorded_at": "2026-10-18T14:04:02.000Z"},
    {"total_value": 10011.40, "recorded_at": "2026-10-18T14:04:30.000Z"}
  ]
}
```

A fresh database already has one snapshot (`10000.00`, recorded at DB creation).

- `limit` out of range or not an integer → `400 {"detail": "limit must be an integer between 1 and 10000"}`.

---

## Chat

### Actions object

Returned by `POST /api/chat`, stored verbatim (as JSON text) in `chat_messages.actions`, and returned again by `GET /api/chat/history`. Both arrays are always present (may be empty).

```json
{
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add", "status": "ok", "error": null}
  ],
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 190.12, "status": "failed", "error": "Insufficient cash: need $1901.20, have $500.00"}
  ]
}
```

Watchlist change result:

| Field | Type | Notes |
|---|---|---|
| `ticker` | string | Normalized (uppercased) |
| `action` | `"add"` \| `"remove"` | |
| `status` | `"ok"` \| `"failed"` | Idempotent no-ops (add existing / remove absent) are `"ok"` |
| `error` | string \| null | Same strings as the REST endpoints; `null` when ok |

Trade result:

| Field | Type | Notes |
|---|---|---|
| `ticker` | string | Normalized |
| `side` | `"buy"` \| `"sell"` | |
| `quantity` | number | As requested, rounded to 4 dp |
| `price` | number \| null | Fill price when ok; the cached price when it failed for another reason; `null` if no price was available |
| `status` | `"ok"` \| `"failed"` | |
| `error` | string \| null | Same strings as `POST /api/portfolio/trade`; `null` when ok |

Execution order: all `watchlist_changes` in array order, then all `trades` in array order. One failure does not stop the rest.

### `POST /api/chat`

Request:
```json
{"message": "Add PYPL to my watchlist and buy 5 shares"}
```

`200`
```json
{
  "message": "Adding PYPL to your watchlist and placing an order for 5 PYPL.",
  "actions": {
    "watchlist_changes": [
      {"ticker": "PYPL", "action": "add", "status": "ok", "error": null}
    ],
    "trades": [
      {"ticker": "PYPL", "side": "buy", "quantity": 5.0, "price": 72.40, "status": "ok", "error": null}
    ]
  }
}
```

No actions:
```json
{"message": "Your portfolio is 81% cash. AAPL is your only position, up 0.60%.", "actions": {"watchlist_changes": [], "trades": []}}
```

Errors:

| Condition | Status | `detail` | Stored? |
|---|---|---|---|
| Missing `message` / wrong type | 400 | `Invalid request: message: <reason>` | nothing |
| Empty after trim | 400 | `Message must not be empty` | nothing |
| Longer than 2000 characters | 400 | `Message must be at most 2000 characters` | nothing |
| No API key and `LLM_MOCK` ≠ `true` | 503 | `LLM not configured: set OPENROUTER_API_KEY or LLM_MOCK=true` | nothing |
| Timeout (30 s), provider error, or invalid structured output after one retry | 502 | `LLM request failed: <short reason>` | user message only; no actions executed |

The UI renders 502/503 as an inline error in the chat panel. After a `200` with any action, the frontend refetches portfolio, watchlist and history.

### `GET /api/chat/history`

Query: `limit` (optional, integer 1–100, default 20). Returns the most recent `limit` messages in **ascending** `created_at` order. `actions` is `null` for user messages.

`200`
```json
{
  "messages": [
    {"id": "0b9d6a7e-5c1f-4a8e-8f0a-6e2d1c3b4a50", "role": "user", "content": "Add PYPL to my watchlist and buy 5 shares", "actions": null, "created_at": "2026-10-18T14:05:40.900Z"},
    {"id": "c47e2f13-9a2b-4d6c-b1e8-7f3a5d9c0e22", "role": "assistant", "content": "Adding PYPL to your watchlist and placing an order for 5 PYPL.", "actions": {"watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "ok", "error": null}], "trades": [{"ticker": "PYPL", "side": "buy", "quantity": 5.0, "price": 72.40, "status": "ok", "error": null}]}, "created_at": "2026-10-18T14:05:41.300Z"}
  ]
}
```

Fresh database: `{"messages": []}`.

- `limit` out of range → `400 {"detail": "limit must be an integer between 1 and 100"}`.

---

## LLM structured output

Model: `openrouter/openai/gpt-oss-120b` via LiteLLM → OpenRouter, Cerebras provider (see the cerebras-inference skill). Sent as:

```json
{"type": "json_schema", "json_schema": {"name": "finally_response", "strict": true, "schema": { ...schema below... }}}
```

Schema — all three properties are **required**; arrays may be empty:
```json
{
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
          "quantity": {"type": "number"}
        },
        "required": ["ticker", "side", "quantity"],
        "additionalProperties": false
      }
    },
    "watchlist_changes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "ticker": {"type": "string"},
          "action": {"type": "string", "enum": ["add", "remove"]}
        },
        "required": ["ticker", "action"],
        "additionalProperties": false
      }
    }
  },
  "required": ["message", "trades", "watchlist_changes"],
  "additionalProperties": false
}
```

Parsing rules:
- Output that isn't valid JSON or doesn't match the schema is a **parse failure** → retry the call once → second failure is `502`.
- Values that match the schema but fail business validation (bad ticker, `quantity ≤ 0`, insufficient cash) are **not** parse failures; they become `"failed"` action results.

---

## LLM mock mode

Active when `LLM_MOCK=true`. No network call, no retry, never returns `502`/`503`. The structured response is built from the user's message by the rules below, then flows through the normal execution/storage/response path.

Let `m` be the user's message. All regexes are **case-insensitive**.

1. **Watchlist adds** — every match of `\badd\s+([A-Za-z]{1,5})\b`, in order of appearance → `{"ticker": UPPER(group 1), "action": "add"}`.
2. **Watchlist removes** — every match of `\bremove\s+([A-Za-z]{1,5})\b`, in order → `{"ticker": UPPER(group 1), "action": "remove"}`.
   `watchlist_changes` = adds followed by removes.
3. **Buy** — if `\bbuy\b` matches anywhere → trade `{"ticker": "AAPL", "side": "buy", "quantity": 1}`.
4. **Sell** — if `\bsell\b` matches anywhere → trade `{"ticker": "AAPL", "side": "sell", "quantity": 1}`.
   `trades` = buy (if any) followed by sell (if any).
5. **Message**:
   - No actions → exactly
     `This is a mock response from FinAlly. Try "buy", "sell", "add XYZ" or "remove XYZ".`
   - Otherwise → `Mock response: ` + the phrases below joined with `; ` + `.`, in action order (watchlist changes, then trades):
     - add → `adding XYZ to your watchlist`
     - remove → `removing XYZ from your watchlist`
     - buy → `placing a buy order for 1 AAPL`
     - sell → `placing a sell order for 1 AAPL`

Examples:

| User message | `watchlist_changes` | `trades` | `message` |
|---|---|---|---|
| `hello` | `[]` | `[]` | `This is a mock response from FinAlly. Try "buy", "sell", "add XYZ" or "remove XYZ".` |
| `buy` | `[]` | buy 1 AAPL | `Mock response: placing a buy order for 1 AAPL.` |
| `please sell` | `[]` | sell 1 AAPL | `Mock response: placing a sell order for 1 AAPL.` |
| `add PYPL` | add PYPL | `[]` | `Mock response: adding PYPL to your watchlist.` |
| `Add pypl and buy` | add PYPL | buy 1 AAPL | `Mock response: adding PYPL to your watchlist; placing a buy order for 1 AAPL.` |
| `remove NFLX` | remove NFLX | `[]` | `Mock response: removing NFLX from your watchlist.` |

Note that `buy`/`sell` always trade AAPL, regardless of other tickers in the message. Results still follow normal validation — e.g. `sell` with no AAPL position yields a `"failed"` trade with `Insufficient shares: requested 1, held 0`.

---

## Metric formulas

Used identically by the backend (`/api/portfolio`, snapshots, LLM context) and the frontend (live values). `price` is the live/cached price, or `avg_cost` when none is available.

```
market_value     = quantity × price
unrealized_pnl   = (price − avg_cost) × quantity
pnl_pct          = (price − avg_cost) / avg_cost × 100
positions_value  = Σ market_value
total_value      = cash_balance + positions_value
total_pnl        = total_value − 10000
total_pnl_pct    = total_pnl / 10000 × 100
change_pct       = (price − open_price) / open_price × 100        # watchlist daily change
weight           = market_value / positions_value                  # heatmap tile area
```

Trade bookkeeping:
```
buy:   cost = round(q × price, 2);  cash −= cost
       new_qty  = old_qty + q
       avg_cost = (old_qty × old_avg + q × price) / new_qty
sell:  cash += round(q × price, 2)
       new_qty = old_qty − q;  avg_cost unchanged
       if new_qty < 1e-6: delete the position row
```
Quantities are stored rounded to 4 dp, cash to 2 dp. Realized P&L is not tracked separately.

---

## Heatmap color scale

- Tile color from the position's `pnl_pct`, **clamped to [−5, +5]**.
- Linear RGB interpolation from neutral gray at 0 toward red (negative) or green (positive):

| `pnl_pct` | Color |
|---|---|
| ≤ −5 | `#da3633` rgb(218, 54, 51) |
| 0 | `#585860` rgb(88, 88, 96) |
| ≥ +5 | `#2ea043` rgb(46, 160, 67) |

```ts
const RED = [218, 54, 51], GRAY = [88, 88, 96], GREEN = [46, 160, 67];
function heatColor(pnlPct: number): string {
  const t = Math.max(-5, Math.min(5, pnlPct)) / 5;            // −1..1
  const target = t < 0 ? RED : GREEN;
  const k = Math.abs(t);
  const [r, g, b] = GRAY.map((c, i) => Math.round(c + (target[i] - c) * k));
  return `rgb(${r}, ${g}, ${b})`;
}
```

The gray has equal R and G, so the sign is readable from the color: positive → G > R, negative → R > G, zero → R = G. E2E tests assert exactly that against each tile's displayed P&L %.

- **No cash tile.** Tile area ∝ `weight`.
- **Empty state** (no positions): the heatmap area shows `No positions yet — buy something to see your heatmap.`

---

## Errors

All errors are `{"detail": "<string>"}`.

| Status | When |
|---|---|
| 400 | Any validation failure, including malformed/missing body fields and bad query params. FastAPI's default 422 is converted to 400 by a `RequestValidationError` handler, with `detail` = `Invalid request: <field>: <reason>` |
| 404 | Unknown `/api/*` route: `{"detail": "Not Found"}` (JSON — the static-file mount must never serve `index.html` for `/api/*`) |
| 502 | LLM upstream failure: `LLM request failed: <short reason>` |
| 503 | LLM not configured: `LLM not configured: set OPENROUTER_API_KEY or LLM_MOCK=true` |

Exact `400` strings are listed with each endpoint above.
