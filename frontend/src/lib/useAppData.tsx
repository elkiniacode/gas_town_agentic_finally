"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Portfolio, PortfolioSnapshot, WatchlistItem } from "./types";

/** A watchlist click. `seq` changes on every click so re-clicking a ticker re-fills the trade bar. */
export type Selection = { ticker: string; seq: number };

export type AppData = {
  portfolio: Portfolio | null;
  watchlist: WatchlistItem[];
  snapshots: PortfolioSnapshot[];
  /** Last refresh failure, cleared on the next successful refresh. */
  loadError: string | null;
  /** Refetch portfolio, watchlist and history (R29). Call after any trade, watchlist change or chat action. */
  refresh: () => Promise<void>;
  /** Replace the watchlist with a server response (POST/DELETE return the full list). */
  setWatchlist: (items: WatchlistItem[]) => void;
  selection: Selection | null;
  /** Ticker shown in the main chart: the last click, else the first watchlist ticker. */
  activeTicker: string | null;
  selectTicker: (ticker: string) => void;
};

const AppDataContext = createContext<AppData | null>(null);

const fetchAll = () => Promise.allSettled([api.getPortfolio(), api.getWatchlist(), api.getPortfolioHistory()]);
type Fetched = Awaited<ReturnType<typeof fetchAll>>;

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);

  const apply = useCallback(([p, w, h]: Fetched) => {
    if (p.status === "fulfilled") setPortfolio(p.value);
    if (w.status === "fulfilled") setWatchlist(w.value.watchlist);
    if (h.status === "fulfilled") setSnapshots(h.value.snapshots);
    const failed = [p, w, h].find((r) => r.status === "rejected");
    setLoadError(failed ? (failed.reason as Error).message : null);
  }, []);

  const refresh = useCallback(() => fetchAll().then(apply), [apply]);

  useEffect(() => {
    // Initial load. State is set from the promise callback, never synchronously in the effect.
    let live = true;
    void fetchAll().then((r) => live && apply(r));
    return () => {
      live = false;
    };
  }, [apply]);

  const selectTicker = useCallback((ticker: string) => {
    setSelection((prev) => ({ ticker, seq: (prev?.seq ?? 0) + 1 }));
  }, []);

  const tickers = watchlist.map((w) => w.ticker);
  const activeTicker =
    selection && (tickers.includes(selection.ticker) || portfolio?.positions.some((p) => p.ticker === selection.ticker))
      ? selection.ticker
      : (tickers[0] ?? null);

  const value = useMemo<AppData>(
    () => ({
      portfolio,
      watchlist,
      snapshots,
      loadError,
      refresh,
      setWatchlist,
      selection,
      activeTicker,
      selectTicker,
    }),
    [portfolio, watchlist, snapshots, loadError, refresh, selection, activeTicker, selectTicker],
  );

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppData {
  const ctx = useContext(AppDataContext);
  if (!ctx) throw new Error("useAppData must be used inside <AppDataProvider>");
  return ctx;
}
