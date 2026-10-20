import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/lib/api";
import type { ChatActions, ChatHistoryResponse, ChatMessage, ChatResponse } from "@/lib/types";
import { CHAT_EMPTY_TEXT, ChatPanel } from "./ChatPanel";

const NO_ACTIONS: ChatActions = { watchlist_changes: [], trades: [] };

const msg = (role: ChatMessage["role"], content: string, actions: ChatActions | null = null): ChatMessage => ({
  id: `${role}-${content}`,
  role,
  content,
  actions,
  created_at: "2026-10-18T14:05:40.900Z",
});

const history = (...messages: ChatMessage[]) => vi.fn(async (): Promise<ChatHistoryResponse> => ({ messages }));

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function send(text: string) {
  await userEvent.type(screen.getByTestId("chat-input"), text);
  await userEvent.click(screen.getByTestId("chat-send"));
}

describe("ChatPanel", () => {
  it("loads history on mount in ascending order (R24)", async () => {
    const loadHistory = history(msg("user", "hello"), msg("assistant", "Hi, how can I help?"));
    render(<ChatPanel onActions={vi.fn()} loadHistory={loadHistory} sendChat={vi.fn()} />);
    const rows = await screen.findAllByTestId("chat-message");
    expect(loadHistory).toHaveBeenCalledTimes(1);
    expect(rows.map((r) => [r.dataset.role, r.textContent])).toEqual([
      ["user", "Youhello"],
      ["assistant", "FinAllyHi, how can I help?"],
    ]);
    expect(screen.queryByTestId("chat-empty")).not.toBeInTheDocument();
  });

  it("shows an empty-state hint for a fresh conversation", async () => {
    render(<ChatPanel onActions={vi.fn()} loadHistory={history()} sendChat={vi.fn()} />);
    expect(await screen.findByTestId("chat-empty")).toHaveTextContent(CHAT_EMPTY_TEXT);
  });

  it("renders stored action results from history with ✓ / ✗ and errors (R22/R23)", async () => {
    const actions: ChatActions = {
      watchlist_changes: [{ ticker: "PYPL", action: "add", status: "ok", error: null }],
      trades: [
        { ticker: "AAPL", side: "buy", quantity: 10, price: 190.12, status: "failed", error: "Insufficient cash: need $1901.20, have $500.00" },
        { ticker: "PYPL", side: "sell", quantity: 2.5, price: 72.4, status: "ok", error: null },
      ],
    };
    render(<ChatPanel onActions={vi.fn()} loadHistory={history(msg("assistant", "Placing orders.", actions))} sendChat={vi.fn()} />);
    const rows = await screen.findAllByTestId("chat-action");
    expect(rows.map((r) => [r.dataset.kind, r.dataset.status])).toEqual([
      ["watchlist", "ok"],
      ["trade", "failed"],
      ["trade", "ok"],
    ]);
    expect(rows[0]).toHaveTextContent("✓Succeeded: Add PYPL to watchlist");
    expect(rows[1]).toHaveTextContent("✗Failed: Buy 10 AAPL");
    expect(rows[1]).toHaveTextContent("Insufficient cash: need $1901.20, have $500.00");
    expect(rows[1]).not.toHaveTextContent("@");
    expect(rows[2]).toHaveTextContent("✓Succeeded: Sell 2.5 PYPL @ $72.40");
  });

  it("shows a loading indicator while awaiting the reply, then the reply", async () => {
    const reply = deferred<ChatResponse>();
    const sendChat = vi.fn(() => reply.promise);
    render(<ChatPanel onActions={vi.fn()} loadHistory={history()} sendChat={sendChat} />);
    await screen.findByTestId("chat-empty");

    await send("  how am I doing?  ");
    expect(sendChat).toHaveBeenCalledWith("how am I doing?");
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    expect(screen.getByTestId("chat-send")).toBeDisabled();
    expect(screen.getByTestId("chat-input")).toHaveValue("");
    expect(screen.getAllByTestId("chat-message").at(-1)).toHaveTextContent("how am I doing?");

    reply.resolve({ message: "You are 100% cash.", actions: NO_ACTIONS });
    expect(await screen.findByText("You are 100% cash.")).toBeInTheDocument();
    expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument();
  });

  it("renders action results from a reply and triggers the shared refetch (R29)", async () => {
    const sendChat = vi.fn(
      async (): Promise<ChatResponse> => ({
        message: "Mock response: adding PYPL to your watchlist; placing a buy order for 1 AAPL.",
        actions: {
          watchlist_changes: [{ ticker: "PYPL", action: "add", status: "ok", error: null }],
          trades: [{ ticker: "AAPL", side: "buy", quantity: 1, price: 190.12, status: "ok", error: null }],
        },
      }),
    );
    const onActions = vi.fn();
    render(<ChatPanel onActions={onActions} loadHistory={history()} sendChat={sendChat} />);
    await send("add PYPL and buy");
    const reply = (await screen.findAllByTestId("chat-message")).at(-1)!;
    expect(reply).toHaveAttribute("data-role", "assistant");
    const results = within(reply).getAllByTestId("chat-action");
    expect(results[0]).toHaveTextContent("Add PYPL to watchlist");
    expect(results[1]).toHaveTextContent("Buy 1 AAPL @ $190.12");
    expect(onActions).toHaveBeenCalledTimes(1);
  });

  it("does not refetch after a reply without actions", async () => {
    const onActions = vi.fn();
    const sendChat = vi.fn(async (): Promise<ChatResponse> => ({ message: "Hello!", actions: NO_ACTIONS }));
    render(<ChatPanel onActions={onActions} loadHistory={history()} sendChat={sendChat} />);
    await send("hello");
    await screen.findByText("Hello!");
    expect(screen.queryByTestId("chat-actions")).not.toBeInTheDocument();
    expect(onActions).not.toHaveBeenCalled();
  });

  it.each([
    [502, "LLM request failed: timeout"],
    [503, "LLM not configured: set OPENROUTER_API_KEY or LLM_MOCK=true"],
  ])("shows a %i inline as an error and keeps the user's message (R26/R3)", async (status, detail) => {
    const onActions = vi.fn();
    const sendChat = vi.fn(async (): Promise<ChatResponse> => {
      throw new ApiError(status, detail);
    });
    render(<ChatPanel onActions={onActions} loadHistory={history()} sendChat={sendChat} />);
    await send("buy");
    expect(await screen.findByTestId("chat-error")).toHaveTextContent(detail);
    expect(screen.getByTestId("chat-message")).toHaveTextContent("buy");
    expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument();
    expect(onActions).not.toHaveBeenCalled();
    // The panel stays usable after an error.
    await userEvent.type(screen.getByTestId("chat-input"), "again");
    expect(screen.getByTestId("chat-send")).toBeEnabled();
  });

  it("shows a history load failure inline", async () => {
    const loadHistory = vi.fn(async (): Promise<ChatHistoryResponse> => {
      throw new ApiError(0, "Network error: could not reach the server");
    });
    render(<ChatPanel onActions={vi.fn()} loadHistory={loadHistory} sendChat={vi.fn()} />);
    expect(await screen.findByTestId("chat-error")).toHaveTextContent(
      "Could not load chat history: Network error: could not reach the server",
    );
  });

  it("does not send a blank message", async () => {
    const sendChat = vi.fn();
    render(<ChatPanel onActions={vi.fn()} loadHistory={history()} sendChat={sendChat} />);
    await screen.findByTestId("chat-empty");
    await userEvent.type(screen.getByTestId("chat-input"), "   {Enter}");
    expect(screen.getByTestId("chat-send")).toBeDisabled();
    expect(sendChat).not.toHaveBeenCalled();
  });
});
