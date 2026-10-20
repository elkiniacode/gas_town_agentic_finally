import { act, render, screen } from "@testing-library/react";
import { PriceStreamProvider, useConnectionStatus } from "@/lib/usePriceStream";
import type { Portfolio } from "@/lib/types";
import { fakeFactory, tick } from "@/test/fakeEventSource";
import { ConnectionDot } from "./ConnectionDot";
import { Header } from "./Header";

const portfolio: Portfolio = {
  cash_balance: 8099.4,
  positions: [
    { ticker: "AAPL", quantity: 10, avg_cost: 190.06, current_price: 191.2, market_value: 1912, unrealized_pnl: 11.4, pnl_pct: 0.6 },
    { ticker: "NVDA", quantity: 0.5, avg_cost: 400, current_price: 400, market_value: 200, unrealized_pnl: 0, pnl_pct: 0 },
  ],
  positions_value: 2112,
  total_value: 10211.4,
  total_pnl: 211.4,
  total_pnl_pct: 2.11,
};

describe("Header", () => {
  it("computes total value from cash + live prices with avg_cost fallback (R17)", () => {
    // AAPL live at 200 → 2000; NVDA has no live price → 0.5 × 400 = 200.
    render(<Header portfolio={portfolio} prices={{ AAPL: tick(200) }} status="connected" />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,299.40");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$8,099.40");
    expect(screen.getByTestId("total-pnl")).toHaveTextContent("$299.40 (+2.99%)");
    expect(screen.getByTestId("total-pnl")).toHaveClass("text-up");
  });

  it("shows dashes before the portfolio loads", () => {
    render(<Header portfolio={null} prices={{}} status="connecting" />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("—");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("—");
  });
});

describe("Connection indicator driven by EventSource (R38, S9)", () => {
  function Indicator() {
    return <ConnectionDot status={useConnectionStatus()} />;
  }

  it("goes yellow → green on onopen → yellow on onerror → green → red on CLOSED", () => {
    const f = fakeFactory();
    render(
      <PriceStreamProvider eventSourceFactory={f.factory}>
        <Indicator />
      </PriceStreamProvider>,
    );
    const dot = () => screen.getByTestId("connection-status");
    expect(dot()).toHaveAttribute("data-status", "connecting");

    act(() => f.latest().open());
    expect(dot()).toHaveAttribute("data-status", "connected");
    expect(dot()).toHaveTextContent("Live");

    act(() => f.latest().error(0));
    expect(dot()).toHaveAttribute("data-status", "connecting");
    expect(dot()).toHaveTextContent("Reconnecting");

    act(() => f.latest().open());
    expect(dot()).toHaveAttribute("data-status", "connected");

    act(() => f.latest().error(2));
    expect(dot()).toHaveAttribute("data-status", "disconnected");
    expect(dot()).toHaveTextContent("Disconnected");
  });
});
