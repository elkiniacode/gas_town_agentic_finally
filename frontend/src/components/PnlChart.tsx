import { formatUsd } from "@/lib/format";
import type { PortfolioSnapshot } from "@/lib/types";
import { Panel } from "./Panel";
import { Placeholder } from "./Placeholder";

/**
 * Total portfolio value over time. PLACEHOLDER — fin-k90.7 replaces the body with a
 * Lightweight Charts line of `snapshots` plus `liveTotal` appended as the latest point.
 */
export function PnlChart({
  snapshots,
  liveTotal,
  className = "",
}: {
  snapshots: readonly PortfolioSnapshot[];
  liveTotal: number | null;
  className?: string;
}) {
  return (
    <Panel title="Portfolio value" testId="pnl-chart" className={className}>
      <Placeholder owner="fin-k90.7">
        {snapshots.length} snapshot{snapshots.length === 1 ? "" : "s"}
        {liveTotal !== null && ` · live ${formatUsd(liveTotal)}`}
      </Placeholder>
    </Panel>
  );
}
