import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";

export const DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];

type Position = { ticker: string; quantity: number; avg_cost: number };
type Portfolio = { cash_balance: number; positions: Position[]; total_value: number };

/** "$10,000.00" / "-$4.00" / "+$1.20" → number. */
export function parseUsd(text: string): number {
  const n = Number(text.replace(/[$,+\s]/g, ""));
  if (!Number.isFinite(n)) throw new Error(`Not a dollar amount: ${JSON.stringify(text)}`);
  return n;
}

export async function readUsd(locator: Locator): Promise<number> {
  return parseUsd((await locator.textContent()) ?? "");
}

/** Open the terminal and wait until the portfolio has loaded and the price stream is connected. */
export async function openTerminal(page: Page, url = "/"): Promise<void> {
  await page.goto(url);
  await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
  await expect(page.getByTestId("cash-balance")).toHaveText(/^\$[\d,]+\.\d\d$/);
}

// --- API setup helpers: let a test establish its own starting state (R36) ---

export async function getPortfolio(request: APIRequestContext): Promise<Portfolio> {
  const res = await request.get("/api/portfolio");
  expect(res.status()).toBe(200);
  return res.json();
}

export async function heldQuantity(request: APIRequestContext, ticker: string): Promise<number> {
  return (await getPortfolio(request)).positions.find((p) => p.ticker === ticker)?.quantity ?? 0;
}

export async function apiTrade(request: APIRequestContext, ticker: string, side: "buy" | "sell", quantity: number) {
  const res = await request.post("/api/portfolio/trade", { data: { ticker, side, quantity } });
  expect(res.status(), await res.text()).toBe(200);
  return res.json();
}

export async function removeFromWatchlist(request: APIRequestContext, ticker: string): Promise<void> {
  const res = await request.delete(`/api/watchlist/${ticker}`);
  expect(res.status()).toBe(200);
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Same formatting as the app's header and trade results. */
export const formatUsd = (n: number): string => usd.format(n);

/** Cents-exact a − b for 2 dp money values. */
export const subUsd = (a: number, b: number): number => Math.round((a - b) * 100) / 100;

/** "Bought 2 MSFT @ $412.34" → 412.34 */
export function tradePrice(resultText: string): number {
  const m = /@ (\$[\d,]+\.\d\d)$/.exec(resultText.trim());
  if (!m) throw new Error(`No price in trade result: ${JSON.stringify(resultText)}`);
  return parseUsd(m[1]);
}

/** Buy or sell through the trade bar and return the fill price shown inline. */
export async function tradeViaUi(page: Page, ticker: string, side: "buy" | "sell", quantity: number): Promise<number> {
  const bar = page.getByTestId("trade-bar");
  await bar.getByLabel("Trade ticker").fill(ticker);
  await bar.getByLabel("Trade quantity").fill(String(quantity));
  await bar.getByRole("button", { name: side === "buy" ? "Buy" : "Sell", exact: true }).click();
  const verb = side === "buy" ? "Bought" : "Sold";
  const result = bar.getByTestId("trade-result");
  await expect(result).toHaveText(new RegExp(`^${verb} ${quantity} ${ticker} @ \\$[\\d,]+\\.\\d\\d$`));
  return tradePrice((await result.textContent()) ?? "");
}
