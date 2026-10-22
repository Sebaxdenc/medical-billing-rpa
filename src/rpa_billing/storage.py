import sqlite3
from pathlib import Path
from typing import Iterator


TERMINAL_STATUSES = {"SUCCESS", "BUSINESS_NOT_FOUND", "BUSINESS_ERROR", "INVALID_INPUT"}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    connection.commit()
    return connection


def get(connection: sqlite3.Connection, account_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
    ).fetchone()


def save(connection: sqlite3.Connection, record: dict[str, object]) -> None:
    connection.execute(
        """INSERT INTO accounts(account_id, status, title, body, error, attempts)
        VALUES (:account_id, :status, :title, :body, :error, :attempts)
        ON CONFLICT(account_id) DO UPDATE SET
          status=excluded.status, title=excluded.title, body=excluded.body,
          error=excluded.error, attempts=excluded.attempts,
          updated_at=CURRENT_TIMESTAMP""",
        record,
    )
    connection.commit()


def all_records(connection: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    yield from connection.execute("SELECT * FROM accounts ORDER BY account_id")
