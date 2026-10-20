# Massive API fixtures

Response bodies for `tests/test_massive.py`. Tests never call the live API.

Shapes follow the Massive (formerly Polygon.io) REST docs, checked 2026-10-20:

- `snapshot_*.json`: `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=...`
- `grouped_daily_*.json`: `GET /v2/aggs/grouped/locale/us/market/stocks/{date}`
- `unauthorized.json` (401), `rate_limited.json` (429): error bodies

These were written from the documented example responses, not captured from a
live key: none was available when the client was built. Refresh them from a
real key when you can. See `planning/MASSIVE_FREE_TIER.md`.
