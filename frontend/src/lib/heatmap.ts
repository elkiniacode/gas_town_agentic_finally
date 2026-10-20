// Portfolio heatmap math — API_CONTRACT.md §Heatmap color scale (R30).
import { hierarchy, treemap, treemapSquarify } from "d3-hierarchy";
import type { LivePosition } from "./portfolio";

type Rgb = readonly [number, number, number];

const RED: Rgb = [218, 54, 51];
const GRAY: Rgb = [88, 88, 96];
const GREEN: Rgb = [46, 160, 67];

/** P&L % beyond which the tile color saturates. */
export const HEAT_CLAMP_PCT = 5;

/** Tile color: P&L % clamped to ±5, interpolated gray → red (negative) / green (positive). */
export function heatColor(pnlPct: number): string {
  const t = Math.max(-HEAT_CLAMP_PCT, Math.min(HEAT_CLAMP_PCT, pnlPct)) / HEAT_CLAMP_PCT;
  const target = t < 0 ? RED : GREEN;
  const k = Math.abs(t);
  const [r, g, b] = GRAY.map((c, i) => Math.round(c + (target[i] - c) * k));
  return `rgb(${r}, ${g}, ${b})`;
}

export type HeatTile = {
  ticker: string;
  pnl_pct: number;
  market_value: number;
  /** market_value / positions_value (0..1). */
  weight: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

type TreeNode = { position?: LivePosition; children?: TreeNode[] };

/**
 * Squarified treemap of positions in a `width` × `height` box, area ∝ market value.
 * Cash is never a tile; positions with no market value are skipped.
 */
export function layoutHeatmap(positions: readonly LivePosition[], width: number, height: number): HeatTile[] {
  const valued = positions.filter((p) => p.market_value > 0);
  const total = valued.reduce((sum, p) => sum + p.market_value, 0);
  if (total <= 0 || width <= 0 || height <= 0) return [];

  const root = hierarchy<TreeNode>({ children: valued.map((position) => ({ position })) })
    .sum((d) => d.position?.market_value ?? 0)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const laidOut = treemap<TreeNode>().tile(treemapSquarify).size([width, height]).round(false)(root);

  return laidOut.leaves().map((leaf) => {
    const p = leaf.data.position!;
    return {
      ticker: p.ticker,
      pnl_pct: p.pnl_pct,
      market_value: p.market_value,
      weight: p.market_value / total,
      x0: leaf.x0,
      y0: leaf.y0,
      x1: leaf.x1,
      y1: leaf.y1,
    };
  });
}
