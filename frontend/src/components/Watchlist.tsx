"use client";

import { useState, type FormEvent } from "react";
import { formatPct, signClass } from "@/lib/format";
import { changePct } from "@/lib/portfolio";
import type { PricePoint } from "@/lib/priceStore";
import type { PriceEvent, WatchlistItem } from "@/lib/types";
import { Panel } from "./Panel";
import { PriceCell } from "./PriceCell";
import { Sparkline } from "./Sparkline";

/** Sparklines show the most recent slice of the shared history buffer (R28). */
export const SPARKLINE_POINTS = 120;

type Props = {
  items: WatchlistItem[];
  prices: PriceEvent;
  history: Record<string, PricePoint[]>;
  activeTicker: string | null;
  onSelect: (ticker: string) => void;
  /** Resolve on success; reject with an Error whose message is shown inline. */
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => Promise<void>;
};

export function Watchlist({ items, prices, history, activeTicker, onSelect, onAdd, onRemove }: Props) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(ticker);
      setDraft("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(ticker: string) {
    setError(null);
    try {
      await onRemove(ticker);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Panel title="Watchlist" testId="watchlist" bodyClassName="flex flex-col">
      <form onSubmit={submit} className="flex gap-2 border-b border-border p-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value.toUpperCase())}
          placeholder="Add ticker"
          aria-label="Ticker to add"
          maxLength={5}
          className="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-1 font-mono text-sm uppercase placeholder:normal-case placeholder:text-muted focus:border-primary focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="rounded bg-secondary px-3 py-1 text-sm font-semibold text-white hover:bg-secondary-hover disabled:opacity-50"
        >
          Add
        </button>
      </form>
      {error && (
        <p role="alert" className="border-b border-border px-3 py-1 text-xs text-down">
          {error}
        </p>
      )}
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {items.map((item) => {
          const live = prices[item.ticker];
          const price = live?.price ?? item.price;
          const pct = live ? changePct(live.price, live.open_price) : item.change_pct;
          const active = item.ticker === activeTicker;
          return (
            <li
              key={item.ticker}
              data-testid={`watchlist-row-${item.ticker}`}
              role="button"
              tabIndex={0}
              aria-pressed={active}
              onClick={() => onSelect(item.ticker)}
              onKeyDown={(e) => {
                if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  onSelect(item.ticker);
                }
              }}
              className={`group grid cursor-pointer grid-cols-[3.5rem_1fr_auto] items-center gap-x-2 border-b border-border/60 px-3 py-1.5 hover:bg-panel-2 focus:outline-none focus-visible:bg-panel-2 ${
                active ? "bg-panel-2 shadow-[inset_2px_0_0] shadow-accent" : ""
              }`}
            >
              <span className="font-mono text-sm font-semibold">{item.ticker}</span>
              <Sparkline points={(history[item.ticker] ?? []).slice(-SPARKLINE_POINTS)} />
              <div className="flex items-center gap-1">
                <div className="flex flex-col items-end leading-tight">
                  <PriceCell price={price} className="text-sm" />
                  <span className={`font-mono text-[11px] tabular-nums ${signClass(pct)}`} data-testid="change-pct">
                    {formatPct(pct)}
                  </span>
                </div>
                <button
                  type="button"
                  aria-label={`Remove ${item.ticker}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    void remove(item.ticker);
                  }}
                  className="ml-1 rounded px-1 text-muted opacity-40 hover:bg-down/20 hover:text-down group-hover:opacity-100"
                >
                  ×
                </button>
              </div>
            </li>
          );
        })}
        {items.length === 0 && <li className="px-3 py-4 text-center text-xs text-muted">No tickers — add one above.</li>}
      </ul>
    </Panel>
  );
}
