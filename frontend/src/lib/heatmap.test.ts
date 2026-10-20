import { heatColor, layoutHeatmap } from "./heatmap";
import type { LivePosition } from "./portfolio";

const rgb = (s: string) => s.match(/\d+/g)!.map(Number);

function pos(ticker: string, market_value: number, pnl_pct = 0): LivePosition {
  return { ticker, quantity: 1, avg_cost: market_value, current_price: market_value, market_value, unrealized_pnl: 0, pnl_pct };
}

describe("heatColor (API_CONTRACT §Heatmap color scale)", () => {
  it("hits the contract colors at 0 and ±5", () => {
    expect(heatColor(0)).toBe("rgb(88, 88, 96)");
    expect(heatColor(-5)).toBe("rgb(218, 54, 51)");
    expect(heatColor(5)).toBe("rgb(46, 160, 67)");
  });

  it("clamps beyond ±5%", () => {
    expect(heatColor(-42)).toBe(heatColor(-5));
    expect(heatColor(12.5)).toBe(heatColor(5));
  });

  it("interpolates linearly toward red or green", () => {
    expect(heatColor(-2.5)).toBe("rgb(153, 71, 74)"); // halfway gray → red
    expect(heatColor(2.5)).toBe("rgb(67, 124, 82)"); // halfway gray → green
  });

  it("encodes the sign: positive G > R, negative R > G, zero R = G", () => {
    for (const pct of [0.05, 0.5, 1, 3, 5, 9]) {
      const [r, g] = rgb(heatColor(pct));
      expect(g).toBeGreaterThan(r);
    }
    for (const pct of [-0.05, -0.5, -1, -3, -5, -9]) {
      const [r, g] = rgb(heatColor(pct));
      expect(r).toBeGreaterThan(g);
    }
    // |P&L %| below ~0.04 rounds to the neutral gray ("gray for ~0").
    for (const pct of [0, 0.01, -0.01]) {
      const [r, g] = rgb(heatColor(pct));
      expect(r).toBe(g);
    }
  });
});

describe("layoutHeatmap", () => {
  const area = (t: { x0: number; y0: number; x1: number; y1: number }) => (t.x1 - t.x0) * (t.y1 - t.y0);

  it("returns no tiles without positions (no cash tile)", () => {
    expect(layoutHeatmap([], 300, 200)).toEqual([]);
  });

  it("sizes tiles by market value weight and fills the box", () => {
    const tiles = layoutHeatmap([pos("AAPL", 600, 1.5), pos("TSLA", 300, -2), pos("NVDA", 100)], 300, 200);
    expect(tiles.map((t) => t.ticker).sort()).toEqual(["AAPL", "NVDA", "TSLA"]);
    const byTicker = Object.fromEntries(tiles.map((t) => [t.ticker, t]));
    expect(byTicker.AAPL.weight).toBeCloseTo(0.6);
    expect(byTicker.TSLA.weight).toBeCloseTo(0.3);
    expect(byTicker.NVDA.weight).toBeCloseTo(0.1);
    for (const t of tiles) {
      expect(area(t) / (300 * 200)).toBeCloseTo(t.weight, 5);
      expect(t.x0).toBeGreaterThanOrEqual(0);
      expect(t.y0).toBeGreaterThanOrEqual(0);
      expect(t.x1).toBeLessThanOrEqual(300 + 1e-9);
      expect(t.y1).toBeLessThanOrEqual(200 + 1e-9);
    }
    expect(byTicker.AAPL.pnl_pct).toBe(1.5);
    expect(byTicker.TSLA.pnl_pct).toBe(-2);
  });

  it("gives a single position the whole box", () => {
    const [t] = layoutHeatmap([pos("AAPL", 1234.5, 0.6)], 120, 80);
    expect(t).toMatchObject({ ticker: "AAPL", weight: 1, x0: 0, y0: 0, x1: 120, y1: 80 });
  });

  it("skips positions with no market value", () => {
    expect(layoutHeatmap([pos("AAPL", 0)], 100, 100)).toEqual([]);
  });
});
