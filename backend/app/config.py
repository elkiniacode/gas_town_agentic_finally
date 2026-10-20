"""Runtime configuration from environment variables (PLAN.md §5).

Every variable is optional. Empty strings are treated the same as unset.
When running locally, the repository-root ``.env`` is loaded first; real
environment variables always take precedence over it (R34).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_DB_PATH = REPO_ROOT / "db" / "finally.db"
DEFAULT_STATIC_DIR = BACKEND_DIR / "static"
DEFAULT_MASSIVE_POLL_SECONDS = 15.0
DEV_CORS_ORIGINS = ("http://localhost:3000",)


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    static_dir: Path = DEFAULT_STATIC_DIR
    openrouter_api_key: str | None = None
    massive_api_key: str | None = None
    massive_poll_seconds: float = DEFAULT_MASSIVE_POLL_SECONDS
    llm_mock: bool = False
    dev_mode: bool = False

    @property
    def llm_configured(self) -> bool:
        """True when chat can run: mock mode, or an OpenRouter key is present (R3)."""
        return self.llm_mock or self.openrouter_api_key is not None

    @property
    def use_massive(self) -> bool:
        return self.massive_api_key is not None


def _get(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _get_bool(env: Mapping[str, str], name: str) -> bool:
    return (_get(env, name) or "").lower() == "true"


def _get_float(env: Mapping[str, str], name: str, default: float) -> float:
    value = _get(env, name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0, got {value!r}")
    return parsed


def settings_from_env(env: Mapping[str, str]) -> Settings:
    """Build Settings from a mapping of environment variables (no ``.env`` loading)."""
    db_path = _get(env, "DB_PATH")
    return Settings(
        db_path=Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH,
        openrouter_api_key=_get(env, "OPENROUTER_API_KEY"),
        massive_api_key=_get(env, "MASSIVE_API_KEY"),
        massive_poll_seconds=_get_float(env, "MASSIVE_POLL_SECONDS", DEFAULT_MASSIVE_POLL_SECONDS),
        llm_mock=_get_bool(env, "LLM_MOCK"),
        dev_mode=_get_bool(env, "DEV_MODE"),
    )


def load_settings(dotenv_path: Path | None = REPO_ROOT / ".env") -> Settings:
    """Load the root ``.env`` (if present, without overriding real env vars), then read env."""
    if dotenv_path is not None and dotenv_path.is_file():
        load_dotenv(dotenv_path, override=False)
    return settings_from_env(os.environ)
