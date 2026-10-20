"use client";

import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { formatPct, formatUsd, roundPct } from "@/lib/format";
import { heatColor, layoutHeatmap } from "@/lib/heatmap";
import type { LivePosition } from "@/lib/portfolio";
import { Panel } from "./Panel";

export const HEATMAP_EMPTY_TEXT = "No positions yet — buy something to see your heatmap.";

/** Layout box before the container has been measured (tiles are placed in %, so only the aspect matters). */
const FALLBACK_SIZE = { width: 100, height: 100 };

function useElementSize(ref: RefObject<HTMLElement | null>) {
  const [size, setSize] = useState(FALLBACK_SIZE);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

/**
 * Treemap of positions (R30): d3-hierarchy squarified layout rendered as plain divs,
 * area ∝ live market value, color by P&L % (±5% clamp, red → gray → green). No cash tile.
 */
export function PortfolioHeatmap({
  positions,
  onSelect,
  className = "",
}: {
  positions: readonly LivePosition[];
  onSelect?: (ticker: string) => void;
  className?: string;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const { width, height } = useElementSize(boxRef);
  const tiles = useMemo(() => layoutHeatmap(positions, width, height), [positions, width, height]);

  return (
    <Panel title="Heatmap" testId="heatmap" className={className} bodyClassName="p-1">
      <div ref={boxRef} className="relative h-full w-full">
        {tiles.length === 0 ? (
          <p
            data-testid="heatmap-empty"
            className="flex h-full items-center justify-center p-4 text-center text-xs text-muted"
          >
            {HEATMAP_EMPTY_TEXT}
          </p>
        ) : (
          tiles.map((t) => {
            // Color from the displayed (2 dp) value so the tile's color always matches its text's sign.
            const pct = roundPct(t.pnl_pct);
            return (
              <button
                key={t.ticker}
                type="button"
                data-testid={`heatmap-tile-${t.ticker}`}
                data-pnl-pct={pct.toFixed(2)}
                onClick={() => onSelect?.(t.ticker)}
                title={`${t.ticker} · ${formatUsd(t.market_value)} · ${(t.weight * 100).toFixed(1)}% of positions · ${formatPct(pct)}`}
                className="absolute flex flex-col items-center justify-center overflow-hidden rounded-sm border border-bg/70 text-white transition-[left,top,width,height] duration-300 hover:brightness-110"
                style={{
                  left: `${(t.x0 / width) * 100}%`,
                  top: `${(t.y0 / height) * 100}%`,
                  width: `${((t.x1 - t.x0) / width) * 100}%`,
                  height: `${((t.y1 - t.y0) / height) * 100}%`,
                  backgroundColor: heatColor(pct),
                }}
              >
                <span className="font-mono text-xs font-semibold leading-tight">{t.ticker}</span>
                <span data-testid="heatmap-pnl" className="font-mono text-[11px] leading-tight tabular-nums opacity-90">
                  {formatPct(pct)}
                </span>
              </button>
            );
          })
        )}
      </div>
    </Panel>
  );
}
