import { Placeholder } from "./Placeholder";

/**
 * AI chat conversation (R24). PLACEHOLDER — fin-k90.8 replaces this with history,
 * input, loading state and ✓/✗ action results. Call `onActions` after a 200 whose
 * actions are non-empty so the app refetches portfolio, watchlist and history (R29).
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- consumed by fin-k90.8
export function ChatPanel({ onActions }: { onActions: () => void | Promise<void> }) {
  return (
    <div data-testid="chat-panel" className="h-full">
      <Placeholder owner="fin-k90.8">AI assistant</Placeholder>
    </div>
  );
}
