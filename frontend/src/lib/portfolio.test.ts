import { changePct, liveValuation } from "./portfolio";
import type { Portfolio } from "./types";
import { tick } from "@/test/fakeEventSource";

const portfolio: Portfolio = {
  cash_balance: 8000,
  positions: [
    { ticker: "AAPL", quantity: 10, avg_cost: 100, current_price: 100, market_value: 1000, unrealized_pnl: 0, pnl_pct: 0 },
    { ticker: "TSLA", quantity: 2.5, avg_cost: 200, current_price: 200, market_value: 500, unrealized_pnl: 0, pnl_pct: 0 },
  ],
  positions_value: 1500,
  total_value: 9500,
  total_pnl: -500,
  total_pnl_pct: -5,
};

describe("liveValuation (R17)", () => {
  it("values positions at live prices, falling back to avg_cost", () => {
    const v = liveValuation(portfolio, { AAPL: tick(110) });
    const [aapl, tsla] = v.positions;
    expect(aapl).toMatchObject({ current_price: 110, market_value: 1100, unrealized_pnl: 100, pnl_pct: 10 });
    expect(tsla).toMatchObject({ current_price: 200, market_value: 500, unrealized_pnl: 0, pnl_pct: 0 });
    expect(v.positions_value).toBe(1600);
    expect(v.total_value).toBe(9600);
    expect(v.total_pnl).toBe(-400);
    expect(v.total_pnl_pct).toBe(-4);
  });

  it("is just cash with no positions", () => {
    const v = liveValuation({ ...portfolio, cash_balance: 10000, positions: [] }, {});
    expect(v).toMatchObject({ positions_value: 0, total_value: 10000, total_pnl: 0, total_pnl_pct: 0 });
  });
});

describe("changePct", () => {
  it("is the daily change vs open_price in percentage points", () => {
    expect(changePct(190.12, 189.5)).toBeCloseTo(0.327, 3);
    expect(changePct(90, 100)).toBe(-10);
    expect(changePct(5, 0)).toBe(0);
  });
});
