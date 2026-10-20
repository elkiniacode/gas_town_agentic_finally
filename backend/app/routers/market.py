"""Market data routes — implemented by the market-data bead (fin-k90.3).

Endpoints (API_CONTRACT.md §Market data), paths relative to ``/api``:
    GET /stream/prices   SSE, one batched event per tick
"""

from fastapi import APIRouter

router = APIRouter(tags=["market"])
