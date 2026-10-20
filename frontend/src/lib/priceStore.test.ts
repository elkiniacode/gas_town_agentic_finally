import { fakeFactory, tick } from "@/test/fakeEventSource";
import { appendPoint, DISCONNECTED_AFTER_MS, HISTORY_CAP, PriceStore, RECREATE_AFTER_MS } from "./priceStore";

describe("PriceStore connection status (R38)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function setup() {
    const f = fakeFactory();
    const store = new PriceStore("/api/stream/prices", f.factory);
    store.connect();
    return { store, ...f };
  }

  it("starts connecting and turns green on open", () => {
    const { store, latest } = setup();
    expect(latest().url).toBe("/api/stream/prices");
    expect(store.getStatus()).toBe("connecting");
    latest().open();
    expect(store.getStatus()).toBe("connected");
  });

  it("shows yellow on a brief drop and green again on reconnect", () => {
    const { store, latest } = setup();
    latest().open();
    latest().error(0);
    expect(store.getStatus()).toBe("connecting");
    vi.advanceTimersByTime(DISCONNECTED_AFTER_MS - 1);
    latest().open();
    expect(store.getStatus()).toBe("connected");
    // The 15 s timer was cleared by the reopen.
    vi.advanceTimersByTime(DISCONNECTED_AFTER_MS);
    expect(store.getStatus()).toBe("connected");
  });

  it("turns red when still not reconnected 15 s after the first error", () => {
    const { store, latest } = setup();
    latest().open();
    latest().error(0);
    vi.advanceTimersByTime(5_000);
    latest().error(0); // repeated retries don't restart the clock
    vi.advanceTimersByTime(DISCONNECTED_AFTER_MS - 5_000);
    expect(store.getStatus()).toBe("disconnected");
  });

  it("turns red immediately on CLOSED and re-creates the source later", () => {
    const { store, sources, latest } = setup();
    latest().open();
    const first = latest();
    first.error(2);
    expect(store.getStatus()).toBe("disconnected");
    expect(first.closed).toBe(true);
    expect(sources).toHaveLength(1);
    vi.advanceTimersByTime(RECREATE_AFTER_MS);
    expect(sources).toHaveLength(2);
    latest().open();
    expect(store.getStatus()).toBe("connected");
  });

  it("notifies subscribers on status change and stops after disconnect()", () => {
    const { store, latest } = setup();
    const listener = vi.fn();
    store.subscribe(listener);
    latest().open();
    expect(listener).toHaveBeenCalledTimes(1);
    store.disconnect();
    expect(latest().closed).toBe(true);
  });
});

describe("PriceStore messages and history (R28)", () => {
  it("stores the latest event and buckets history per second", () => {
    const store = new PriceStore("/x", fakeFactory().factory);
    store.handleMessage(JSON.stringify({ AAPL: tick(190, 190, 189.5, "2026-10-18T14:03:12.000Z") }));
    store.handleMessage(JSON.stringify({ AAPL: tick(191, 190, 189.5, "2026-10-18T14:03:12.500Z") }));
    store.handleMessage(JSON.stringify({ AAPL: tick(192, 191, 189.5, "2026-10-18T14:03:13.000Z") }));
    expect(store.getPrices().AAPL.price).toBe(192);
    const t0 = Date.parse("2026-10-18T14:03:12.000Z") / 1000;
    expect(store.getHistory().AAPL).toEqual([
      { time: t0, value: 191 },
      { time: t0 + 1, value: 192 },
    ]);
  });

  it("drops tickers that leave the stream and ignores malformed data", () => {
    const store = new PriceStore("/x", fakeFactory().factory);
    store.handleMessage(JSON.stringify({ AAPL: tick(1), MSFT: tick(2) }));
    store.handleMessage(JSON.stringify({ AAPL: tick(1.5, 1, 1, "2026-10-18T14:03:14.000Z") }));
    expect(Object.keys(store.getPrices())).toEqual(["AAPL"]);
    expect(store.getHistory().MSFT).toBeUndefined();
    const before = store.getPrices();
    store.handleMessage("not json");
    expect(store.getPrices()).toBe(before);
  });

  it("caps history at HISTORY_CAP points and ignores out-of-order points", () => {
    let pts = appendPoint([], 0, 1);
    for (let t = 1; t < HISTORY_CAP + 50; t++) pts = appendPoint(pts, t, t);
    expect(pts).toHaveLength(HISTORY_CAP);
    expect(pts[pts.length - 1]).toEqual({ time: HISTORY_CAP + 49, value: HISTORY_CAP + 49 });
    expect(appendPoint(pts, 3, 99)).toBe(pts);
  });
});
