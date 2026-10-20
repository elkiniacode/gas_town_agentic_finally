# FinAlly backend

FastAPI app (Python 3.12, managed with [uv](https://docs.astral.sh/uv/)). The ASGI entrypoint is `app.main:app`, run from this directory.

```bash
cd backend
uv sync                                   # create .venv with dev dependencies
uv run uvicorn app.main:app --reload      # http://localhost:8000/api/health
uv run pytest                             # tests
uv run ruff check . && uv run ruff format --check .
```

Configuration comes from environment variables; when run locally the root `.env` is loaded too (real environment variables win). See `../.env.example` and `../planning/PLAN.md` §5.

## Layout

```
app/
├── main.py          # create_app(), lifespan, router registration, static mount
├── config.py        # Settings + load_settings() (env / root .env)
├── errors.py        # {"detail": "<string>"} error handlers (422 → 400)
├── timeutil.py      # ISO-8601 UTC timestamps with ms + "Z"
├── deps.py          # FastAPI dependencies (get_db, get_settings, get_price_cache, ...)
├── market/          # PriceCache, MarketDataSource, GBM simulator, tracked-set helpers
├── routers/         # health, market (SSE), portfolio, watchlist + chat stub
├── services/        # watchlist + portfolio/trade logic shared by routes and chat
└── storage/         # schema.sql, seed data, init_database(), Database helper
tests/               # pytest; conftest.py provides a temp-DB app/client
```

### Database access

`app.state.db` is a `Database` (see `app/storage/database.py`). Inject it with `Depends(get_db)`:

```python
with db.connect() as conn:  # read-only work; rows are sqlite3.Row
    rows = conn.execute("SELECT ...").fetchall()

with db.transaction() as conn:  # BEGIN IMMEDIATE ... COMMIT / ROLLBACK
    conn.execute("UPDATE ...")
```

Use `app.timeutil.utc_now_iso()` for every stored timestamp and `app.storage.new_id()` for primary keys.

### Market data

The lifespan builds `app.state.price_cache` (a `PriceCache`) and starts `app.state.market_source`
(the simulator, or `MassiveSource` when `MASSIVE_API_KEY` is set). Inject them with `Depends(get_price_cache)` /
`Depends(get_market_source)`.

- Read prices with `cache.get("AAPL")` → `PriceEntry | None` (`price`, `previous_price`,
  `open_price`, `timestamp`). Both sources write prices rounded to 2 dp, so the cached price is
  the fill price. With Massive a ticker may have no entry (invalid symbol, or added since the
  last poll).
- After committing **any** watchlist add/remove or trade, call
  `app.market.sync_ticker(db, source, ticker)`. It prices the ticker iff it is on the watchlist or
  held (R9): a newly added ticker is priced immediately; a held ticker removed from the watchlist
  keeps streaming; a closed, unwatched position stops.
- Simulator knobs are the module constants `SIM_TIME_SCALE` and `EVENT_PROBABILITY` in
  `app/market/simulator.py` (R15).
- An open SSE connection keeps uvicorn's graceful shutdown waiting; run the server with
  `--timeout-graceful-shutdown 2` (the Docker CMD should) so `docker stop` is prompt.

### Watchlist and portfolio services

`app.services` holds the logic behind `/api/watchlist` and `/api/portfolio*`; the chat bead calls
it directly (not over HTTP) so both paths share validation, error strings and the trade lock.

- `get_watchlist(db, cache)`, `add_to_watchlist(db, source, ticker)`,
  `remove_from_watchlist(db, source, ticker)` — idempotent; they normalize the ticker, re-sync the
  priced set and return the normalized ticker.
- `await execute_trade(db, cache, source, lock, ticker, quantity, side)` → `ExecutedTrade`
  (`.to_wire()` is the contract's `trade` object). Runs under the trade lock (R20) in one
  transaction, then re-syncs pricing and records a snapshot.
- `get_portfolio(db, cache)` → the `GET /api/portfolio` body; `load_portfolio` returns the
  unrounded `Portfolio` (e.g. for LLM context).
- Failures raise `app.errors.BadRequest` with `.detail` set to the exact contract string (the app
  renders it as `400 {"detail": ...}`). Trade failures are `TradeError`, whose `.price` is the
  cached price when the ticker had one — what a failed chat trade reports.
- The lifespan runs `run_snapshot_loop` (every 30 s) after starting the market source.
