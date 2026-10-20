from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import DEFAULT_DB_PATH, REPO_ROOT, load_settings, settings_from_env
from app.timeutil import parse_iso, to_iso


def test_defaults_when_env_empty() -> None:
    s = settings_from_env({})
    assert s.db_path == DEFAULT_DB_PATH == REPO_ROOT / "db" / "finally.db"
    assert s.openrouter_api_key is None
    assert s.massive_api_key is None
    assert s.massive_poll_seconds == 15.0
    assert s.llm_mock is False
    assert s.dev_mode is False
    assert s.llm_configured is False
    assert s.use_massive is False


def test_empty_strings_are_unset() -> None:
    s = settings_from_env(
        {"DB_PATH": "", "OPENROUTER_API_KEY": "  ", "MASSIVE_API_KEY": "", "LLM_MOCK": ""}
    )
    assert s.db_path == DEFAULT_DB_PATH
    assert s.openrouter_api_key is None
    assert s.massive_api_key is None
    assert s.llm_mock is False


def test_values_are_read() -> None:
    s = settings_from_env(
        {
            "DB_PATH": "/app/db/finally.db",
            "OPENROUTER_API_KEY": "sk-or-123",
            "MASSIVE_API_KEY": "mk",
            "MASSIVE_POLL_SECONDS": "5",
            "LLM_MOCK": "TRUE",
            "DEV_MODE": "true",
        }
    )
    assert s.db_path == Path("/app/db/finally.db")
    assert s.openrouter_api_key == "sk-or-123"
    assert s.use_massive is True
    assert s.massive_poll_seconds == 5.0
    assert s.llm_mock is True
    assert s.dev_mode is True


@pytest.mark.parametrize("value", ["false", "1", "yes", "no"])
def test_only_true_enables_flags(value: str) -> None:
    assert settings_from_env({"LLM_MOCK": value, "DEV_MODE": value}).llm_mock is False


def test_llm_configured_by_key_or_mock() -> None:
    assert settings_from_env({"OPENROUTER_API_KEY": "k"}).llm_configured is True
    assert settings_from_env({"LLM_MOCK": "true"}).llm_configured is True


@pytest.mark.parametrize("value", ["abc", "0", "-3"])
def test_bad_poll_seconds_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="MASSIVE_POLL_SECONDS"):
        settings_from_env({"MASSIVE_POLL_SECONDS": value})


def test_dotenv_loaded_but_real_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("LLM_MOCK=true\nDB_PATH=/from/dotenv.db\n")
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.setenv("DB_PATH", "/from/env.db")
    s = load_settings(dotenv)
    assert s.llm_mock is True
    assert s.db_path == Path("/from/env.db")


def test_to_iso_format() -> None:
    dt = datetime(2026, 10, 18, 14, 3, 12, 500999, tzinfo=UTC)
    assert to_iso(dt) == "2026-10-18T14:03:12.500Z"
    assert parse_iso("2026-10-18T14:03:12.500Z") == dt.replace(microsecond=500000)


def test_to_iso_converts_to_utc_and_rejects_naive() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert to_iso(datetime(2026, 10, 18, 16, 0, tzinfo=plus_two)) == "2026-10-18T14:00:00.000Z"
    with pytest.raises(ValueError):
        to_iso(datetime(2026, 10, 18))
