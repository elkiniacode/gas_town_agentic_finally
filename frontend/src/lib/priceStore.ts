// Live price state fed by the SSE stream (PLAN §6 SSE, §10 R28/R38).
import type { PriceEvent } from "./types";

export type ConnectionStatus = "connected" | "connecting" | "disconnected";

/** One point per 1-second bucket. `time` is unix seconds (Lightweight Charts' UTCTimestamp). */
export type PricePoint = { time: number; value: number };

/** Per-ticker history cap shared by sparklines and the main chart (R28). */
export const HISTORY_CAP = 1000;
/** Still not reconnected this long after the first error → red (R38). */
export const DISCONNECTED_AFTER_MS = 15_000;
/** Delay before re-creating an EventSource the browser gave up on (readyState CLOSED). */
export const RECREATE_AFTER_MS = 5_000;

// EventSource.readyState values; numeric so the store doesn't need a global EventSource.
const CONNECTING = 0;
const CLOSED = 2;

/** The subset of EventSource the store uses — lets tests inject a fake. */
export type EventSourceLike = {
  readyState: number;
  onopen: ((ev: Event) => unknown) | null;
  onerror: ((ev: Event) => unknown) | null;
  onmessage: ((ev: MessageEvent) => unknown) | null;
  close(): void;
};

export type EventSourceFactory = (url: string) => EventSourceLike;

const defaultFactory: EventSourceFactory = (url) => new EventSource(url);

/** Append `value` at `time`, replacing the last point if it is in the same second. Returns a new array. */
export function appendPoint(points: readonly PricePoint[], time: number, value: number, cap = HISTORY_CAP): PricePoint[] {
  const last = points[points.length - 1];
  if (last && time < last.time) return points as PricePoint[]; // out of order; ignore
  const next = last && last.time === time ? [...points.slice(0, -1), { time, value }] : [...points, { time, value }];
  return next.length > cap ? next.slice(next.length - cap) : next;
}

export class PriceStore {
  private prices: PriceEvent = {};
  private history: Record<string, PricePoint[]> = {};
  private status: ConnectionStatus = "connecting";
  private listeners = new Set<() => void>();
  private source: EventSourceLike | null = null;
  private disconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private recreateTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly url: string,
    private readonly factory: EventSourceFactory = defaultFactory,
  ) {}

  // --- useSyncExternalStore plumbing (snapshots change identity only on update) ---

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getPrices = (): PriceEvent => this.prices;
  getHistory = (): Record<string, PricePoint[]> => this.history;
  getStatus = (): ConnectionStatus => this.status;

  private emit() {
    for (const l of this.listeners) l();
  }

  private setStatus(status: ConnectionStatus) {
    if (status === this.status) return;
    this.status = status;
    this.emit();
  }

  // --- Connection lifecycle ---

  connect(): void {
    if (this.source) return;
    const es = this.factory(this.url);
    this.source = es;
    es.onopen = () => this.handleOpen();
    es.onerror = () => this.handleError(es);
    es.onmessage = (ev) => this.handleMessage(ev.data);
  }

  disconnect(): void {
    this.clearTimers();
    this.source?.close();
    this.source = null;
  }

  private clearTimers() {
    if (this.disconnectTimer) clearTimeout(this.disconnectTimer);
    if (this.recreateTimer) clearTimeout(this.recreateTimer);
    this.disconnectTimer = null;
    this.recreateTimer = null;
  }

  private handleOpen() {
    this.clearTimers();
    this.setStatus("connected");
  }

  private handleError(es: EventSourceLike) {
    if (es.readyState === CLOSED) {
      // The browser will not retry on its own; show red and re-create the source later.
      this.clearTimers();
      es.close();
      if (this.source === es) this.source = null;
      this.setStatus("disconnected");
      this.recreateTimer = setTimeout(() => {
        this.recreateTimer = null;
        this.connect();
      }, RECREATE_AFTER_MS);
      return;
    }
    if (es.readyState === CONNECTING && this.disconnectTimer === null && this.status !== "disconnected") {
      // Brief drop: yellow while EventSource retries, red if it hasn't recovered in 15 s.
      this.setStatus("connecting");
      this.disconnectTimer = setTimeout(() => {
        this.disconnectTimer = null;
        this.setStatus("disconnected");
      }, DISCONNECTED_AFTER_MS);
    }
  }

  /** Apply one SSE event. Public so tests and callers can feed data directly. */
  handleMessage(data: string): void {
    let event: PriceEvent;
    try {
      event = JSON.parse(data);
    } catch {
      return;
    }
    if (!event || typeof event !== "object") return;

    // Each event carries every priced ticker; tickers absent from it were removed.
    const history: Record<string, PricePoint[]> = {};
    for (const [ticker, update] of Object.entries(event)) {
      const parsed = Date.parse(update.timestamp);
      const time = Math.floor((Number.isNaN(parsed) ? Date.now() : parsed) / 1000);
      history[ticker] = appendPoint(this.history[ticker] ?? [], time, update.price);
    }
    this.prices = event;
    this.history = history;
    this.emit();
  }
}
