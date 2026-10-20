"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { formatQty, formatUsd } from "@/lib/format";
import type { TradeRequest, TradeResponse, TradeSide } from "@/lib/types";
import type { Selection } from "@/lib/useAppData";

/** Inline result lifetime (R31). */
export const RESULT_CLEAR_MS = 4000;

type Result = { ok: boolean; text: string };

type Props = {
  /** Watchlist click; each new click pre-fills the ticker field (R31). */
  selection: Selection | null;
  /** Called after a successful trade so the app can refetch (R29). */
  onTraded: () => void | Promise<void>;
  trade?: (req: TradeRequest) => Promise<TradeResponse>;
};

/** Market-order bar: ticker, fractional quantity, Buy / Sell, inline result. */
export function TradeBar({ selection, onTraded, trade = api.trade }: Props) {
  const [ticker, setTicker] = useState(selection?.ticker ?? "");
  const [quantity, setQuantity] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [seenSeq, setSeenSeq] = useState(selection?.seq);

  if (selection && selection.seq !== seenSeq) {
    setSeenSeq(selection.seq);
    setTicker(selection.ticker);
  }

  useEffect(() => {
    if (!result) return;
    const t = setTimeout(() => setResult(null), RESULT_CLEAR_MS);
    return () => clearTimeout(t);
  }, [result]);

  async function submit(side: TradeSide) {
    setResult(null);
    const symbol = ticker.trim().toUpperCase();
    const qty = Number(quantity);
    if (!symbol) return setResult({ ok: false, text: "Enter a ticker" });
    if (!quantity.trim() || !Number.isFinite(qty) || qty <= 0) {
      return setResult({ ok: false, text: "Quantity must be greater than 0" });
    }
    setBusy(true);
    try {
      const { trade: t } = await trade({ ticker: symbol, quantity: qty, side });
      setResult({
        ok: true,
        text: `${t.side === "buy" ? "Bought" : "Sold"} ${formatQty(t.quantity)} ${t.ticker} @ ${formatUsd(t.price)}`,
      });
      await onTraded();
    } catch (err) {
      setResult({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  // Enter in a field does nothing: the side must be chosen explicitly.
  const onSubmit = (e: FormEvent<HTMLFormElement>) => e.preventDefault();

  const input =
    "rounded border border-border bg-bg px-2 py-1.5 font-mono text-sm focus:border-primary focus:outline-none placeholder:text-muted";
  const button = "rounded bg-secondary px-4 py-1.5 text-sm font-semibold text-white hover:bg-secondary-hover disabled:opacity-50";

  return (
    <form onSubmit={onSubmit} data-testid="trade-bar" className="flex flex-col gap-1 rounded border border-border bg-panel px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Trade</span>
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="Ticker"
          aria-label="Trade ticker"
          maxLength={5}
          className={`${input} w-24 uppercase placeholder:normal-case`}
        />
        <input
          type="number"
          inputMode="decimal"
          step="0.0001"
          min="0"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="Quantity"
          aria-label="Trade quantity"
          className={`${input} w-28`}
        />
        <button type="button" onClick={() => void submit("buy")} disabled={busy} className={button}>
          Buy
        </button>
        <button type="button" onClick={() => void submit("sell")} disabled={busy} className={button}>
          Sell
        </button>
        <span className="text-[11px] text-muted">Market order · instant fill</span>
      </div>
      <p
        role="status"
        data-testid="trade-result"
        className={`min-h-4 font-mono text-xs ${result ? (result.ok ? "text-up" : "text-down") : ""}`}
      >
        {result?.text}
      </p>
    </form>
  );
}
