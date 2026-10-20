import type { EventSourceFactory, EventSourceLike } from "@/lib/priceStore";
import type { PriceEvent } from "@/lib/types";

/** Test double for EventSource: drive it with open() / error() / send(). */
export class FakeEventSource implements EventSourceLike {
  readyState = 0;
  closed = false;
  onopen: ((ev: Event) => unknown) | null = null;
  onerror: ((ev: Event) => unknown) | null = null;
  onmessage: ((ev: MessageEvent) => unknown) | null = null;

  constructor(readonly url: string) {}

  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  /** `readyState` 0 = browser is retrying (CONNECTING), 2 = gave up (CLOSED). */
  error(readyState: 0 | 2 = 0) {
    this.readyState = readyState;
    this.onerror?.(new Event("error"));
  }

  send(event: PriceEvent) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(event) }));
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }
}

/** A factory that records every source it creates; `latest()` is the current one. */
export function fakeFactory() {
  const sources: FakeEventSource[] = [];
  const factory: EventSourceFactory = (url) => {
    const es = new FakeEventSource(url);
    sources.push(es);
    return es;
  };
  return { factory, sources, latest: () => sources[sources.length - 1] };
}

export const tick = (price: number, previous = price, open = price, timestamp = "2026-10-18T14:03:12.500Z") => ({
  price,
  previous_price: previous,
  open_price: open,
  timestamp,
});
