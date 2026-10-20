# FinAlly: one image, one port (PLAN.md §11, R5, R33, R37).
# Stage 1 builds the Next.js static export; stage 2 runs FastAPI, which serves it.

# ---- Stage 1: frontend static export -> /frontend/out ----
FROM node:22-slim AS frontend

WORKDIR /frontend
ENV NEXT_TELEMETRY_DISABLED=1 \
    # Same-origin API in production (R32); never inherit a dev value.
    NEXT_PUBLIC_API_BASE=""

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/backend/.venv/bin:$PATH"

# The backend lives at /app/backend so /app/db belongs to the volume alone (R33).
WORKDIR /app/backend

# Dependencies first so code changes don't invalidate this layer.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./
COPY --from=frontend /frontend/out/ ./static/

ENV DB_PATH=/app/db/finally.db

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --start-interval=1s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=3).status == 200 else 1)"]

# Single worker (R20). An open SSE stream otherwise holds graceful shutdown
# until Docker's SIGKILL, so cap it to keep `docker stop` prompt.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--timeout-graceful-shutdown", "2"]
