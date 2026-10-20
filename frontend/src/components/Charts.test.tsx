import { render, screen } from "@testing-library/react";
import { chartFor } from "@/test/lightweightCharts";
import { MainChart } from "./MainChart";
import { PnlChart } from "./PnlChart";

describe("MainChart", () => {
  it("prompts for a ticker when none is selected", () => {
    render(<MainChart ticker={null} points={[]} />);
    expect(screen.getByTestId("main-chart")).toHaveTextContent("Select a ticker in the watchlist");
  });

  it("waits for prices, then plots the R28 buffer and re-fits", () => {
    const { rerender } = render(<MainChart ticker="AAPL" points={[]} />);
    expect(screen.getByTestId("main-chart")).toHaveTextContent("Waiting for AAPL prices");
    const chart = chartFor("main-chart-canvas");

    const points = [
      { time: 100, value: 190 },
      { time: 101, value: 191.9 },
    ];
    rerender(<MainChart ticker="AAPL" points={points} />);
    expect(chart.series[0].data).toEqual(points);
    expect(chart.fitContent).toHaveBeenCalled();
    expect(screen.getByTestId("main-chart-canvas")).toHaveAttribute("data-point-count", "2");
    expect(screen.getByTestId("main-chart-price")).toHaveTextContent("191.90");
    expect(screen.getByTestId("main-chart")).toHaveTextContent("+1.00%");
    expect(screen.getByTestId("main-chart")).not.toHaveTextContent("Waiting");
  });

  it("keeps one chart across ticker switches and removes it on unmount", () => {
    const { rerender, unmount } = render(<MainChart ticker="AAPL" points={[{ time: 1, value: 10 }]} />);
    const chart = chartFor("main-chart-canvas");
    rerender(<MainChart ticker="MSFT" points={[{ time: 5, value: 400 }]} />);
    expect(chartFor("main-chart-canvas")).toBe(chart);
    expect(chart.series[0].data).toEqual([{ time: 5, value: 400 }]);
    unmount();
    expect(chart.removed).toBe(true);
  });
});

describe("PnlChart", () => {
  const snapshots = [
    { total_value: 10000, recorded_at: "2026-10-18T14:00:00.000Z" },
    { total_value: 9950, recorded_at: "2026-10-18T14:00:30.000Z" },
  ];

  it("plots snapshots plus the live total", () => {
    render(<PnlChart snapshots={snapshots} liveTotal={10011.4} />);
    const series = chartFor("pnl-chart-canvas").series[0];
    expect(series.data.map((d) => d.value)).toEqual([10000, 9950, 10011.4]);
    expect(screen.getByTestId("pnl-chart-canvas")).toHaveAttribute("data-point-count", "3");
    expect(screen.getByTestId("pnl-chart")).toHaveTextContent("$10,011.40");
    expect(screen.getByTestId("pnl-chart")).toHaveTextContent("+0.11%");
    expect(series.options.color).toBe("#2ea043");
  });

  it("turns red below the starting $10,000", () => {
    render(<PnlChart snapshots={snapshots} liveTotal={9800} />);
    expect(chartFor("pnl-chart-canvas").series[0].options.color).toBe("#da3633");
    expect(screen.getByTestId("pnl-chart")).toHaveTextContent("-2.00%");
  });

  it("shows an empty state with no data", () => {
    render(<PnlChart snapshots={[]} liveTotal={null} />);
    expect(screen.getByTestId("pnl-chart")).toHaveTextContent("No portfolio history yet");
  });
});
