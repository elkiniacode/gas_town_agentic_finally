import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { WatchlistItem } from "@/lib/types";
import { tick } from "@/test/fakeEventSource";
import { Watchlist } from "./Watchlist";

const items: WatchlistItem[] = [
  { ticker: "AAPL", price: 190.12, previous_price: 190.05, open_price: 189.5, change_pct: 0.33, added_at: "2026-10-18T14:00:00.000Z" },
  { ticker: "PYPL", price: null, previous_price: null, open_price: null, change_pct: null, added_at: "2026-10-18T14:05:00.000Z" },
];

const noop = () => Promise.resolve();

describe("Watchlist rendering with mock data", () => {
  it("renders rows with live price, daily change % and a sparkline", () => {
    render(
      <Watchlist
        items={items}
        prices={{ AAPL: tick(200, 199, 190) }}
        history={{ AAPL: [{ time: 1, value: 199 }, { time: 2, value: 200 }] }}
        activeTicker="AAPL"
        onSelect={vi.fn()}
        onAdd={noop}
        onRemove={noop}
      />,
    );
    const aapl = screen.getByTestId("watchlist-row-AAPL");
    expect(within(aapl).getByTestId("price")).toHaveTextContent("200.00");
    expect(within(aapl).getByTestId("change-pct")).toHaveTextContent("+5.26%");
    expect(within(aapl).getByTestId("sparkline").querySelector("polyline")).not.toBeNull();
    expect(aapl).toHaveAttribute("aria-pressed", "true");

    // No live price and none from REST → dashes, empty sparkline.
    const pypl = screen.getByTestId("watchlist-row-PYPL");
    expect(within(pypl).getByTestId("price")).toHaveTextContent("—");
    expect(within(pypl).getByTestId("change-pct")).toHaveTextContent("—");
    expect(within(pypl).getByTestId("sparkline").querySelector("polyline")).toBeNull();
  });

  it("falls back to the REST snapshot before the stream delivers", () => {
    render(<Watchlist items={items} prices={{}} history={{}} activeTicker={null} onSelect={vi.fn()} onAdd={noop} onRemove={noop} />);
    const aapl = screen.getByTestId("watchlist-row-AAPL");
    expect(within(aapl).getByTestId("price")).toHaveTextContent("190.12");
    expect(within(aapl).getByTestId("change-pct")).toHaveTextContent("+0.33%");
  });

  it("selects a ticker on click without triggering it from the remove button", async () => {
    const onSelect = vi.fn();
    const onRemove = vi.fn(noop);
    render(<Watchlist items={items} prices={{}} history={{}} activeTicker={null} onSelect={onSelect} onAdd={noop} onRemove={onRemove} />);
    await userEvent.click(screen.getByTestId("watchlist-row-PYPL"));
    expect(onSelect).toHaveBeenCalledWith("PYPL");
    await userEvent.click(screen.getByRole("button", { name: "Remove AAPL" }));
    expect(onRemove).toHaveBeenCalledWith("AAPL");
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
