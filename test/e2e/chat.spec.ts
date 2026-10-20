import { expect, test, type Page } from "@playwright/test";
import { heldQuantity, openTerminal, removeFromWatchlist } from "./helpers";

// Mock-mode replies are fixed by API_CONTRACT.md §LLM mock mode.

/** Send a message and return the assistant's reply to it. */
async function send(page: Page, message: string) {
  const panel = page.getByTestId("chat-panel");
  const messages = panel.getByTestId("chat-message");
  // History is shared across tests: wait for it to load, then count from there.
  await expect(panel.getByTestId("chat-empty").or(messages.first())).toBeVisible();
  const before = await messages.count();

  await panel.getByTestId("chat-input").fill(message);
  await panel.getByTestId("chat-send").click();
  await expect(messages).toHaveCount(before + 2);
  await expect(messages.nth(before)).toHaveAttribute("data-role", "user");
  await expect(messages.nth(before)).toContainText(message);
  await expect(panel.getByTestId("chat-loading")).toHaveCount(0);
  return messages.nth(before + 1);
}

test("mocked chat: plain message gets the fixed reply with no actions", async ({ page }) => {
  await openTerminal(page);
  const reply = await send(page, "hello there");
  await expect(reply).toHaveAttribute("data-role", "assistant");
  await expect(reply).toContainText('This is a mock response from FinAlly. Try "buy", "sell", "add XYZ" or "remove XYZ".');
  await expect(reply.getByTestId("chat-actions")).toHaveCount(0);
});

test("mocked chat: buy executes and the trade appears inline", async ({ page, request }) => {
  const held = await heldQuantity(request, "AAPL");
  await openTerminal(page);
  const cash = page.getByTestId("cash-balance");
  const cashBefore = await cash.textContent();

  const reply = await send(page, "please buy");
  await expect(reply).toHaveAttribute("data-role", "assistant");
  await expect(reply).toContainText("Mock response: placing a buy order for 1 AAPL.");
  const action = reply.getByTestId("chat-action");
  await expect(action).toHaveCount(1);
  await expect(action).toHaveAttribute("data-kind", "trade");
  await expect(action).toHaveAttribute("data-status", "ok");
  await expect(action).toHaveText(/✓\s*Succeeded:\s*Buy 1 AAPL @ \$[\d,]+\.\d\d/);

  // The app refetches after chat actions (R29).
  await expect(page.getByTestId("position-row-AAPL").getByTestId("quantity")).toHaveText(String(held + 1));
  await expect(cash).not.toHaveText(cashBefore ?? "");
});

test("mocked chat: watchlist add appears inline and in the watchlist", async ({ page, request }) => {
  await removeFromWatchlist(request, "UBER");
  await openTerminal(page);

  const reply = await send(page, "add uber");
  await expect(reply).toContainText("Mock response: adding UBER to your watchlist.");
  const action = reply.getByTestId("chat-action");
  await expect(action).toHaveAttribute("data-kind", "watchlist");
  await expect(action).toHaveAttribute("data-status", "ok");
  await expect(action).toContainText("Add UBER to watchlist");
  await expect(page.getByTestId("watchlist-row-UBER")).toBeVisible();

  await removeFromWatchlist(request, "UBER");
});

test("mocked chat: failed action shows ✗ with the error", async ({ page, request }) => {
  // Hold no AAPL so the mock's "sell 1 AAPL" must fail.
  const held = await heldQuantity(request, "AAPL");
  if (held > 0) {
    const res = await request.post("/api/portfolio/trade", { data: { ticker: "AAPL", side: "sell", quantity: held } });
    expect(res.status()).toBe(200);
  }
  await openTerminal(page);

  const reply = await send(page, "sell");
  await expect(reply).toContainText("Mock response: placing a sell order for 1 AAPL.");
  const action = reply.getByTestId("chat-action");
  await expect(action).toHaveAttribute("data-status", "failed");
  await expect(action).toContainText("✗");
  await expect(action).toContainText("Insufficient shares: requested 1, held 0");
});
