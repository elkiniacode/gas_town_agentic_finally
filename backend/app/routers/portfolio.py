"""Portfolio routes — implemented by the portfolio bead.

Endpoints (API_CONTRACT.md §Portfolio), paths relative to ``/api``:
    GET  /portfolio
    POST /portfolio/trade      (serialize with deps.get_trade_lock, R20)
    GET  /portfolio/history
"""

from fastapi import APIRouter

router = APIRouter(tags=["portfolio"])
