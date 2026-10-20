import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/lib/api";
import type { TradeRequest, TradeResponse } from "@/lib/types";
import { TradeBar } from "./TradeBar";

const fill = (req: TradeRequest): TradeResponse => ({
  trade: {
    id: "t1",
    ticker: req.ticker,
    side: req.side,
    quantity: req.quantity,
    price: 190.12,
    total: Math.round(req.quantity * 190.12 * 100) / 100,
    executed_at: "2026-10-18T14:04:02.000Z",
  },
  portfolio: { cash_balance: 0, positions: [], positions_value: 0, total_value: 0, total_pnl: 0, total_pnl_pct: 0 },
});

describe("TradeBar (R31)", () => {
  it("pre-fills the ticker from each watchlist click", () => {
    const { rerender } = render(<TradeBar selection={{ ticker: "AAPL", seq: 1 }} onTraded={vi.fn()} />);
    const ticker = screen.getByLabelText("Trade ticker");
    expect(ticker).toHaveValue("AAPL");
    rerender(<TradeBar selection={{ ticker: "MSFT", seq: 2 }} onTraded={vi.fn()} />);
    expect(ticker).toHaveValue("MSFT");
  });

  it("submits a fractional buy, shows the fill inline and triggers a refetch (R29)", async () => {
    const trade = vi.fn(async (req: TradeRequest) => fill(req));
    const onTraded = vi.fn();
    render(<TradeBar selection={null} onTraded={onTraded} trade={trade} />);
    await userEvent.type(screen.getByLabelText("Trade ticker"), "aapl");
    await userEvent.type(screen.getByLabelText("Trade quantity"), "2.5");
    await userEvent.click(screen.getByRole("button", { name: "Buy" }));
    expect(trade).toHaveBeenCalledWith({ ticker: "AAPL", quantity: 2.5, side: "buy" });
    expect(await screen.findByText("Bought 2.5 AAPL @ $190.12")).toHaveClass("text-up");
    expect(onTraded).toHaveBeenCalledTimes(1);
  });

  it("shows the API detail on failure and does not refetch", async () => {
    const trade = vi.fn(async () => {
      throw new ApiError(400, "Insufficient shares: requested 5, held 0");
    });
    const onTraded = vi.fn();
    render(<TradeBar selection={{ ticker: "AAPL", seq: 1 }} onTraded={onTraded} trade={trade} />);
    await userEvent.type(screen.getByLabelText("Trade quantity"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Sell" }));
    expect(await screen.findByText("Insufficient shares: requested 5, held 0")).toHaveClass("text-down");
    expect(onTraded).not.toHaveBeenCalled();
  });

  it("rejects a zero quantity without calling the API", async () => {
    const trade = vi.fn(async (req: TradeRequest) => fill(req));
    render(<TradeBar selection={{ ticker: "AAPL", seq: 1 }} onTraded={vi.fn()} trade={trade} />);
    await userEvent.type(screen.getByLabelText("Trade quantity"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Buy" }));
    expect(screen.getByTestId("trade-result")).toHaveTextContent("Quantity must be greater than 0");
    expect(trade).not.toHaveBeenCalled();
  });
});
