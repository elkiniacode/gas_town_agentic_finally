import type { LivePosition } from "@/lib/portfolio";
import { Panel } from "./Panel";
import { Placeholder } from "./Placeholder";

export const HEATMAP_EMPTY_TEXT = "No positions yet — buy something to see your heatmap.";

/**
 * Treemap of positions (R30). PLACEHOLDER — fin-k90.7 replaces the body with
 * d3-hierarchy tiles sized by market value and colored by pnl_pct.
 */
export function PortfolioHeatmap({ positions, className = "" }: { positions: readonly LivePosition[]; className?: string }) {
  return (
    <Panel title="Heatmap" testId="heatmap" className={className}>
      <Placeholder owner="fin-k90.7">
        {positions.length === 0 ? HEATMAP_EMPTY_TEXT : `${positions.length} position${positions.length === 1 ? "" : "s"}`}
      </Placeholder>
    </Panel>
  );
}
