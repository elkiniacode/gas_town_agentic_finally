import { formatPct, formatUsd, signClass } from "@/lib/format";
import { liveValuation } from "@/lib/portfolio";
import type { ConnectionStatus } from "@/lib/priceStore";
import type { Portfolio, PriceEvent } from "@/lib/types";
import { ConnectionDot } from "./ConnectionDot";

function Stat({ label, value, valueClass = "", testId }: { label: string; value: string; valueClass?: string; testId?: string }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[10px] uppercase tracking-wider text-muted">{label}</span>
      <span className={`font-mono text-sm tabular-nums ${valueClass}`} data-testid={testId}>
        {value}
      </span>
    </div>
  );
}

/** Live total value (cash + Σ qty × live price, avg_cost fallback — R17), cash and stream status. */
export function Header({ portfolio, prices, status }: { portfolio: Portfolio | null; prices: PriceEvent; status: ConnectionStatus }) {
  const live = portfolio ? liveValuation(portfolio, prices) : null;
  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-border bg-panel px-4">
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold tracking-tight text-accent">FinAlly</span>
        <span className="hidden text-xs text-muted sm:inline">AI Trading Workstation</span>
      </div>
      <div className="flex items-center gap-6">
        <Stat label="Total value" value={live ? formatUsd(live.total_value) : "—"} valueClass="text-text font-semibold" testId="total-value" />
        <Stat
          label="P&L"
          value={live ? `${formatUsd(live.total_pnl)} (${formatPct(live.total_pnl_pct)})` : "—"}
          valueClass={signClass(live?.total_pnl)}
          testId="total-pnl"
        />
        <Stat label="Cash" value={live ? formatUsd(live.cash_balance) : "—"} testId="cash-balance" />
        <ConnectionDot status={status} />
      </div>
    </header>
  );
}
