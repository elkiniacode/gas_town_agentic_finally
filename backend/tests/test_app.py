from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import Settings
from app.main import create_app


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_initializes_database(client: TestClient, settings: Settings) -> None:
    assert settings.db_path.is_file()
    assert client.app.state.db.path == settings.db_path
    assert client.app.state.settings is settings
    with client.app.state.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 10


def test_unknown_api_route_is_json_404(client: TestClient) -> None:
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_validation_errors_become_400_with_string_detail(app: FastAPI) -> None:
    class Body(BaseModel):
        ticker: str
        quantity: float

    @app.post("/api/_echo")
    def echo(body: Body) -> dict[str, str]:
        return {"ticker": body.ticker}

    with TestClient(app) as client:
        missing = client.post("/api/_echo", json={"quantity": 1})
        assert missing.status_code == 400
        assert missing.json() == {"detail": "Invalid request: ticker: Field required"}

        wrong_type = client.post("/api/_echo", json={"ticker": "AAPL", "quantity": "lots"})
        assert wrong_type.status_code == 400
        assert wrong_type.json()["detail"].startswith("Invalid request: quantity: ")

        bad_json = client.post(
            "/api/_echo", content=b"{not json", headers={"content-type": "application/json"}
        )
        assert bad_json.status_code == 400
        assert bad_json.json()["detail"].startswith("Invalid request: body: ")

        no_body = client.post("/api/_echo")
        assert no_body.status_code == 400
        assert no_body.json()["detail"].startswith("Invalid request: body: ")


def test_unhandled_errors_are_json_500(app: FastAPI) -> None:
    @app.get("/api/_boom")
    def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/_boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def _static_dir(tmp_path: Path) -> Path:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>FinAlly</html>")
    (static / "404.html").write_text("<html>missing</html>")
    return static


def test_static_frontend_served_at_root(settings: Settings, tmp_path: Path) -> None:
    app = create_app(replace(settings, static_dir=_static_dir(tmp_path)))
    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "FinAlly" in root.text

        # API routers are registered before the mount, so they still win.
        assert client.get("/api/health").json() == {"status": "ok"}

        # Unknown /api/* paths must be JSON, never the export's 404.html.
        api_missing = client.get("/api/nope")
        assert api_missing.status_code == 404
        assert api_missing.json() == {"detail": "Not Found"}


def test_static_mount_skipped_when_dir_missing(client: TestClient) -> None:
    assert client.get("/").status_code == 404


def test_cors_disabled_by_default(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_enabled_for_next_dev_in_dev_mode(settings: Settings) -> None:
    app = create_app(replace(settings, dev_mode=True))
    with TestClient(app) as client:
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"

        other = client.get("/api/health", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in other.headers
