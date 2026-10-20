import { expect, test } from "@playwright/test";
import { apiTrade, openTerminal } from "./helpers";

/** API_CONTRACT.md §Heatmap color scale. */
const RED = [218, 54, 51];
const GRAY = [88, 88, 96];
const GREEN = [46, 160, 67];
function heatColor(pnlPct: number): string {
  const t = Math.max(-5, Math.min(5, pnlPct)) / 5;
  const target = t < 0 ? RED : GREEN;
  const k = Math.abs(t);
  const [r, g, b] = GRAY.map((c, i) => Math.round(c + (target[i] - c) * k));
  return `rgb(${r}, ${g}, ${b})`;
}

type TileSample = { ticker: string; text: string; color: string };

test("heatmap tiles are colored by the sign of their P&L %, P&L chart has points", async ({ page, request }) => {
  const tickers = ["NVDA", "V"];
  for (const t of tickers) await apiTrade(request, t, "buy", 1);
  await openTerminal(page);

  for (const t of tickers) await expect(page.getByTestId(`heatmap-tile-${t}`)).toBeVisible();

  // Prices stream, so sample for a few seconds. Text and color are read in one
  // evaluate so both come from the same render.
  const samples: TileSample[] = [];
  for (let i = 0; i < 6; i++) {
    samples.push(
      ...(await page.locator('[data-testid^="heatmap-tile-"]').evaluateAll((tiles) =>
        tiles.map((el) => ({
          ticker: el.getAttribute("data-testid")!.replace("heatmap-tile-", ""),
          text: el.querySelector('[data-testid="heatmap-pnl"]')!.textContent ?? "",
          color: getComputedStyle(el).backgroundColor,
        })),
      )),
    );
    await page.waitForTimeout(1000);
  }

  for (const t of tickers) expect(samples.some((s) => s.ticker === t)).toBe(true);
  for (const { ticker, text, color } of samples) {
    const label = `${ticker} ${text} ${color}`;
    expect(text, label).toMatch(/^[+-]?\d+\.\d\d%$/);
    const pct = Number(text.replace("%", ""));
    const [r, g, b] = color.match(/\d+/g)!.map(Number);

    // Sign rule (R36): green-ish when positive, red-ish when negative, gray at ~0.
    // Below ~0.04% the contract's scale rounds to exact gray, which counts as ~0.
    if (pct > 0) expect(g >= r && r <= GRAY[0], label).toBe(true);
    else if (pct < 0) expect(r >= g && g <= GRAY[1], label).toBe(true);
    else expect([r, g, b], label).toEqual(GRAY);
    if (Math.abs(pct) >= 0.05) expect(pct > 0 ? g > r : r > g, label).toBe(true);

    // And exactly the contract's color for the displayed value.
    expect(color, label).toBe(heatColor(pct));
  }

  // Seed snapshot + the snapshots recorded by the trades above, plus the live point.
  const pnl = page.getByTestId("pnl-chart-canvas");
  await expect.poll(async () => Number(await pnl.getAttribute("data-point-count"))).toBeGreaterThanOrEqual(2);
  await expect(pnl.locator("canvas").first()).toBeVisible();
});
