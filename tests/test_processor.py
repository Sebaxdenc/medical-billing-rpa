import logging
import sqlite3
from pathlib import Path
from unittest.mock import patch

from rpa_billing.client import ApiResult
from rpa_billing.config import Config
from rpa_billing.processor import process, read_unique_ids
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


def test_zero_is_sent_to_api(tmp_path: Path) -> None:
    input_path = tmp_path / "cuentas.csv"
    input_path.write_text("id_cuenta\n0\n", encoding="utf-8")
    config = Config(
        base_url="https://example.test/posts",
        timeout_seconds=1,
        max_attempts=1,
        backoff_seconds=0,
        state_db=tmp_path / "state.db",
        output_xlsx=tmp_path / "result.xlsx",
        log_dir=tmp_path / "logs",
        log_level="INFO",
    )
    connection = connect(config.state_db)
    with patch(
        "rpa_billing.processor.fetch_post",
        return_value=ApiResult("BUSINESS_NOT_FOUND", error="HTTP 404", attempts=1),
    ) as fetch:
        process(input_path, config, connection, logging.getLogger("test"))
    fetch.assert_called_once_with(
        config.base_url, 0, config.timeout_seconds,
        config.max_attempts, config.backoff_seconds,
    )
    assert connection.execute(
        "SELECT status FROM accounts WHERE account_id = '0'"
    ).fetchone()[0] == "BUSINESS_NOT_FOUND"
    connection.close()
