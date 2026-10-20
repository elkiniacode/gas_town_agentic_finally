import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { liveValuation } from "@/lib/portfolio";
import type { Portfolio } from "@/lib/types";
import { tick } from "@/test/fakeEventSource";
import { PositionsTable } from "./PositionsTable";

const portfolio: Portfolio = {
  cash_balance: 7000,
  positions: [
    { ticker: "AAPL", quantity: 10, avg_cost: 190.06, current_price: 190.06, market_value: 1900.6, unrealized_pnl: 0, pnl_pct: 0 },
    { ticker: "TSLA", quantity: 2.5, avg_cost: 200, current_price: 200, market_value: 500, unrealized_pnl: 0, pnl_pct: 0 },
    { ticker: "V", quantity: 1, avg_cost: 250, current_price: 250, market_value: 250, unrealized_pnl: 0, pnl_pct: 0 },
  ],
  positions_value: 2650.6,
  total_value: 9650.6,
  total_pnl: -349.4,
  total_pnl_pct: -3.49,
};

describe("PositionsTable rendering with mock data", () => {
  it("shows an empty state with no positions", () => {
    render(<PositionsTable positions={[]} />);
    expect(screen.getByTestId("positions")).toHaveTextContent("No open positions");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("renders the R18 columns with live values and sign coloring", () => {
    const live = liveValuation(portfolio, { AAPL: tick(191.2), TSLA: tick(190) });
    render(<PositionsTable positions={live.positions} />);

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Ticker", "Qty", "Avg cost", "Price", "Unrealized P&L", "P&L %"]);

    const aapl = screen.getByTestId("position-row-AAPL");
    expect(within(aapl).getByRole("rowheader")).toHaveTextContent("AAPL");
    expect(within(aapl).getByTestId("quantity")).toHaveTextContent("10");
    expect(within(aapl).getByTestId("avg-cost")).toHaveTextContent("190.06");
    expect(within(aapl).getByTestId("price")).toHaveTextContent("191.20");
    expect(within(aapl).getByTestId("unrealized-pnl")).toHaveTextContent("+$11.40");
    expect(within(aapl).getByTestId("pnl-pct")).toHaveTextContent("+0.60%");
    expect(within(aapl).getByTestId("pnl-pct")).toHaveClass("text-up");

    const tsla = screen.getByTestId("position-row-TSLA");
    expect(within(tsla).getByTestId("quantity")).toHaveTextContent("2.5");
    expect(within(tsla).getByTestId("unrealized-pnl")).toHaveTextContent("-$25.00");
    expect(within(tsla).getByTestId("unrealized-pnl")).toHaveClass("text-down");
    expect(within(tsla).getByTestId("pnl-pct")).toHaveTextContent("-5.00%");

    // No live price: valued at avg_cost, flat and neutral.
    const v = screen.getByTestId("position-row-V");
    expect(within(v).getByTestId("price")).toHaveTextContent("250.00");
    expect(within(v).getByTestId("unrealized-pnl")).toHaveTextContent("$0.00");
    expect(within(v).getByTestId("pnl-pct")).toHaveTextContent("0.00%");
    expect(within(v).getByTestId("pnl-pct")).toHaveClass("text-muted");
  });

  it("updates the live price in place", () => {
    const { rerender } = render(<PositionsTable positions={liveValuation(portfolio, { AAPL: tick(191.2) }).positions} />);
    rerender(<PositionsTable positions={liveValuation(portfolio, { AAPL: tick(189) }).positions} />);
    const aapl = screen.getByTestId("position-row-AAPL");
    expect(within(aapl).getByTestId("price")).toHaveTextContent("189.00");
    expect(within(aapl).getByTestId("unrealized-pnl")).toHaveTextContent("-$10.60");
  });

  it("selects a ticker when a row is clicked", async () => {
    const onSelect = vi.fn();
    render(<PositionsTable positions={liveValuation(portfolio, {}).positions} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId("position-row-TSLA"));
    expect(onSelect).toHaveBeenCalledWith("TSLA");
  });
});
