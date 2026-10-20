"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  LineSeries,
  TickMarkType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { PricePoint } from "@/lib/priceStore";

// Theme tokens from globals.css; the canvas can't read CSS variables.
const MUTED = "#8b949e";
const BORDER = "#30363d";
const GRID = "rgba(48, 54, 61, 0.45)";
const FONT = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace';

const toDate = (t: Time) => new Date((t as number) * 1000);
const two = (n: number) => String(n).padStart(2, "0");
const hhmm = (d: Date) => `${two(d.getHours())}:${two(d.getMinutes())}`;

/** Axis labels in the viewer's local time (Lightweight Charts formats UTC by default). */
function tickMark(time: Time, type: TickMarkType): string {
  const d = toDate(time);
  switch (type) {
    case TickMarkType.Year:
      return String(d.getFullYear());
    case TickMarkType.Month:
      return d.toLocaleString("en-US", { month: "short" });
    case TickMarkType.DayOfMonth:
      return d.toLocaleString("en-US", { month: "short", day: "numeric" });
    case TickMarkType.TimeWithSeconds:
      return `${hhmm(d)}:${two(d.getSeconds())}`;
    default:
      return hhmm(d);
  }
}

const crosshairTime = (time: Time) => {
  const d = toDate(time);
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${hhmm(d)}:${two(d.getSeconds())}`;
};

/**
 * Canvas line chart (TradingView Lightweight Charts) that always shows all of `data`.
 * `data` must be strictly ascending by `time` (unix seconds). User scroll/zoom is off:
 * every update re-fits the whole series. `data-point-count` exposes the series length
 * for E2E checks, since the canvas itself can't be inspected.
 */
export function LineChart({
  data,
  color,
  secondsVisible = false,
  testId,
}: {
  data: readonly PricePoint[];
  color: string;
  secondsVisible?: boolean;
  testId?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    const chart = createChart(containerRef.current!, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: MUTED,
        fontFamily: FONT,
        fontSize: 11,
      },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      rightPriceScale: { borderColor: BORDER },
      timeScale: { borderColor: BORDER, timeVisible: true, tickMarkFormatter: tickMark },
      localization: { timeFormatter: crosshairTime },
      handleScroll: false,
      handleScale: false,
    });
    chartRef.current = chart;
    seriesRef.current = chart.addSeries(LineSeries, { lineWidth: 2 });
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.applyOptions({ timeScale: { secondsVisible } });
  }, [secondsVisible]);

  useEffect(() => {
    seriesRef.current?.applyOptions({ color });
  }, [color]);

  useEffect(() => {
    seriesRef.current?.setData(data.map((p) => ({ time: p.time as UTCTimestamp, value: p.value }) satisfies LineData));
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={containerRef} data-testid={testId} data-point-count={data.length} className="absolute inset-0" />;
}
