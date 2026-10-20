"""Chat routes — implemented by the LLM chat bead.

Endpoints (API_CONTRACT.md §Chat), paths relative to ``/api``:
    POST /chat
    GET  /chat/history
"""

from fastapi import APIRouter

router = APIRouter(tags=["chat"])
