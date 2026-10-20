import type { LivePosition } from "@/lib/portfolio";
import { Panel } from "./Panel";
import { Placeholder } from "./Placeholder";

/**
 * Ticker, quantity, avg cost, current price, unrealized P&L, P&L % (R18).
 * PLACEHOLDER — fin-k90.7 replaces the body with the table of live-valued `positions`.
 */
export function PositionsTable({ positions, className = "" }: { positions: readonly LivePosition[]; className?: string }) {
  return (
    <Panel title="Positions" testId="positions" className={className}>
      <Placeholder owner="fin-k90.7">
        {positions.length === 0 ? "No open positions" : positions.map((p) => p.ticker).join(" · ")}
      </Placeholder>
    </Panel>
  );
}
