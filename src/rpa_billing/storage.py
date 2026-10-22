import sqlite3
from pathlib import Path
from typing import Iterator


TERMINAL_STATUSES = {
    "SUCCESS",
    "BUSINESS_NOT_FOUND",
    "BUSINESS_ERROR",
    "CONFIGURATION_ERROR",
    "INVALID_INPUT",
}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(accounts)")
    }
    if columns and "batch_id" not in columns:
        connection.execute("ALTER TABLE accounts RENAME TO accounts_legacy")
    elif columns and "appearances" not in columns:
        connection.execute(
            "ALTER TABLE accounts ADD COLUMN appearances INTEGER NOT NULL DEFAULT 1"
        )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS accounts (
            batch_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            appearances INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (batch_id, account_id)
        )"""
    )
    if columns and "batch_id" not in columns:
        connection.execute(
            """INSERT INTO accounts
            (batch_id, account_id, appearances, status, title, body, error, attempts, updated_at)
            SELECT 'legacy', account_id, 1, status, title, body, error, attempts, updated_at
            FROM accounts_legacy"""
        )
    connection.commit()
    return connection


def get(
    connection: sqlite3.Connection, batch_id: str, account_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM accounts WHERE batch_id = ? AND account_id = ?",
        (batch_id, account_id),
    ).fetchone()


def save(connection: sqlite3.Connection, record: dict[str, object]) -> None:
    connection.execute(
        """INSERT INTO accounts
        (batch_id, account_id, appearances, status, title, body, error, attempts)
        VALUES (:batch_id, :account_id, :appearances, :status, :title, :body, :error, :attempts)
        ON CONFLICT(batch_id, account_id) DO UPDATE SET
          appearances=excluded.appearances, status=excluded.status,
          title=excluded.title, body=excluded.body,
          error=excluded.error, attempts=excluded.attempts,
          updated_at=CURRENT_TIMESTAMP""",
        record,
    )
    connection.commit()


def all_records(connection: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    yield from connection.execute(
        "SELECT * FROM accounts ORDER BY batch_id, account_id"
    )
