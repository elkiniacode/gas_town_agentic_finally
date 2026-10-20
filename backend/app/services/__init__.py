"""Service layer: watchlist and portfolio logic shared by the REST routes and the chat bead.

The chat bead calls these functions directly (not via HTTP) so manual and
chat-initiated actions share validation, error strings and the trade lock.
Business-rule failures raise :class:`app.errors.BadRequest` (``.detail`` is the
contract string); trade failures raise its subclass :class:`TradeError`.
"""

from app.services.portfolio import (
    get_history,
    get_portfolio,
    load_portfolio,
    record_snapshot,
    run_snapshot_loop,
)
from app.services.tickers import INVALID_TICKER, normalize_ticker
from app.services.trading import (
    ExecutedTrade,
    TradeError,
    execute_trade,
    normalize_quantity,
    normalize_side,
)
from app.services.watchlist import add_to_watchlist, get_watchlist, remove_from_watchlist

__all__ = [
    "INVALID_TICKER",
    "ExecutedTrade",
    "TradeError",
    "add_to_watchlist",
    "execute_trade",
    "get_history",
    "get_portfolio",
    "get_watchlist",
    "load_portfolio",
    "normalize_quantity",
    "normalize_side",
    "normalize_ticker",
    "record_snapshot",
    "remove_from_watchlist",
    "run_snapshot_loop",
]
