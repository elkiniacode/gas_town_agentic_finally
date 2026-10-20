import { expect, test } from "@playwright/test";
import { apiTrade, formatUsd, heldQuantity, openTerminal, readUsd, subUsd, tradeViaUi } from "./helpers";

// Each test trades its own ticker and measures against its own baseline (R36).

test("buy shares: cash decreases, position appears, portfolio updates", async ({ page, request }) => {
  const ticker = "MSFT";
  const held = await heldQuantity(request, ticker);
  await openTerminal(page);

  // Clicking a watchlist ticker pre-fills the trade bar (R31).
  await page.getByTestId(`watchlist-row-${ticker}`).click();
  await expect(page.getByTestId("trade-bar").getByLabel("Trade ticker")).toHaveValue(ticker);

  const cash = page.getByTestId("cash-balance");
  const cashBefore = await readUsd(cash);
  const price = await tradeViaUi(page, ticker, "buy", 2);

  await expect(cash).toHaveText(formatUsd(subUsd(cashBefore, Math.round(2 * price * 100) / 100)));
  const row = page.getByTestId(`position-row-${ticker}`);
  await expect(row).toBeVisible();
  await expect(row.getByTestId("quantity")).toHaveText(String(held + 2));
  await expect(page.getByTestId(`heatmap-tile-${ticker}`)).toBeVisible();
  expect(await heldQuantity(request, ticker)).toBe(held + 2);
});

test("sell shares: cash increases, position updates, then disappears", async ({ page, request }) => {
  const ticker = "JPM";
  await apiTrade(request, ticker, "buy", 3);
  const held = await heldQuantity(request, ticker);
  await openTerminal(page);

  const cash = page.getByTestId("cash-balance");
  const row = page.getByTestId(`position-row-${ticker}`);
  await expect(row.getByTestId("quantity")).toHaveText(String(held));

  // Partial sell: the position shrinks.
  let cashBefore = await readUsd(cash);
  let price = await tradeViaUi(page, ticker, "sell", 1);
  await expect(cash).toHaveText(formatUsd(subUsd(cashBefore, -price)));
  await expect(row.getByTestId("quantity")).toHaveText(String(held - 1));

  // Sell the rest: the position and its heatmap tile disappear.
  cashBefore = await readUsd(cash);
  price = await tradeViaUi(page, ticker, "sell", held - 1);
  await expect(cash).toHaveText(formatUsd(subUsd(cashBefore, -Math.round((held - 1) * price * 100) / 100)));
  await expect(row).toHaveCount(0);
  await expect(page.getByTestId(`heatmap-tile-${ticker}`)).toHaveCount(0);
  expect(await heldQuantity(request, ticker)).toBe(0);
});

test("selling more than held shows the API error inline", async ({ page, request }) => {
  const ticker = "NFLX";
  const held = await heldQuantity(request, ticker);
  await openTerminal(page);

  const cash = page.getByTestId("cash-balance");
  const cashBefore = await cash.textContent();
  const bar = page.getByTestId("trade-bar");
  await bar.getByLabel("Trade ticker").fill(ticker);
  await bar.getByLabel("Trade quantity").fill(String(held + 1));
  await bar.getByRole("button", { name: "Sell", exact: true }).click();
  await expect(bar.getByTestId("trade-result")).toHaveText(/^Insufficient shares/);
  await expect(cash).toHaveText(cashBefore ?? "");
});
