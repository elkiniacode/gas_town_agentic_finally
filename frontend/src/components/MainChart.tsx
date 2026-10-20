"use client";

import { formatPct, formatPrice, signClass } from "@/lib/format";
import type { PricePoint } from "@/lib/priceStore";
import { LineChart } from "./LineChart";
import { Panel } from "./Panel";

const LINE_COLOR = "#209dd7"; // --color-primary

/**
 * Selected-ticker price chart: the shared R28 buffer (1-second buckets since page load),
 * so it starts empty after a reload and fills in progressively.
 */
export function MainChart({ ticker, points, className = "" }: { ticker: string | null; points: readonly PricePoint[]; className?: string }) {
  const first = points[0];
  const last = points[points.length - 1];
  const movePct = first && last && first.value !== 0 ? ((last.value - first.value) / first.value) * 100 : null;

  return (
    <Panel
      title={ticker ? `${ticker} · Price` : "Price"}
      testId="main-chart"
      className={className}
      bodyClassName="relative"
      actions={
        last && (
          <span className="flex items-baseline gap-2 font-mono text-xs tabular-nums">
            <span data-testid="main-chart-price">{formatPrice(last.value)}</span>
            <span className={signClass(movePct)} title="Change since page load">
              {formatPct(movePct)}
            </span>
          </span>
        )
      }
    >
      <LineChart data={points} color={LINE_COLOR} secondsVisible testId="main-chart-canvas" />
      {points.length === 0 && (
        <p className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-muted">
          {ticker ? `Waiting for ${ticker} prices…` : "Select a ticker in the watchlist"}
        </p>
      )}
    </Panel>
  );
}
