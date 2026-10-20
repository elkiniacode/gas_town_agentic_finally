import sqlite3
from pathlib import Path

import pytest

from app.storage import (
    DEFAULT_TICKERS,
    DEFAULT_USER_ID,
    STARTING_CASH,
    TABLES,
    Database,
    init_database,
)
from app.timeutil import parse_iso

EXPECTED_COLUMNS = {
    "users_profile": ["id", "cash_balance", "created_at"],
    "watchlist": ["id", "user_id", "ticker", "added_at"],
    "positions": ["id", "user_id", "ticker", "quantity", "avg_cost", "updated_at"],
    "trades": ["id", "user_id", "ticker", "side", "quantity", "price", "executed_at"],
    "portfolio_snapshots": ["id", "user_id", "total_value", "recorded_at"],
    "chat_messages": ["id", "user_id", "role", "content", "actions", "created_at"],
}


def _counts(db: Database) -> dict[str, int]:
    with db.connect() as conn:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def test_init_creates_parent_dir_and_all_tables(db_path: Path) -> None:
    assert not db_path.parent.exists()
    db = init_database(db_path)
    assert db_path.is_file()
    with db.connect() as conn:
        for table, columns in EXPECTED_COLUMNS.items():
            info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            assert [row["name"] for row in info] == columns, table


def test_user_id_defaults_to_default(db_path: Path) -> None:
    db = init_database(db_path)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO trades (id, ticker, side, quantity, price, executed_at)"
            " VALUES ('t1', 'AAPL', 'buy', 1, 190, '2026-10-18T14:00:00.000Z')"
        )
        row = conn.execute("SELECT user_id FROM trades WHERE id = 't1'").fetchone()
    assert row["user_id"] == "default"


def test_fresh_database_is_seeded(db_path: Path) -> None:
    db = init_database(db_path)
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users_profile").fetchall()
        tickers = [
            r["ticker"]
            for r in conn.execute("SELECT ticker FROM watchlist ORDER BY added_at, rowid")
        ]
        snapshots = conn.execute("SELECT * FROM portfolio_snapshots").fetchall()

    assert len(user) == 1
    assert user[0]["id"] == DEFAULT_USER_ID
    assert user[0]["cash_balance"] == STARTING_CASH
    assert tickers == list(DEFAULT_TICKERS)
    assert len(snapshots) == 1
    assert snapshots[0]["total_value"] == STARTING_CASH
    assert snapshots[0]["user_id"] == DEFAULT_USER_ID
    assert _counts(db) == {
        "users_profile": 1,
        "watchlist": 10,
        "positions": 0,
        "trades": 0,
        "portfolio_snapshots": 1,
        "chat_messages": 0,
    }


def test_seeded_timestamps_use_contract_format(db_path: Path) -> None:
    db = init_database(db_path)
    with db.connect() as conn:
        created_at = conn.execute("SELECT created_at FROM users_profile").fetchone()[0]
    assert len(created_at) == len("2026-10-18T14:03:12.500Z")
    assert created_at.endswith("Z")
    parse_iso(created_at)


def test_seeding_is_idempotent(db_path: Path) -> None:
    first = _counts(init_database(db_path))
    second = _counts(init_database(db_path))
    assert first == second


def test_reinit_does_not_restore_removed_defaults_or_reset_cash(db_path: Path) -> None:
    db = init_database(db_path)
    with db.transaction() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = 'NFLX'")
        conn.execute("UPDATE users_profile SET cash_balance = 1234.5")

    db = init_database(db_path)
    with db.connect() as conn:
        tickers = {r[0] for r in conn.execute("SELECT ticker FROM watchlist")}
        cash = conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0]
    assert "NFLX" not in tickers
    assert len(tickers) == 9
    assert cash == 1234.5


def test_init_adds_missing_tables_to_existing_file(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
    db = init_database(db_path)
    assert _counts(db)["watchlist"] == 10


def test_transaction_rolls_back_on_error(db_path: Path) -> None:
    db = init_database(db_path)
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute("UPDATE users_profile SET cash_balance = 0")
        raise RuntimeError("boom")
    with db.connect() as conn:
        assert conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == STARTING_CASH


def test_watchlist_ticker_is_unique_per_user(db_path: Path) -> None:
    db = init_database(db_path)
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO watchlist (id, ticker, added_at)"
            " VALUES ('dup', 'AAPL', '2026-10-18T14:00:00.000Z')"
        )


def test_check_constraints_reject_bad_enums(db_path: Path) -> None:
    db = init_database(db_path)
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO trades (id, ticker, side, quantity, price, executed_at)"
            " VALUES ('x', 'AAPL', 'hold', 1, 1, '2026-10-18T14:00:00.000Z')"
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, role, content, created_at)"
            " VALUES ('x', 'system', 'hi', '2026-10-18T14:00:00.000Z')"
        )
