"""Thin SQLite access layer shared by every router and background task.

Each ``connect()`` / ``transaction()`` call opens its own short-lived
connection, so there is no shared connection state across requests or tasks.
Connections run in autocommit mode (``isolation_level=None``); writes that must
be atomic go through ``transaction()``, which wraps them in ``BEGIN IMMEDIATE``.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from app.storage.seed import seed_defaults

BUSY_TIMEOUT_MS = 5000

TABLES = (
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
)


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """A connection for reads (or single-statement writes); closed on exit."""
        conn = _open(self.path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """A connection inside ``BEGIN IMMEDIATE``: committed on success, rolled back on error.

        IMMEDIATE takes the write lock up front, so read-then-write logic (e.g.
        check cash, then debit it) can't interleave with another writer.
        """
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")


def schema_sql() -> str:
    return resources.files("app.storage").joinpath("schema.sql").read_text(encoding="utf-8")


def init_database(path: Path) -> Database:
    """Create the parent directory, schema (if missing) and seed data (if fresh).

    Idempotent: called once per process from the FastAPI lifespan (S2), and
    safe against an existing, already-seeded database.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    with db.connect() as conn:
        # WAL lets SSE/portfolio reads proceed while a trade is writing.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(schema_sql())
    with db.transaction() as conn:
        seed_defaults(conn)
    return db
