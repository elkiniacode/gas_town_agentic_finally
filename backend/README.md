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
├── deps.py          # FastAPI dependencies (get_db, get_settings)
├── routers/         # health (done) + market, portfolio, watchlist, chat stubs
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
