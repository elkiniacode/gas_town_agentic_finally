import type { PricePoint } from "@/lib/priceStore";
import { Panel } from "./Panel";
import { Placeholder } from "./Placeholder";

/**
 * Selected-ticker price chart. PLACEHOLDER — fin-k90.7 replaces the body with a
 * Lightweight Charts line series fed by `points` (the shared R28 buffer).
 */
export function MainChart({ ticker, points, className = "" }: { ticker: string | null; points: readonly PricePoint[]; className?: string }) {
  return (
    <Panel title={ticker ? `${ticker} · Price` : "Price"} testId="main-chart" className={className}>
      <Placeholder owner="fin-k90.7">
        {ticker ? `${points.length} points buffered for ${ticker}` : "Select a ticker in the watchlist"}
      </Placeholder>
    </Panel>
  );
}
