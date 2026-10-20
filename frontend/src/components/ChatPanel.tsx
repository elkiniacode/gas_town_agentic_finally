"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { formatQty, formatUsd } from "@/lib/format";
import type { ChatActions, ChatHistoryResponse, ChatMessage, ChatResponse, TradeResult, WatchlistChangeResult } from "@/lib/types";

/** Server-side limit on POST /api/chat (API_CONTRACT §Chat). */
export const MAX_MESSAGE_CHARS = 2000;

export const CHAT_EMPTY_TEXT = "Ask about your portfolio, or tell me to trade and manage your watchlist.";

/** A conversation row: a stored message, or an inline error that is never persisted (R26). */
type Entry = Pick<ChatMessage, "id" | "content" | "actions"> & { role: ChatMessage["role"] | "error" };

type Props = {
  /** Called after a 200 whose actions are non-empty so the app refetches (R29). */
  onActions: () => void | Promise<void>;
  sendChat?: (message: string) => Promise<ChatResponse>;
  loadHistory?: () => Promise<ChatHistoryResponse>;
};

const hasActions = (a: ChatActions | null): a is ChatActions =>
  !!a && a.watchlist_changes.length + a.trades.length > 0;

/**
 * AI chat conversation: history from GET /api/chat/history on mount (R24), input with a
 * purple Send button, a loading indicator while POST /api/chat is in flight, each action
 * result inline as ✓ / ✗ + error (R22/R23), and 502/503 failures as inline errors (R26/R3).
 */
export function ChatPanel({ onActions, sendChat = api.sendChat, loadHistory = api.getChatHistory }: Props) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const nextId = useRef(0);
  const scroller = useRef<HTMLDivElement>(null);

  const localId = (kind: string) => `local-${kind}-${++nextId.current}`;

  useEffect(() => {
    // State is set from the promise callbacks, never synchronously in the effect.
    let live = true;
    loadHistory().then(
      ({ messages }) => live && setEntries((prev) => [...messages, ...prev]),
      (err: Error) =>
        live &&
        setEntries((prev) => [
          { id: "history-error", role: "error", content: `Could not load chat history: ${err.message}`, actions: null },
          ...prev,
        ]),
    ).finally(() => live && setLoaded(true));
    return () => {
      live = false;
    };
  }, [loadHistory]);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries, pending]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const message = draft.trim();
    if (!message || pending) return;
    setDraft("");
    setPending(true);
    setEntries((prev) => [...prev, { id: localId("user"), role: "user", content: message, actions: null }]);
    try {
      const res = await sendChat(message);
      setEntries((prev) => [
        ...prev,
        { id: localId("assistant"), role: "assistant", content: res.message, actions: res.actions },
      ]);
      if (hasActions(res.actions)) await onActions();
    } catch (err) {
      setEntries((prev) => [...prev, { id: localId("error"), role: "error", content: (err as Error).message, actions: null }]);
    } finally {
      setPending(false);
    }
  }

  return (
    <div data-testid="chat-panel" className="flex h-full flex-col">
      <div ref={scroller} data-testid="chat-messages" className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {loaded && entries.length === 0 && !pending && (
          <p data-testid="chat-empty" className="pt-6 text-center text-xs text-muted">
            {CHAT_EMPTY_TEXT}
          </p>
        )}
        {entries.map((entry) => (
          <ChatEntry key={entry.id} entry={entry} />
        ))}
        {pending && (
          <div role="status" data-testid="chat-loading" className="flex items-center gap-2 text-xs text-muted">
            <span className="flex gap-1" aria-hidden>
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-secondary"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
            FinAlly is thinking…
          </div>
        )}
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-border p-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message FinAlly"
          aria-label="Chat message"
          data-testid="chat-input"
          maxLength={MAX_MESSAGE_CHARS}
          className="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-1.5 text-sm placeholder:text-muted focus:border-primary focus:outline-none"
        />
        <button
          type="submit"
          data-testid="chat-send"
          disabled={pending || !draft.trim()}
          className="rounded bg-secondary px-4 py-1.5 text-sm font-semibold text-white hover:bg-secondary-hover disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}

function ChatEntry({ entry }: { entry: Entry }) {
  if (entry.role === "error") {
    return (
      <p role="alert" data-testid="chat-error" className="rounded border border-down/40 bg-down/10 px-3 py-2 text-xs text-down">
        {entry.content}
      </p>
    );
  }

  const user = entry.role === "user";
  return (
    <div data-testid="chat-message" data-role={entry.role} className={`flex flex-col ${user ? "items-end" : "items-start"}`}>
      <span className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{user ? "You" : "FinAlly"}</span>
      <div
        className={`max-w-[90%] whitespace-pre-wrap break-words rounded px-3 py-2 text-sm ${
          user ? "bg-secondary/25" : "border border-border bg-panel-2"
        }`}
      >
        {entry.content}
        {hasActions(entry.actions) && <ActionResults actions={entry.actions} />}
      </div>
    </div>
  );
}

/** Results in execution order: watchlist changes, then trades (R25). */
function ActionResults({ actions }: { actions: ChatActions }) {
  return (
    <ul data-testid="chat-actions" className="mt-2 space-y-1 border-t border-border pt-2 font-mono text-xs">
      {actions.watchlist_changes.map((c, i) => (
        <ActionRow key={`w${i}`} kind="watchlist" label={watchlistLabel(c)} status={c.status} error={c.error} />
      ))}
      {actions.trades.map((t, i) => (
        <ActionRow key={`t${i}`} kind="trade" label={tradeLabel(t)} status={t.status} error={t.error} />
      ))}
    </ul>
  );
}

function ActionRow({ kind, label, status, error }: { kind: string; label: string; status: string; error: string | null }) {
  const ok = status === "ok";
  return (
    <li data-testid="chat-action" data-kind={kind} data-status={status}>
      <span className={ok ? "text-up" : "text-down"} aria-hidden>
        {ok ? "✓" : "✗"}
      </span>
      <span className="sr-only">{ok ? "Succeeded:" : "Failed:"}</span>{" "}
      {label}
      {!ok && error && <span className="block pl-4 text-down">{error}</span>}
    </li>
  );
}

const watchlistLabel = (c: WatchlistChangeResult) =>
  c.action === "add" ? `Add ${c.ticker} to watchlist` : `Remove ${c.ticker} from watchlist`;

const tradeLabel = (t: TradeResult) =>
  `${t.side === "buy" ? "Buy" : "Sell"} ${formatQty(t.quantity)} ${t.ticker}` +
  (t.status === "ok" && t.price !== null ? ` @ ${formatUsd(t.price)}` : "");
