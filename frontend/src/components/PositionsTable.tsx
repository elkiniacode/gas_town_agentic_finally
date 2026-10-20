"use client";

import { formatPct, formatPrice, formatQty, formatSignedUsd, signClass } from "@/lib/format";
import type { LivePosition } from "@/lib/portfolio";
import { Panel } from "./Panel";
import { PriceCell } from "./PriceCell";

const COLUMNS = ["Ticker", "Qty", "Avg cost", "Price", "Unrealized P&L", "P&L %"] as const;

/** Ticker, quantity, avg cost, live price, unrealized P&L, P&L % (R18), green/red by sign. */
export function PositionsTable({
  positions,
  onSelect,
  className = "",
}: {
  positions: readonly LivePosition[];
  onSelect?: (ticker: string) => void;
  className?: string;
}) {
  return (
    <Panel title="Positions" testId="positions" className={className} bodyClassName="overflow-auto">
      {positions.length === 0 ? (
        <p data-testid="positions-empty" className="flex h-full items-center justify-center p-4 text-xs text-muted">
          No open positions
        </p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-panel">
            <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
              {COLUMNS.map((c, i) => (
                <th key={c} scope="col" className={`px-3 py-1.5 font-semibold ${i === 0 ? "text-left" : "text-right"}`}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {positions.map((p) => {
              const tone = signClass(p.unrealized_pnl);
              return (
                <tr
                  key={p.ticker}
                  data-testid={`position-row-${p.ticker}`}
                  onClick={() => onSelect?.(p.ticker)}
                  className={`border-b border-border/60 hover:bg-panel-2 ${onSelect ? "cursor-pointer" : ""}`}
                >
                  <th scope="row" className="px-3 py-1 text-left font-semibold">
                    {p.ticker}
                  </th>
                  <td data-testid="quantity" className="px-3 py-1 text-right">
                    {formatQty(p.quantity)}
                  </td>
                  <td data-testid="avg-cost" className="px-3 py-1 text-right">
                    {formatPrice(p.avg_cost)}
                  </td>
                  <td className="px-2 py-1 text-right">
                    <PriceCell price={p.current_price} />
                  </td>
                  <td data-testid="unrealized-pnl" className={`px-3 py-1 text-right ${tone}`}>
                    {formatSignedUsd(p.unrealized_pnl)}
                  </td>
                  <td data-testid="pnl-pct" className={`px-3 py-1 text-right ${tone}`}>
                    {formatPct(p.pnl_pct)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
