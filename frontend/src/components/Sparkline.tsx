import type { PricePoint } from "@/lib/priceStore";

/** Inline SVG polyline sparkline (S4) — green if up over the window, red if down. */
export function Sparkline({ points, width = 80, height = 24 }: { points: readonly PricePoint[]; width?: number; height?: number }) {
  if (points.length < 2) {
    return <svg width={width} height={height} aria-hidden data-testid="sparkline" />;
  }
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pad = 1;
  const step = (width - pad * 2) / (points.length - 1);
  const coords = values
    .map((v, i) => `${(pad + i * step).toFixed(1)},${(pad + (height - pad * 2) * (1 - (v - min) / range)).toFixed(1)}`)
    .join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden data-testid="sparkline">
      <polyline points={coords} fill="none" strokeWidth={1.25} strokeLinejoin="round" className={up ? "stroke-up" : "stroke-down"} />
    </svg>
  );
}
