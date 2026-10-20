"use client";

import { useMemo } from "react";
import { pnlSeries } from "@/lib/chartData";
import { formatPct, formatUsd, signClass } from "@/lib/format";
import { STARTING_CASH } from "@/lib/portfolio";
import type { PortfolioSnapshot } from "@/lib/types";
import { LineChart } from "./LineChart";
import { Panel } from "./Panel";

const UP = "#2ea043"; // --color-up
const DOWN = "#da3633"; // --color-down

/**
 * Total portfolio value over time: `/api/portfolio/history` snapshots (refetched after
 * trades, R29) with the live SSE-valued total appended as the latest point.
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
  const data = useMemo(() => pnlSeries(snapshots, liveTotal), [snapshots, liveTotal]);
  const latest = data[data.length - 1]?.value ?? null;
  const pnlPct = latest === null ? null : ((latest - STARTING_CASH) / STARTING_CASH) * 100;

  return (
    <Panel
      title="Portfolio value"
      testId="pnl-chart"
      className={className}
      bodyClassName="relative"
      actions={
        latest !== null && (
          <span className="flex items-baseline gap-2 font-mono text-xs tabular-nums">
            <span>{formatUsd(latest)}</span>
            <span className={signClass(pnlPct)}>{formatPct(pnlPct)}</span>
          </span>
        )
      }
    >
      <LineChart data={data} color={latest !== null && latest < STARTING_CASH ? DOWN : UP} testId="pnl-chart-canvas" />
      {data.length === 0 && (
        <p className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-muted">
          No portfolio history yet
        </p>
      )}
    </Panel>
  );
}
