from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import Database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A throwaway SQLite path; the parent dir doesn't exist yet (init must create it)."""
    return tmp_path / "data" / "finally.db"


@pytest.fixture
def settings(db_path: Path, tmp_path: Path) -> Settings:
    # static_dir points somewhere empty so a developer's backend/static/ never leaks in.
    return Settings(db_path=db_path, static_dir=tmp_path / "no-static", llm_mock=True)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """TestClient with the lifespan running (DB initialized and seeded)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(client: TestClient) -> Database:
    return client.app.state.db
