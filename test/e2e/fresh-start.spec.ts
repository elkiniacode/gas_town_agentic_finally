import { expect, test } from "@playwright/test";
import { FRESH_BASE_URL } from "../playwright.config";
import { DEFAULT_TICKERS, openTerminal } from "./helpers";

// Read-only, against the instance no other test writes to.
test.use({ baseURL: FRESH_BASE_URL });

test("fresh start: default watchlist, $10k, streaming prices", async ({ page }) => {
  await openTerminal(page);

  const rows = page.locator('[data-testid^="watchlist-row-"]');
  await expect(rows).toHaveCount(DEFAULT_TICKERS.length);
  const order = await rows.evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")));
  expect(order).toEqual(DEFAULT_TICKERS.map((t) => `watchlist-row-${t}`));

  await expect(page.getByTestId("cash-balance")).toHaveText("$10,000.00");
  await expect(page.getByTestId("total-value")).toHaveText("$10,000.00");
  await expect(page.getByTestId("heatmap-empty")).toBeVisible();
  await expect(page.getByTestId("positions-empty")).toBeVisible();
  await expect(page.getByTestId("chat-panel")).toBeVisible();

  // Every ticker gets a price, and prices keep moving.
  const prices = page.getByTestId("watchlist").getByTestId("price");
  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watchlist-row-${ticker}`).getByTestId("price")).toHaveText(/^\d+\.\d\d$/);
  }
  const before = await prices.allTextContents();
  await expect.poll(async () => (await prices.allTextContents()).join(" "), { timeout: 10_000 }).not.toBe(before.join(" "));

  // Sparklines fill in from the stream.
  await expect(page.getByTestId("watchlist-row-AAPL").locator('[data-testid="sparkline"] polyline')).toBeAttached();
});
