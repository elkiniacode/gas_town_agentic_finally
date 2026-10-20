// Wire types mirroring planning/API_CONTRACT.md exactly (snake_case, ISO-8601 UTC strings).

// --- SSE: GET /api/stream/prices ---

export type PriceUpdate = {
  price: number;
  previous_price: number;
  open_price: number;
  timestamp: string;
};

export type PriceEvent = Record<string, PriceUpdate>;

// --- Watchlist ---

export type WatchlistItem = {
  ticker: string;
  price: number | null;
  previous_price: number | null;
  open_price: number | null;
  change_pct: number | null;
  added_at: string;
};

export type WatchlistResponse = { watchlist: WatchlistItem[] };

// --- Portfolio ---

export type Position = {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pnl_pct: number;
};

export type Portfolio = {
  cash_balance: number;
  positions: Position[];
  positions_value: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
};

export type TradeSide = "buy" | "sell";

export type TradeRequest = { ticker: string; quantity: number; side: TradeSide };

export type Trade = {
  id: string;
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  total: number;
  executed_at: string;
};

export type TradeResponse = { trade: Trade; portfolio: Portfolio };

export type PortfolioSnapshot = { total_value: number; recorded_at: string };

export type PortfolioHistoryResponse = { snapshots: PortfolioSnapshot[] };

// --- Chat ---

export type ActionStatus = "ok" | "failed";

export type WatchlistChangeResult = {
  ticker: string;
  action: "add" | "remove";
  status: ActionStatus;
  error: string | null;
};

export type TradeResult = {
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number | null;
  status: ActionStatus;
  error: string | null;
};

export type ChatActions = {
  watchlist_changes: WatchlistChangeResult[];
  trades: TradeResult[];
};

export type ChatResponse = { message: string; actions: ChatActions };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions: ChatActions | null;
  created_at: string;
};

export type ChatHistoryResponse = { messages: ChatMessage[] };

// --- System ---

export type HealthResponse = { status: "ok" };
