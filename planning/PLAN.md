# FinAlly — AI Trading Workstation

## Project Plan (shared agent contract)

This document is the authoritative build plan. It is `SPEC.md` with every review item from SPEC §13 (R1–R38, S1–S9) resolved and folded into the relevant section. Items are still cited inline (e.g. "(R22)") so agents can trace decisions back to the review.

Exact request/response JSON, status codes, the SSE payload, the LLM structured-output schema and the mock-mode rules live in **[`planning/API_CONTRACT.md`](API_CONTRACT.md)**. Frontend and backend build in parallel against that file. If this document and the contract ever disagree on a wire format, the contract wins — fix whichever is wrong in the same change.

Global conventions (R7):

- JSON keys are **snake_case** everywhere.
- Timestamps are **ISO-8601 UTC strings with milliseconds and a `Z` suffix**, e.g. `2026-10-18T14:03:12.500Z`. The database stores the same format.
- Errors use FastAPI's `{"detail": "<string>"}` shape. `detail` is always a human-readable string (never a list).
- Money and prices are rounded to 2 decimals in responses; quantities to 4 decimals; percentages are percentage points rounded to 2 decimals (`1.23` means 1.23%).

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single start script (which wraps `docker run`). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist (if no LLM is configured, chat shows a clear "LLM not configured" message; everything else works — R3)

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area; clicking also pre-fills the trade bar's ticker field (R31)
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog, fractional quantities allowed (S8)
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L %, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, P&L % (R18)
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language. Each action's result is shown inline as ✓ or ✗ with the error (R22)
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot in the header — green = connected, yellow = reconnecting, red = disconnected. Brief drops show yellow, not red (R38); exact rules in §10
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python 3.12 / uv), 1 uvicorn worker   │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving        │
│                      (Next.js export)           │
│                                                 │
│  SQLite database (volume-mounted at /app/db)    │
│  Background tasks: market data sim/poller,      │
│                    portfolio snapshots (30 s)   │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python 3.12), managed as a `uv` project
- **Database**: SQLite, single file at `DB_PATH` (default `<repo root>/db/finally.db`; `/app/db/finally.db` in the container), volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — one-way server→client push, one batched event per tick
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution; a single LLM call per chat message (S7)
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided (Massive is a stretch goal, built last — S6)

### Concurrency model (R20)

- Uvicorn runs with a **single worker** (`--workers 1`). Multiple workers would each run their own simulator, price cache and snapshot task.
- All trade executions (manual and chat-initiated) are serialized through one process-wide `asyncio.Lock`. Each trade runs in a single DB transaction.

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container, no compose for running the app (S1) | Students run one script; the only compose file is `test/docker-compose.test.yml` |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |
| Single uvicorn worker | One price cache, one simulator, one snapshot task; trades serialized with an `asyncio.Lock` |

---

## 4. Directory Structure

The tree root below is the repository root, whatever the checkout directory is called.

```
<repo root>/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python 3.12)
│   ├── pyproject.toml
│   ├── uv.lock               # Committed (Docker uses uv sync --frozen)
│   ├── app/                  # Python package; ASGI entrypoint is app.main:app
│   │   └── storage/          # Schema SQL, seed data, DB initialization (R33)
│   └── tests/                # pytest
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   ├── API_CONTRACT.md       # Exact wire formats (authoritative)
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS and Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS and Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; *.db is gitignored
├── Dockerfile                # Multi-stage build (Node 22 → Python 3.12)
├── .env.example              # Committed template (R35)
├── .env                      # Local environment (gitignored, never baked into the image)
├── .gitignore
└── README.md                 # Quick start: scripts, .env setup, URL
```

There is **no root `docker-compose.yml`** (S1). The `*_mac.sh` scripts work unchanged on Linux; the names are kept for course continuity.

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents, with two fixed points: the ASGI app is `app.main:app` (run from `backend/`), and schema/seed/init code lives in `backend/app/storage/`.
- **`backend/app/storage/`** contains schema SQL definitions and seed logic. It is deliberately *not* called `db/`, so there is only one directory named `db` in the repo and nothing collides with the container's `/app/db` volume (R33).
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan and the API contract. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (`docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

`.env.example` is committed; `.env` is gitignored (R35).

```bash
# Optional: OpenRouter API key for LLM chat. Without it (and with LLM_MOCK not
# "true"), the app runs normally and POST /api/chat returns 503 "LLM not configured".
OPENROUTER_API_KEY=

# Optional: Massive (Polygon.io) API key for real market data.
# If not set, the built-in market simulator is used (recommended for most users).
MASSIVE_API_KEY=

# Optional: "true" for deterministic mock LLM responses (tests, no API key needed)
LLM_MOCK=false

# Optional: SQLite file path. Default: <repo root>/db/finally.db.
# The Docker image sets DB_PATH=/app/db/finally.db.
DB_PATH=
```

Additional optional variables (not needed for normal use):

| Variable | Default | Purpose |
|---|---|---|
| `MASSIVE_POLL_SECONDS` | `15` | Massive poll interval (free tier: 15; paid: 2–15) |
| `DEV_MODE` | `false` | `true` enables CORS for `http://localhost:3000` for local `next dev` (R32). Never set in the image |
| `NEXT_PUBLIC_API_BASE` | `""` | Frontend build/dev-time API origin, e.g. `http://localhost:8000` when running `next dev`. Empty in production (same origin). Set in `frontend/.env.local`, not the root `.env` |

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (rules in API_CONTRACT.md §LLM mock mode); no API key needed
- If `LLM_MOCK` is not `true` and `OPENROUTER_API_KEY` is empty → app starts normally; `POST /api/chat` returns `503 {"detail": "LLM not configured: set OPENROUTER_API_KEY or LLM_MOCK=true"}` (R3)
- When running locally outside Docker, the backend loads the root `.env` with `python-dotenv` (real environment variables take precedence). In Docker, `.env` is passed via `--env-file` and is **never** copied into the image (R34)
- Empty-string values are treated the same as unset

---

## 6. Market Data

### Two Implementations, One Interface (R10)

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on `MASSIVE_API_KEY`. All downstream code (SSE streaming, trades, snapshots, LLM context, frontend) is agnostic to the source.

```python
class MarketDataSource(ABC):
    async def start(self) -> None: ...        # begin the background loop
    async def stop(self) -> None: ...         # cancel it cleanly
    def add_ticker(self, ticker: str) -> None: ...
    def remove_ticker(self, ticker: str) -> None: ...

class PriceCache:
    def get(self, ticker: str) -> PriceEntry | None: ...
    def get_all(self) -> dict[str, PriceEntry]: ...
    # plus a write method used only by the active source, and remove(ticker)

@dataclass
class PriceEntry:
    price: float
    previous_price: float
    open_price: float       # reference for daily change % (R11)
    timestamp: datetime     # UTC
```

### Which tickers are priced (R9)

The **tracked set** is: every ticker on the watchlist ∪ every ticker with an open position.

- On startup, the tracked set is loaded from the DB and passed to the source.
- Adding a watchlist ticker calls `add_ticker`. Opening a position in an untracked ticker cannot happen (trades need a cached price), so positions only ever reference tracked tickers.
- Removing a ticker from the watchlist calls `remove_ticker` **only if there is no open position** in it. A held ticker keeps being priced, so its valuation never freezes.
- When a sell closes a position and the ticker is not on the watchlist, it is removed from the source and cache.
- A trade whose ticker has no cached price is rejected with `400 "No price available for XYZ"`.

### Simulator (Default)

- Geometric Brownian motion (GBM), one step every **500 ms**: `S ← S · exp((μ − σ²/2)·dt + σ·√dt·ε)`
- `dt` is the tick length in trading-years (`0.5 s / (252 × 6.5 × 3600 s)`) multiplied by **`SIM_TIME_SCALE = 25`** (R15). At σ = 30%/yr this gives ≈0.04% per tick and ≈1.5% over 10 minutes — lively but believable. `SIM_TIME_SCALE` is a single module-level constant.
- **Correlation (S5)** — no covariance matrix. Each tick, draw one market shock `Z_m`, one shock per sector `Z_s`, and one idiosyncratic shock `Z_i` per ticker (all standard normal). The ticker's shock is
  `ε = (β·w_m·Z_m + w_s·Z_s + w_i·Z_i) / √((β·w_m)² + w_s² + w_i²)`
  (normalized to unit variance). Suggested weights `w_m = 0.5, w_s = 0.35, w_i = 0.35`; tickers without a sector use `w_s = 0`.
- **Events** — each tick, each ticker has probability **`EVENT_PROBABILITY = 0.001`** of a sudden jump of ±2–5% (uniform magnitude, random sign). With 10 tickers that's roughly one event every 50 s. Single constant (R15).
- **Seed parameters** for the default tickers (μ = 0 for all):

  | Ticker | Seed price | σ (annual) | β | Sector |
  |---|---|---|---|---|
  | AAPL | 190 | 0.25 | 1.1 | tech |
  | GOOGL | 175 | 0.28 | 1.1 | tech |
  | MSFT | 420 | 0.24 | 1.0 | tech |
  | AMZN | 185 | 0.30 | 1.2 | consumer |
  | TSLA | 250 | 0.55 | 1.8 | consumer |
  | NVDA | 120 | 0.50 | 1.7 | tech |
  | META | 500 | 0.35 | 1.3 | tech |
  | JPM | 200 | 0.22 | 0.9 | finance |
  | V | 275 | 0.20 | 0.8 | finance |
  | NFLX | 650 | 0.38 | 1.2 | consumer |

- **Unknown tickers (R12)**: any symbol matching `^[A-Z]{1,5}$` is accepted. It gets a uniformly random seed price in $50–$300, σ = 0.35, β = 1.0 and no sector (market + idiosyncratic only). `add_ticker` writes the seed price to the cache **immediately** so the ticker can be traded in the same request (e.g. the LLM adds and buys it in one response).
- **Restart continuity (R14)**: on startup, each ticker with an open position is seeded from its **most recent trade price** (from `trades`) instead of the table seed, so P&L and the P&L chart don't jump after a restart.
- **`open_price` (R11)**: the price at which the ticker entered the cache in this process (its seed or restart price). Daily change % = `(price − open_price) / open_price × 100`.
- On the first write for a ticker, `previous_price = price = open_price`.
- Runs as an in-process asyncio background task — no external dependencies.

### Massive API (Optional, stretch goal — S6)

Built **last**, after everything else works. The interface above is kept so it slots in without downstream changes.

- REST polling (not WebSocket), every `MASSIVE_POLL_SECONDS` (default 15 s, which fits the free tier's 5 calls/min)
- One multi-ticker snapshot call per poll for the whole tracked set
- `open_price` = previous close from the snapshot response
- **Unverified tier limits (R16)**: Polygon's free tier historically provided end-of-day data only, and the snapshot endpoint may require a paid tier. The Massive agent must confirm this before building. If data is EOD-only or the market is closed, prices simply don't change between polls; SSE keeps sending the (unchanged) cache — that is acceptable behavior, not an error.
- **Invalid symbols (R12)**: a symbol absent from the snapshot response stays on the watchlist with no price (`price: null`, UI shows "—"); trades on it get `400 "No price available for XYZ"`. It is not auto-removed.
- `add_ticker` cannot price immediately with Massive; the ticker gets a price on the next poll.
- Tests run against recorded JSON responses, never the live API.

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- Each entry holds `price`, `previous_price`, `open_price` and `timestamp` (R10, R11)
- SSE streams, trade execution, snapshots and the LLM context all read from this cache
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming (R13, S3)

- Endpoint: `GET /api/stream/prices`, consumed with the native `EventSource` API
- **One event per tick (~500 ms)** carrying a map of **all** priced tickers. Default (unnamed) event, so the client uses `onmessage`.
- The first event is sent **immediately on connect** so the UI is never blank.
- No `direction` field — clients derive up/down from `price` vs `previous_price` (S3).
- Newly added tickers appear in the next event without the client reconnecting; removed tickers disappear from it.
- Exact payload: API_CONTRACT.md §SSE.
- Client reconnection is handled by EventSource's built-in retry; the server sends `retry: 2000` with the first event.

---

## 7. Database

### SQLite, Initialized at Startup (R2, S2)

The database is initialized **once, in the FastAPI lifespan startup**, before background tasks start. There is no lazy/first-request initialization path.

Startup sequence:

1. Resolve `DB_PATH` (default `<repo root>/db/finally.db`); create the parent directory if missing.
2. If the file doesn't exist or tables are missing: create the schema (`CREATE TABLE IF NOT EXISTS`) and seed default data, including one initial portfolio snapshot.
3. Build the tracked ticker set (watchlist ∪ positions), seed held tickers from their last trade price (R14), start the market data source.
4. Start the 30 s snapshot task.

Shutdown stops the background tasks.

This means no separate migration step, no manual setup, and fresh Docker volumes start with a clean, seeded database automatically.

### Schema

Every table except `users_profile` has a `user_id` column defaulting to `"default"`; `users_profile` is keyed by `id`, which *is* the user id. Single-user is hardcoded for now, but this enables future multi-user support without schema migration.

All timestamps are stored as ISO-8601 UTC strings in the format described at the top of this document.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional, rounded to 4 dp)
- `avg_cost` REAL
- `updated_at` TEXT
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional, rounded to 4 dp)
- `price` REAL
- `executed_at` TEXT

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded once at DB creation ($10,000 — R21), every 30 seconds by a background task, and immediately after each successful trade.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT

At one row every 30 s the table grows by ~2,880 rows/day, which is fine for SQLite; `GET /api/portfolio/history` takes `?limit` so long-running databases stay cheap to read (R21).

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — the same `actions` object returned by `POST /api/chat`, including each action's result; null for user messages — R23)
- `created_at` TEXT

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX
- One portfolio snapshot: `total_value=10000.0` (R21)

---

## 8. API Endpoints

Exact request/response bodies, status codes and error strings are in **API_CONTRACT.md**. Summary:

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream: one batched event per tick with all priced tickers |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Cash, positions (qty, avg cost, plus point-in-time price/P&L), total value |
| POST | `/api/portfolio/trade` | Execute a trade `{ticker, quantity, side}`; returns the trade **and** the updated portfolio (R8) |
| GET | `/api/portfolio/history` | Portfolio snapshots, ascending by time, optional `?limit=` (R8, R21) |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Watchlist tickers with latest cached prices |
| POST | `/api/watchlist` | Add a ticker `{ticker}`; idempotent `200` if already present (R8) |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker; idempotent `200` if not present (R8) |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message; returns `{message, actions}` with each action's result (R22, R23) |
| GET | `/api/chat/history` | Last 20 messages, ascending, with their actions (R24) |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | `{"status": "ok"}` (R8) |

### Error conventions (R7)

- `400` — any validation failure, including malformed bodies. The backend registers a `RequestValidationError` handler that converts FastAPI's default 422 into `400 {"detail": "<string>"}`.
- `404` — unknown `/api/*` route (JSON, never `index.html`).
- `502` — LLM upstream failure (timeout, malformed output after one retry, provider error).
- `503` — LLM not configured (R3).

### Routing and static files

FastAPI mounts `StaticFiles(directory=<static dir>, html=True)` at `/` **after** all API routers, so it never captures `/api/*`. The static dir is `backend/static/` (populated from the frontend export in Docker; may be absent in development, in which case the mount is skipped).

### Portfolio math (R17, R18, R19)

Shared by the backend (snapshots, LLM context, `/api/portfolio` point-in-time values) and the frontend (live values). Formulas are stated exactly in API_CONTRACT.md §Metric formulas.

- **Live valuation (R17)**: `/api/portfolio` supplies cash, quantities and average costs (and a point-in-time valuation for convenience). The frontend recomputes `total_value = cash + Σ quantity × live_price` from SSE prices, falling back to `avg_cost` when a ticker has no cached price. The backend uses the identical formula for snapshots and LLM context.
- **Unrealized P&L** = `(price − avg_cost) × quantity`
- **P&L %** (positions table column, renamed from "% change") = `(price − avg_cost) / avg_cost × 100`
- **Total P&L** = `total_value − 10,000`
- **avg_cost** is a weighted average on buys and unchanged on sells.
- **Realized P&L is not tracked separately** — accepted. It is implicit in cash.
- **Trade validation (R19)**: ticker is trimmed and uppercased, then must match `^[A-Z]{1,5}$`; `side` must be `buy` or `sell`; `quantity` is rounded to 4 dp and must then be `> 0`; ticker must have a cached price; buys need `cost ≤ cash`; sells need `quantity ≤ held` (rejected, never clamped). Cash is rounded to 2 dp after each trade. A position row is deleted once its quantity drops below `1e-6`. Each trade is one DB transaction, executed under the global trade lock (R20).
- **Fractional shares are kept (S8)**: quantities 4 dp, cash 2 dp.

---

## 9. LLM Integration

When writing code to make calls to LLMs, use the cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs are used to interpret the results.

`OPENROUTER_API_KEY` (in the root `.env`) is optional; see §5 for behavior when it is missing (R3).

### How It Works (S7 — single LLM call)

When the user sends a chat message, the backend:

1. Validates the message (non-empty after trim, ≤ 2,000 chars) and checks the LLM is configured (mock or key).
2. Stores the user's message in `chat_messages`.
3. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value — same formulas as §8).
4. Loads the **last 20 messages** from `chat_messages` (R26), including each assistant message's stored `actions` with results, so the LLM learns about earlier failures (R22).
5. Constructs a prompt: system message, portfolio context, conversation history, the new user message.
6. Calls the LLM via LiteLLM → OpenRouter with structured output (timeout 30 s), using the cerebras-inference skill.
7. Parses the structured JSON response. On a parse/schema failure, **retries once**; if it fails again, or on timeout/upstream error, returns `502` (R26).
8. Executes **watchlist changes first, then trades** (R25), in array order. Each trade goes through exactly the same validation and lock as a manual trade. One failing action does not stop the others.
9. Stores the assistant message with the `actions` object (including each result) in `chat_messages`.
10. Returns `{message, actions}` (R23). No token streaming — a loading indicator is sufficient.

On failure in steps 6–7 (R26): nothing is executed, the user's message stays stored, no assistant message is stored, the endpoint returns `502 {"detail": "..."}`, and the UI shows an inline error in the chat panel.

### Structured Output Schema (R25)

```json
{
  "message": "Placing an order for 10 AAPL and adding PYPL to your watchlist.",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (required): conversational text shown to the user
- `trades` (required, may be empty): trades to auto-execute
- `watchlist_changes` (required, may be empty): `action` is `"add"` or `"remove"`

All three properties are required (strict structured-output modes need every property, and parsing is simpler). The exact JSON Schema sent to the model is in API_CONTRACT.md.

### Action results (R22, R23)

The LLM writes its message before anything is validated, so it cannot know whether a trade will succeed. Instead:

- Each action's result (`status: "ok" | "failed"`, plus `error`, and the fill `price` for trades) is returned alongside the message and stored in `chat_messages.actions`.
- The UI renders each result inline: ✓ for ok, ✗ plus the error for failed.
- The results appear in the next turn's history, so the LLM can acknowledge earlier failures.

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

### System Prompt Guidance

The LLM is prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- **Describe trades as intent** ("Placing an order for 10 AAPL"), never in the past tense, because results are only known after execution (R22)
- Use fractional quantities when the user specifies a dollar amount (`dollars / price`, rounded down to 4 dp)
- Always respond with valid structured JSON matching the schema; use empty arrays when there are no actions

### LLM Mock Mode (R27)

When `LLM_MOCK=true`, the backend skips OpenRouter and builds the structured response deterministically from the user's message. Everything after parsing (execution order, validation, storage, response shape) is identical to the real path. The exact rules — which E2E tests rely on — are in API_CONTRACT.md §LLM mock mode. In short:

- `add XYZ` → add XYZ to the watchlist; `remove XYZ` → remove it
- the word `buy` → buy 1 AAPL; the word `sell` → sell 1 AAPL
- anything else → a fixed reply with no actions

This enables fast, free, reproducible E2E tests, development without an API key, and CI.

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI includes these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), daily change % (vs `open_price` from SSE — R11), a sparkline mini-chart (accumulated from SSE since page load), and a remove control. A ticker with no price shows "—".
- **Main chart area** — larger chart for the currently selected ticker, price over time. Clicking a ticker in the watchlist selects it here and pre-fills the trade bar.
- **Portfolio heatmap** — treemap where each rectangle is a position, sized by portfolio weight (market value), colored by P&L % (R30, below).
- **P&L chart** — line chart of total portfolio value over time from `GET /api/portfolio/history`, with the live total appended as the latest point.
- **Positions table** — ticker, quantity, avg cost, current price, unrealized P&L, P&L % (R18).
- **Trade bar** — ticker field, quantity field, buy button, sell button. Market orders, instant fill (R31, below).
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history (loaded from `GET /api/chat/history` on page load — R24), loading indicator while waiting. Each action result shown inline as ✓ / ✗ + error. An LLM failure (502/503) shows an inline error message in the conversation.
- **Header** — portfolio total value (updating live from SSE — R17), connection status indicator, cash balance.

### Charting (R1, S4)

- **Main chart and P&L chart**: TradingView **Lightweight Charts** (canvas).
- **Sparklines**: inline SVG `<polyline>` — no library.
- **Heatmap**: plain `div`s positioned by **`d3-hierarchy`**'s treemap layout (styled with Tailwind). Recharts is not used.

### Price history buffer (R28)

- The frontend keeps one in-memory buffer per ticker, fed by SSE since page load, grouped into **1-second buckets** (last price in each second — Lightweight Charts does not support sub-second time steps), capped at **1,000 points** per ticker.
- The main chart and the sparkline both read this buffer (the sparkline may show only the most recent slice).
- The main chart is empty after a page reload and fills in progressively. This is accepted; there is no backend price-history endpoint.

### State refresh (R29)

After a manual trade, a watchlist change, or a chat response containing any actions, refetch `/api/portfolio`, `/api/watchlist` and `/api/portfolio/history`. No other polling; SSE drives prices.

### Heatmap details (R30)

- Tile area ∝ position market value (`quantity × live price`). **Cash is not a tile.**
- Color by P&L %, clamped to **±5%**, linearly interpolated **red → neutral gray → green**. Exact colors in API_CONTRACT.md §Heatmap color scale.
- Each tile shows the ticker and its P&L %.
- **Empty state** (no positions): the heatmap area shows the text "No positions yet — buy something to see your heatmap."

### Trade bar behavior (R31)

- Clicking a watchlist ticker pre-fills the ticker field.
- Quantity accepts **fractions** (up to 4 dp; `step="0.0001"`, must be > 0).
- Results are shown **inline** under the trade bar (no toast): success e.g. "Bought 10 AAPL @ $190.12"; error shows the API's `detail`. The message clears after ~4 s or on the next submit.

### Connection status (R38, S9)

Driven by `EventSource` events:

- **green** — `onopen` fired and the connection is open
- **yellow** — `onerror` fired and `readyState === CONNECTING` (browser is retrying)
- **red** — `readyState === CLOSED`, or still not reconnected 15 s after the first error

Brief drops (e.g. hosted platforms cutting long-lived requests) therefore show yellow, not red.

### Technical Notes

- `EventSource` connects to `${NEXT_PUBLIC_API_BASE}/api/stream/prices`; all REST calls go to `${NEXT_PUBLIC_API_BASE}/api/*`. In production `NEXT_PUBLIC_API_BASE` is empty (same origin).
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition (~500 ms), then remove it.
- Tailwind CSS for styling with a custom dark theme.
- **Static export constraints**: `output: 'export'`; set `images: { unoptimized: true }` if `next/image` is used; no Next API routes, middleware or `rewrites`.
- **Development (R32)**: run `next dev` on :3000 with `NEXT_PUBLIC_API_BASE=http://localhost:8000` in `frontend/.env.local`, and the backend with `DEV_MODE=true`, which enables CORS for `http://localhost:3000` only. Production never enables CORS.

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile (R5, R33, R37)

```
Stage 1: node:22-slim
  - Copy frontend/
  - npm ci && npm run build            (static export → frontend/out/)

Stage 2: python:3.12-slim
  - Install uv
  - WORKDIR /app/backend
  - Copy backend/pyproject.toml + backend/uv.lock; uv sync --frozen --no-dev
  - Copy backend/ → /app/backend/
  - Copy frontend/out/ → /app/backend/static/
  - ENV DB_PATH=/app/db/finally.db
  - EXPOSE 8000
  - HEALTHCHECK via python (no curl in slim images):
      python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=3).status == 200 else 1)"
  - CMD: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

The backend lives at `/app/backend`, **not** `/app`, so nothing in the image sits at `/app/db` — that path belongs to the volume alone (R33). `uv.lock` is committed. `.env` is never copied into the image (R34); a `.dockerignore` excludes it along with `node_modules`, `.next`, `out`, `.venv` and `db/`.

### Docker Volume

```bash
docker run -d --name finally -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The named volume `finally-data` is mounted at `/app/db`; the backend writes `finally.db` there.

### Start/Stop Scripts

Names are kept as in the original spec; the `*_mac.sh` scripts work unchanged on Linux.

**`scripts/start_mac.sh`** (macOS/Linux):
- If `.env` is missing, copies `.env.example` to `.env` and prints a warning (R34)
- Builds the image `finally` if it doesn't exist, or if `--build` is passed
- Removes any existing `finally` container, then runs a new one with the volume, port mapping and `--env-file .env`
- Prints `http://localhost:8000`
- Opens the browser if `open` / `xdg-open` is available (skippable with `--no-open`)

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the `finally` container if it exists
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents.

All scripts are idempotent — safe to run multiple times.

### Optional Cloud Deployment (stretch)

The container can deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in `deploy/` as a stretch goal, not part of the core build.

If it goes ahead (R38): the app has no auth and holds the OpenRouter key server-side, so anyone with the URL could trade and spend credits. A public deployment must either add HTTP basic auth or force `LLM_MOCK=true`. Platforms that cap request duration will cut SSE periodically; EventSource reconnects and the status dot shows yellow, which is expected.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, correlation structure behaves (S5), unknown tickers get seeded immediately, the simulator conforms to the abstract interface. Massive parsing tests (against recorded responses) come with the stretch Massive client.
- Portfolio: trade execution, avg-cost math, P&L formulas, rounding, edge cases (selling more than owned, buying with insufficient cash, selling at a loss, dust-position deletion, no cached price)
- LLM: structured output parsing for valid schemas, retry-then-502 on malformed responses, watchlist-before-trades ordering, partial-failure results, every mock-mode rule from API_CONTRACT.md
- API routes: status codes, response shapes and error strings exactly as in API_CONTRACT.md

**Frontend (Vitest + React Testing Library)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Portfolio display calculations (live valuation, P&L, P&L %, heatmap color scale)
- Chat message rendering, action results (✓/✗) and loading state
- Connection indicator transitions on EventSource `onopen` / `onerror` (replaces the SSE-resilience E2E test — S9)

Watchlist CRUD is not unit-tested on the frontend; the E2E scenario covers it (S9).

### E2E Tests (in `test/`)

**Infrastructure**: `test/docker-compose.test.yml` spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment and determinism (R36)**:
- `LLM_MOCK=true`.
- Each run starts with a fresh, throwaway DB (no named volume; e.g. tmpfs at `/app/db`).
- Tests do not depend on execution order; each test asserts relative changes or sets up its own state.
- Heatmap colors are asserted by **sign**: each tile's color must match the sign of its displayed P&L % (green-ish for positive, red-ish for negative, gray for ~0). No fixed-seed simulator is needed.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with sign-consistent colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline

The SSE-resilience E2E test is dropped (S9).
