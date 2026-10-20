import { expect, test } from "@playwright/test";
import { openTerminal, removeFromWatchlist } from "./helpers";

const TICKER = "PYPL";

test("add and remove a ticker from the watchlist", async ({ page, request }) => {
  await removeFromWatchlist(request, TICKER);
  await openTerminal(page);

  const row = page.getByTestId(`watchlist-row-${TICKER}`);
  await expect(row).toHaveCount(0);

  // Add: the row appears and the simulator prices it immediately.
  const input = page.getByLabel("Ticker to add");
  await input.fill(TICKER.toLowerCase());
  await expect(input).toHaveValue(TICKER);
  await page.getByTestId("watchlist").getByRole("button", { name: "Add", exact: true }).click();
  await expect(row).toBeVisible();
  await expect(input).toHaveValue("");
  await expect(row.getByTestId("price")).toHaveText(/^\d+\.\d\d$/);

  // Persisted server-side.
  await page.reload();
  await expect(row).toBeVisible();

  // Remove.
  await row.getByRole("button", { name: `Remove ${TICKER}` }).click();
  await expect(row).toHaveCount(0);
  await page.reload();
  await expect(page.locator('[data-testid^="watchlist-row-"]').first()).toBeVisible();
  await expect(row).toHaveCount(0);
});

test("invalid ticker shows the API error inline", async ({ page }) => {
  await openTerminal(page);
  await page.getByLabel("Ticker to add").fill("AB1");
  await page.getByTestId("watchlist").getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByTestId("watchlist").getByRole("alert")).toHaveText(/^Invalid ticker/);
});
