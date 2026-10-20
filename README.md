# FinAlly — AI Trading Workstation

A simulated trading terminal with live streaming prices, a virtual $10,000 portfolio and an AI chat assistant that can trade on your behalf.

- Build plan: [`planning/PLAN.md`](planning/PLAN.md)
- API contract: [`planning/API_CONTRACT.md`](planning/API_CONTRACT.md)
- Original spec: [`SPEC.md`](SPEC.md)

## Quick start

You need [Docker](https://docs.docker.com/get-docker/), and it must be running.

**macOS / Linux**

```bash
scripts/start_mac.sh          # build (first run only) and start
scripts/stop_mac.sh           # stop
```

**Windows (PowerShell)**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\stop_windows.ps1
```

Then open **http://localhost:8000** (the start script opens it for you).

The start scripts:

- create `.env` from `.env.example` if it is missing, and print a warning;
- build the `finally` image if it doesn't exist yet. Pass `--build` (`-Build` on Windows) to rebuild after pulling changes;
- replace any running `finally` container with a fresh one, wait until it is healthy, and print the URL. Pass `--no-open` (`-NoOpen`) to skip opening the browser.

Both scripts are safe to run more than once. Your portfolio, trades and chat history live in the Docker volume `finally-data` and survive restarts and rebuilds. To start over with a fresh $10,000, stop the app and run `docker volume rm finally-data`.

### Configuration (`.env`)

Every setting is optional. The app runs with `.env.example` as it is: prices come from the built-in simulator, and chat answers `503 LLM not configured`.

| Variable | Effect |
|---|---|
| `OPENROUTER_API_KEY` | Enables AI chat via OpenRouter |
| `LLM_MOCK=true` | Deterministic mock chat replies, no key needed |
| `MASSIVE_API_KEY` | Real market data from Massive (Polygon.io) instead of the simulator |

After editing `.env`, run the start script again. Rebuilding isn't needed, because `.env` is passed with `--env-file` and is never copied into the image. See [`planning/PLAN.md` §5](planning/PLAN.md) for the full list.

The same container can be started by hand:

```bash
docker build -t finally .
docker run -d --name finally -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

## Development

Run the backend and the Next.js dev server separately, with hot reload. You need [uv](https://docs.astral.sh/uv/) and Node 22+.

```bash
# Terminal 1: API on :8000. DEV_MODE enables CORS for localhost:3000.
cd backend
uv sync
DEV_MODE=true uv run uvicorn app.main:app --reload

# Terminal 2: UI on :3000, calling the API on :8000
cd frontend
echo 'NEXT_PUBLIC_API_BASE=http://localhost:8000' > .env.local
npm install
npm run dev
```

Open http://localhost:3000. Outside Docker, the backend reads the root `.env` and stores its database at `db/finally.db`.

### Tests

```bash
# Backend
cd backend
uv run pytest
uv run ruff check . && uv run ruff format --check .

# Frontend
cd frontend
npm test
npm run lint && npm run typecheck
```

End-to-end tests (Playwright) live in [`test/`](test/).
