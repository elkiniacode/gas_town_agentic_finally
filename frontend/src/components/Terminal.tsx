"use client";

import { useCallback, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { liveValuation } from "@/lib/portfolio";
import { useAppData } from "@/lib/useAppData";
import { useConnectionStatus, usePriceHistories, usePrices } from "@/lib/usePriceStream";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { MainChart } from "./MainChart";
import { PnlChart } from "./PnlChart";
import { PortfolioHeatmap } from "./PortfolioHeatmap";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { Watchlist } from "./Watchlist";

/**
 * Whole-page terminal layout (PLAN §10): header across the top; watchlist on the left;
 * main chart, heatmap + P&L chart, positions and trade bar in the center; collapsible
 * AI chat sidebar on the right. Desktop-first; stacks vertically below `lg`.
 */
export function Terminal() {
  const { portfolio, watchlist, snapshots, loadError, refresh, setWatchlist, selection, activeTicker, selectTicker } =
    useAppData();
  const prices = usePrices();
  const histories = usePriceHistories();
  const status = useConnectionStatus();
  const [chatOpen, setChatOpen] = useState(true);

  const live = useMemo(() => (portfolio ? liveValuation(portfolio, prices) : null), [portfolio, prices]);

  // Watchlist changes refetch everything afterwards (R29).
  const addTicker = useCallback(
    async (ticker: string) => {
      setWatchlist((await api.addToWatchlist(ticker)).watchlist);
      await refresh();
    },
    [setWatchlist, refresh],
  );
  const removeTicker = useCallback(
    async (ticker: string) => {
      setWatchlist((await api.removeFromWatchlist(ticker)).watchlist);
      await refresh();
    },
    [setWatchlist, refresh],
  );

  const panelSize = "min-h-56 lg:min-h-0";

  return (
    <div className="flex min-h-screen flex-col lg:h-screen">
      <Header portfolio={portfolio} prices={prices} status={status} />
      {loadError && (
        <p role="alert" className="border-b border-border bg-down/10 px-4 py-1 text-xs text-down">
          {loadError}
        </p>
      )}
      <div className="flex min-h-0 flex-1 flex-col gap-2 p-2 lg:flex-row">
        <aside className="flex min-h-80 flex-col lg:min-h-0 lg:w-72 lg:shrink-0">
          <Watchlist
            items={watchlist}
            prices={prices}
            history={histories}
            activeTicker={activeTicker}
            onSelect={selectTicker}
            onAdd={addTicker}
            onRemove={removeTicker}
          />
        </aside>

        <main className="flex min-w-0 flex-1 flex-col gap-2">
          <MainChart
            ticker={activeTicker}
            points={activeTicker ? (histories[activeTicker] ?? []) : []}
            className={`${panelSize} lg:flex-[3]`}
          />
          <div className="grid gap-2 lg:min-h-0 lg:flex-[2] lg:grid-cols-2">
            <PortfolioHeatmap positions={live?.positions ?? []} className={panelSize} />
            <PnlChart snapshots={snapshots} liveTotal={live?.total_value ?? null} className={panelSize} />
          </div>
          <PositionsTable positions={live?.positions ?? []} className={`${panelSize} lg:flex-[2]`} />
          <TradeBar selection={selection} onTraded={refresh} />
        </main>

        <aside
          data-testid="chat-sidebar"
          data-open={chatOpen}
          className={`flex min-h-0 flex-col rounded border border-border bg-panel ${chatOpen ? "min-h-96 lg:min-h-0 lg:w-96 lg:shrink-0" : "lg:w-9 lg:shrink-0"}`}
        >
          <header className="flex h-8 shrink-0 items-center justify-between border-b border-border px-2">
            {chatOpen && (
              <h2 className="px-1 text-[11px] font-semibold uppercase tracking-wider text-muted">AI Assistant</h2>
            )}
            <button
              type="button"
              onClick={() => setChatOpen((o) => !o)}
              aria-expanded={chatOpen}
              aria-label={chatOpen ? "Collapse AI chat" : "Expand AI chat"}
              className="rounded px-1.5 text-sm text-primary hover:bg-panel-2"
            >
              {chatOpen ? "»" : "«"}
            </button>
          </header>
          {chatOpen && (
            <div className="min-h-0 flex-1">
              <ChatPanel onActions={refresh} />
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
