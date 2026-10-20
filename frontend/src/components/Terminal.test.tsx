import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/api";
import { AppDataProvider } from "@/lib/useAppData";
import { PriceStreamProvider } from "@/lib/usePriceStream";
import { fakeFactory, tick } from "@/test/fakeEventSource";
import { HEATMAP_EMPTY_TEXT } from "./PortfolioHeatmap";
import { Terminal } from "./Terminal";

function mockApi() {
  vi.spyOn(api, "getPortfolio").mockResolvedValue({
    cash_balance: 10000,
    positions: [],
    positions_value: 0,
    total_value: 10000,
    total_pnl: 0,
    total_pnl_pct: 0,
  });
  vi.spyOn(api, "getWatchlist").mockResolvedValue({
    watchlist: ["AAPL", "GOOGL"].map((ticker) => ({
      ticker,
      price: 100,
      previous_price: 100,
      open_price: 100,
      change_pct: 0,
      added_at: "2026-10-18T14:00:00.000Z",
    })),
  });
  vi.spyOn(api, "getPortfolioHistory").mockResolvedValue({
    snapshots: [{ total_value: 10000, recorded_at: "2026-10-18T14:00:00.000Z" }],
  });
}

function renderTerminal() {
  const f = fakeFactory();
  render(
    <PriceStreamProvider eventSourceFactory={f.factory}>
      <AppDataProvider>
        <Terminal />
      </AppDataProvider>
    </PriceStreamProvider>,
  );
  return f;
}

describe("Terminal layout", () => {
  beforeEach(mockApi);
  afterEach(() => vi.restoreAllMocks());

  it("renders every slot with fresh-start data", async () => {
    renderTerminal();
    expect(await screen.findByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,000.00");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$10,000.00");
    for (const id of ["main-chart", "heatmap", "pnl-chart", "positions", "trade-bar", "chat-sidebar", "chat-panel"]) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }
    expect(screen.getByTestId("heatmap")).toHaveTextContent(HEATMAP_EMPTY_TEXT);
    // Main chart defaults to the first watchlist ticker.
    expect(screen.getByTestId("main-chart")).toHaveTextContent("AAPL");
  });

  it("streams prices into the watchlist and selects tickers into chart + trade bar", async () => {
    const f = renderTerminal();
    await screen.findByTestId("watchlist-row-GOOGL");
    act(() => {
      f.latest().open();
      f.latest().send({ AAPL: tick(101, 100, 100), GOOGL: tick(99, 100, 100) });
    });
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
    expect(within(screen.getByTestId("watchlist-row-GOOGL")).getByTestId("price")).toHaveTextContent("99.00");

    await userEvent.click(screen.getByTestId("watchlist-row-GOOGL"));
    expect(screen.getByLabelText("Trade ticker")).toHaveValue("GOOGL");
    expect(screen.getByTestId("main-chart")).toHaveTextContent("GOOGL");
  });

  it("collapses and expands the chat sidebar", async () => {
    renderTerminal();
    await screen.findByTestId("watchlist-row-AAPL");
    await userEvent.click(screen.getByRole("button", { name: "Collapse AI chat" }));
    expect(screen.queryByTestId("chat-panel")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Expand AI chat" }));
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
  });
});
