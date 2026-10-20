import { act, render, screen } from "@testing-library/react";
import { FLASH_MS, PriceCell } from "./PriceCell";

describe("PriceCell flash", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const cell = () => screen.getByTestId("price");

  it("does not flash on first render", () => {
    render(<PriceCell price={100} />);
    expect(cell()).toHaveTextContent("100.00");
    expect(cell().className).not.toMatch(/flash-/);
  });

  it("flashes green on an uptick and clears after ~500 ms", () => {
    const { rerender } = render(<PriceCell price={100} />);
    rerender(<PriceCell price={101} />);
    expect(cell()).toHaveClass("flash-up");
    expect(cell()).toHaveTextContent("101.00");
    act(() => vi.advanceTimersByTime(FLASH_MS));
    expect(cell().className).not.toMatch(/flash-/);
  });

  it("flashes red on a downtick", () => {
    const { rerender } = render(<PriceCell price={100} />);
    rerender(<PriceCell price={99.5} />);
    expect(cell()).toHaveClass("flash-down");
  });

  it("restarts the animation on back-to-back ticks in the same direction", () => {
    const { rerender } = render(<PriceCell price={100} />);
    rerender(<PriceCell price={101} />);
    const first = cell();
    rerender(<PriceCell price={102} />);
    expect(cell()).toHaveClass("flash-up");
    expect(cell()).not.toBe(first); // re-keyed element → CSS animation restarts
  });

  it("shows a dash and does not flash when the price first arrives from null", () => {
    const { rerender } = render(<PriceCell price={null} />);
    expect(cell()).toHaveTextContent("—");
    rerender(<PriceCell price={50} />);
    expect(cell().className).not.toMatch(/flash-/);
  });
});
