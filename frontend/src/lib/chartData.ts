// Series builders for the Lightweight Charts panels (PLAN §10).
import type { PricePoint } from "./priceStore";
import type { PortfolioSnapshot } from "./types";

/**
 * P&L chart series: one point per snapshot (unix seconds, strictly ascending as
 * Lightweight Charts requires — a later snapshot in the same second wins), then
 * the live total appended at `nowSec` when it is newer than the last snapshot.
 */
export function pnlSeries(
  snapshots: readonly PortfolioSnapshot[],
  liveTotal: number | null,
  nowSec: number = Math.floor(Date.now() / 1000),
): PricePoint[] {
  const points: PricePoint[] = [];
  const push = (time: number, value: number) => {
    const last = points[points.length - 1];
    if (last && time < last.time) return;
    if (last && time === last.time) points[points.length - 1] = { time, value };
    else points.push({ time, value });
  };
  for (const s of snapshots) {
    const ms = Date.parse(s.recorded_at);
    if (!Number.isNaN(ms)) push(Math.floor(ms / 1000), s.total_value);
  }
  const last = points[points.length - 1];
  if (liveTotal !== null && (!last || nowSec > last.time)) push(nowSec, liveTotal);
  return points;
}
