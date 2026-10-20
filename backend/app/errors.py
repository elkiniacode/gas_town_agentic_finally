"""Error handlers: every error body is ``{"detail": "<string>"}`` (R7).

FastAPI's default 422 for request validation is converted to
``400 {"detail": "Invalid request: <field>: <reason>"}`` (API_CONTRACT.md §Errors).
"""

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_LOCATION_KINDS = {"body", "query", "path", "header", "cookie"}


def _field_name(loc: Sequence[Any]) -> str:
    parts = list(loc)
    if parts and parts[0] in _LOCATION_KINDS:
        kind, parts = parts[0], parts[1:]
    else:
        kind = "body"
    # A JSON decode error's loc is ("body", <char offset>): report it as the body.
    if not parts or all(isinstance(p, int) for p in parts):
        return kind
    return ".".join(str(p) for p in parts)


def validation_detail(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request: body: invalid"
    first = errors[0]
    return f"Invalid request: {_field_name(first.get('loc', ()))}: {first.get('msg', 'invalid')}"


async def _request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": validation_detail(exc)})


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
