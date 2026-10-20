// Live portfolio math — API_CONTRACT.md §Metric formulas (R17).
import type { Portfolio, Position, PriceEvent } from "./types";

export const STARTING_CASH = 10000;

export type LivePosition = Position;

export type LiveValuation = {
  cash_balance: number;
  positions: LivePosition[];
  positions_value: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
};

/**
 * Recompute valuation from live SSE prices. The authoritative inputs are cash,
 * quantity and avg_cost; a ticker with no live price falls back to avg_cost.
 */
export function liveValuation(portfolio: Portfolio, prices: PriceEvent): LiveValuation {
  const positions = portfolio.positions.map((p) => {
    const price = prices[p.ticker]?.price ?? p.avg_cost;
    return {
      ticker: p.ticker,
      quantity: p.quantity,
      avg_cost: p.avg_cost,
      current_price: price,
      market_value: p.quantity * price,
      unrealized_pnl: (price - p.avg_cost) * p.quantity,
      pnl_pct: p.avg_cost === 0 ? 0 : ((price - p.avg_cost) / p.avg_cost) * 100,
    };
  });
  const positions_value = positions.reduce((sum, p) => sum + p.market_value, 0);
  const total_value = portfolio.cash_balance + positions_value;
  const total_pnl = total_value - STARTING_CASH;
  return {
    cash_balance: portfolio.cash_balance,
    positions,
    positions_value,
    total_value,
    total_pnl,
    total_pnl_pct: (total_pnl / STARTING_CASH) * 100,
  };
}

/** Daily change % vs open_price (R11). */
export function changePct(price: number, openPrice: number): number {
  return openPrice === 0 ? 0 : ((price - openPrice) / openPrice) * 100;
}
