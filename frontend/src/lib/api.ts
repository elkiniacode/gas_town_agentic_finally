import type {
  ChatHistoryResponse,
  ChatResponse,
  HealthResponse,
  Portfolio,
  PortfolioHistoryResponse,
  TradeRequest,
  TradeResponse,
  WatchlistResponse,
} from "./types";

/**
 * API origin (R32). Empty in production (same origin); set NEXT_PUBLIC_API_BASE
 * in frontend/.env.local (e.g. http://localhost:8000) when running `next dev`.
 */
export function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/+$/, "");
}

export function apiUrl(path: string): string {
  return `${apiBase()}${path}`;
}

/** Non-2xx response. `detail` is the contract's `{"detail": "<string>"}` message. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch {
    throw new ApiError(0, "Network error: could not reach the server");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  getWatchlist: () => request<WatchlistResponse>("/api/watchlist"),
  addToWatchlist: (ticker: string) => post<WatchlistResponse>("/api/watchlist", { ticker }),
  removeFromWatchlist: (ticker: string) =>
    request<WatchlistResponse>(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),

  getPortfolio: () => request<Portfolio>("/api/portfolio"),
  trade: (body: TradeRequest) => post<TradeResponse>("/api/portfolio/trade", body),
  getPortfolioHistory: (limit?: number) =>
    request<PortfolioHistoryResponse>(`/api/portfolio/history${limit === undefined ? "" : `?limit=${limit}`}`),

  sendChat: (message: string) => post<ChatResponse>("/api/chat", { message }),
  getChatHistory: (limit?: number) =>
    request<ChatHistoryResponse>(`/api/chat/history${limit === undefined ? "" : `?limit=${limit}`}`),
};

export type Api = typeof api;

export const PRICE_STREAM_PATH = "/api/stream/prices";
