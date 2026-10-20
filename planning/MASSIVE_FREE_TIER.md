# Massive free tier: findings (R16)

Checked 2026-10-20 for fin-k90.11 against the Massive (formerly Polygon.io) REST docs and pricing
pages. Polygon.io became Massive on 2025-10-30. Keys and endpoints are unchanged: `api.massive.com`
and `api.polygon.io` both serve the same API. No live key was available, so these findings come from
the published docs, not from test calls.

## What each plan can use

| Endpoint | Stocks Basic (free) | Starter / Developer | Advanced / Business |
|---|---|---|---|
| Multi-ticker snapshot `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=A,B` | **Not included** (`403 NOT_AUTHORIZED`) | 15-min delayed | Real time |
| Grouped daily bars `GET /v2/aggs/grouped/locale/us/market/stocks/{date}` | End-of-day | 15-min delayed | Real time |

- **Free plan rate limit:** 5 calls per minute. Going over returns `429`. Paid plans have no call
  limit.
- **No intraday prices on the free plan.** PLAN.md's worry was right: the free plan only has
  end-of-day data, and it cannot use the snapshot endpoint at all.
- **Snapshot reset:** snapshot data is cleared every day at 3:30 AM ET and fills back in from 4:00 AM
  ET. In that gap `day`/`min` are zeros and `prevDay` still holds yesterday's bar.
- **Optional fields:** `lastTrade`/`lastQuote` only appear if the plan includes trades/quotes.

Sources: <https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot>,
<https://massive.com/docs/rest/stocks/aggregates/daily-market-summary>, <https://massive.com/pricing>.

## What the client does (`backend/app/market/massive.py`)

Each poll (every `MASSIVE_POLL_SECONDS`, default 15 s) makes at most one HTTP call. That stays
within the free plan's 5 calls/min.

**Snapshot mode (paid plans).** One snapshot call for the whole tracked set.
- price = last trade → minute-bar close → day close → previous close (the first positive one, so a
  ticker still has a price during the 3:30 AM reset).
- `open_price` = `prevDay.c`.

**End-of-day mode (free plan).** The first snapshot `403` switches the client to this mode for the
rest of the process. It loads grouped daily bars, starting at today (UTC) and stepping back one day
per poll until it has two trading days. Weekends and holidays come back empty, and Basic gets `403`
for a day that hasn't closed yet; both just step back. It gives up after 7 days.
- price = latest close; `open_price` = the trading day before's close.
- One call covers every US ticker, so a newly added ticker is priced on the next poll with no extra
  request.
- Bars reload when the UTC date changes: about 2–4 calls a day, otherwise no traffic. A trading
  day's close therefore shows up after the next UTC midnight.

**Market closed / EOD data.** Prices don't change between polls. The cache is still rewritten each
poll (`previous_price == price`) and SSE keeps streaming. This is expected behavior, not an error.

**Invalid symbols (R12).** A symbol missing from the response gets no cache entry (`price: null`, the
UI shows "—"). Trades on it are rejected with `400 "No price available for XYZ"`. It stays on the
watchlist.

**Errors.** `429`, `401` (bad key), `5xx`, timeouts, network errors and malformed bodies never crash
the loop:
- The poll interval doubles per consecutive failure, up to 5 minutes, and resets on success.
- The last good prices stay in the cache.
- Each distinct problem is logged once, plus one "recovered" line.

**Security.** The key is sent as `Authorization: Bearer`, never in the URL, so it can't leak into
logs.

**Restart continuity (R14).** Seed prices from past trades are ignored. Massive serves real prices,
so held tickers are valued at `avg_cost` until the first successful poll.

## Tests

`backend/tests/test_massive.py` uses the response bodies in `backend/tests/fixtures/massive/` and a
patched `urlopen`. It makes no network calls. The fixtures follow the documented response shapes.
Replace them with captured responses once someone has a key.
