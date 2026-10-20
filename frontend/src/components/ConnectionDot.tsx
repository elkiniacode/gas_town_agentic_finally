import type { ConnectionStatus } from "@/lib/priceStore";

const STYLES: Record<ConnectionStatus, { dot: string; label: string }> = {
  connected: { dot: "bg-up", label: "Live" },
  connecting: { dot: "bg-warn", label: "Reconnecting" },
  disconnected: { dot: "bg-down", label: "Disconnected" },
};

/** Green = connected, yellow = reconnecting, red = disconnected (R38). */
export function ConnectionDot({ status }: { status: ConnectionStatus }) {
  const { dot, label } = STYLES[status];
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted" data-testid="connection-status" data-status={status} title={`Price stream: ${label}`}>
      <span className={`inline-block h-2 w-2 rounded-full ${dot} ${status === "connected" ? "shadow-[0_0_6px] shadow-up" : ""}`} aria-hidden />
      {label}
    </span>
  );
}
