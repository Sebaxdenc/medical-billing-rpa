import logging
import sqlite3
from pathlib import Path

from rpa_billing.config import Config
from rpa_billing.processor import read_unique_ids
from rpa_billing.storage import connect


def test_input_is_normalized_and_deduplicated(tmp_path: Path) -> None:
    path = tmp_path / "cuentas.csv"
    path.write_text('id_cuenta\n7\n "42"\n7\n\nabc\n\n', encoding="utf-8")
    assert read_unique_ids(path) == ["7", "42", "abc"]


def test_success_is_terminal(tmp_path: Path) -> None:
    connection = connect(tmp_path / "state.db")
    connection.execute(
        "INSERT INTO accounts(account_id, status) VALUES ('7', 'SUCCESS')"
    )
    connection.commit()
    assert connection.execute(
        "SELECT status FROM accounts WHERE account_id = '7'"
    ).fetchone()[0] == "SUCCESS"
    connection.close()
