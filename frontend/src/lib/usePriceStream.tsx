"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { apiUrl, PRICE_STREAM_PATH } from "./api";
import { PriceStore, type ConnectionStatus, type EventSourceFactory, type PricePoint } from "./priceStore";
import type { PriceEvent, PriceUpdate } from "./types";

const PriceStoreContext = createContext<PriceStore | null>(null);

const EMPTY_HISTORY: PricePoint[] = [];

/**
 * Owns the app's single EventSource on /api/stream/prices. Pass `store` to inject
 * a pre-built store (tests), or `eventSourceFactory` to fake the transport.
 */
export function PriceStreamProvider({
  children,
  store: injected,
  eventSourceFactory,
}: {
  children: ReactNode;
  store?: PriceStore;
  eventSourceFactory?: EventSourceFactory;
}) {
  const [store] = useState(() => injected ?? new PriceStore(apiUrl(PRICE_STREAM_PATH), eventSourceFactory));

  useEffect(() => {
    store.connect();
    return () => store.disconnect();
  }, [store]);

  return <PriceStoreContext.Provider value={store}>{children}</PriceStoreContext.Provider>;
}

function useStore(): PriceStore {
  const store = useContext(PriceStoreContext);
  if (!store) throw new Error("usePriceStream hooks must be used inside <PriceStreamProvider>");
  return store;
}

/** Latest price for every streamed ticker. */
export function usePrices(): PriceEvent {
  const store = useStore();
  return useSyncExternalStore(store.subscribe, store.getPrices, store.getPrices);
}

export function usePrice(ticker: string): PriceUpdate | undefined {
  return usePrices()[ticker];
}

/** Every ticker's price history (see usePriceHistory). */
export function usePriceHistories(): Record<string, PricePoint[]> {
  const store = useStore();
  return useSyncExternalStore(store.subscribe, store.getHistory, store.getHistory);
}

/** 1-second-bucketed price history since page load, capped at HISTORY_CAP points (R28). */
export function usePriceHistory(ticker: string | null): PricePoint[] {
  const store = useStore();
  const get = () => (ticker ? store.getHistory()[ticker] : undefined) ?? EMPTY_HISTORY;
  return useSyncExternalStore(store.subscribe, get, get);
}

export function useConnectionStatus(): ConnectionStatus {
  const store = useStore();
  return useSyncExternalStore(store.subscribe, store.getStatus, store.getStatus);
}
