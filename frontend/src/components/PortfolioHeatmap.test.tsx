import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { heatColor } from "@/lib/heatmap";
import { liveValuation } from "@/lib/portfolio";
import type { Portfolio } from "@/lib/types";
import { tick } from "@/test/fakeEventSource";
import { HEATMAP_EMPTY_TEXT, PortfolioHeatmap } from "./PortfolioHeatmap";

const portfolio: Portfolio = {
  cash_balance: 5000,
  positions: [
    { ticker: "AAPL", quantity: 10, avg_cost: 100, current_price: 100, market_value: 1000, unrealized_pnl: 0, pnl_pct: 0 },
    { ticker: "TSLA", quantity: 5, avg_cost: 200, current_price: 200, market_value: 1000, unrealized_pnl: 0, pnl_pct: 0 },
    { ticker: "NVDA", quantity: 1, avg_cost: 500, current_price: 500, market_value: 500, unrealized_pnl: 0, pnl_pct: 0 },
  ],
  positions_value: 2500,
  total_value: 7500,
  total_pnl: -2500,
  total_pnl_pct: -25,
};

describe("PortfolioHeatmap", () => {
  it("shows the empty-state message with no positions", () => {
    render(<PortfolioHeatmap positions={[]} />);
    expect(screen.getByTestId("heatmap")).toHaveTextContent(HEATMAP_EMPTY_TEXT);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders one tile per position (no cash) with ticker, P&L % and a sign-matched color", () => {
    // AAPL +3%, TSLA -10% (clamps to full red), NVDA flat.
    const live = liveValuation(portfolio, { AAPL: tick(103), TSLA: tick(180), NVDA: tick(500) });
    render(<PortfolioHeatmap positions={live.positions} />);

    const tiles = screen.getAllByTestId(/^heatmap-tile-/);
    expect(tiles.map((t) => t.dataset.testid).sort()).toEqual(["heatmap-tile-AAPL", "heatmap-tile-NVDA", "heatmap-tile-TSLA"]);

    const aapl = screen.getByTestId("heatmap-tile-AAPL");
    expect(aapl).toHaveTextContent("AAPL");
    expect(within(aapl).getByTestId("heatmap-pnl")).toHaveTextContent("+3.00%");
    expect(aapl).toHaveStyle({ backgroundColor: heatColor(3) });

    const tsla = screen.getByTestId("heatmap-tile-TSLA");
    expect(within(tsla).getByTestId("heatmap-pnl")).toHaveTextContent("-10.00%");
    expect(tsla).toHaveStyle({ backgroundColor: "rgb(218, 54, 51)" });

    const nvda = screen.getByTestId("heatmap-tile-NVDA");
    expect(within(nvda).getByTestId("heatmap-pnl")).toHaveTextContent("0.00%");
    expect(nvda).toHaveStyle({ backgroundColor: "rgb(88, 88, 96)" });
  });

  it("sizes tiles by live market value", () => {
    const live = liveValuation(portfolio, {});
    render(<PortfolioHeatmap positions={live.positions} />);
    // Fallback 100×100 layout box: area % = weight × 100 % of the panel.
    const areaPct = (ticker: string) => {
      const s = screen.getByTestId(`heatmap-tile-${ticker}`).style;
      return (parseFloat(s.width) * parseFloat(s.height)) / 100;
    };
    expect(areaPct("AAPL")).toBeCloseTo(40, 5);
    expect(areaPct("TSLA")).toBeCloseTo(40, 5);
    expect(areaPct("NVDA")).toBeCloseTo(20, 5);
  });

  it("selects a ticker when a tile is clicked", async () => {
    const onSelect = vi.fn();
    render(<PortfolioHeatmap positions={liveValuation(portfolio, {}).positions} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId("heatmap-tile-NVDA"));
    expect(onSelect).toHaveBeenCalledWith("NVDA");
  });
});
