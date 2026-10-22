import logging
import sqlite3
from pathlib import Path
from unittest.mock import patch

from rpa_billing.client import ApiResult
from rpa_billing.config import Config
from rpa_billing.processor import batch_id_for, process, read_unique_ids
from rpa_billing.storage import connect


def test_input_is_normalized_and_deduplicated(tmp_path: Path) -> None:
    path = tmp_path / "cuentas.csv"
    path.write_text('id_cuenta\n7\n "42"\n7\n\nabc\n\n', encoding="utf-8")
    assert read_unique_ids(path) == ["7", "42", "abc"]


def test_success_is_terminal(tmp_path: Path) -> None:
    connection = connect(tmp_path / "state.db")
    connection.execute(
        "INSERT INTO accounts(batch_id, account_id, status) VALUES ('batch', '7', 'SUCCESS')"
    )
    connection.commit()
    assert connection.execute(
        "SELECT status FROM accounts WHERE batch_id = 'batch' AND account_id = '7'"
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
        process(input_path, "batch", config, connection, logging.getLogger("test"))
    fetch.assert_called_once_with(
        config.base_url, 0, config.timeout_seconds,
        config.max_attempts, config.backoff_seconds,
    )
    assert connection.execute(
        "SELECT status FROM accounts WHERE batch_id = 'batch' AND account_id = '0'"
    ).fetchone()[0] == "BUSINESS_NOT_FOUND"
    connection.close()


def test_batch_id_is_stable_for_same_file_and_changes_with_date(tmp_path: Path) -> None:
    path = tmp_path / "cuentas.csv"
    path.write_text("id_cuenta\n7\n", encoding="utf-8")
    from datetime import date

    first = batch_id_for(path, date(2026, 10, 22))
    same = batch_id_for(path, date(2026, 10, 22))
    next_day = batch_id_for(path, date(2026, 10, 23))
    assert first == same
    assert first != next_day


def test_same_account_is_processed_again_in_new_batch(tmp_path: Path) -> None:
    input_path = tmp_path / "cuentas.csv"
    input_path.write_text("id_cuenta\n7\n", encoding="utf-8")
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
    result = ApiResult("SUCCESS", title="ok", attempts=1)
    with patch("rpa_billing.processor.fetch_post", return_value=result) as fetch:
        process(input_path, "batch-1", config, connection, logging.getLogger("test"))
        process(input_path, "batch-2", config, connection, logging.getLogger("test"))
    assert fetch.call_count == 2
    assert connection.execute(
        "SELECT COUNT(*) FROM accounts WHERE account_id = '7'"
    ).fetchone()[0] == 2
    connection.close()


def test_duplicate_appearances_are_saved_without_duplicate_calls(tmp_path: Path) -> None:
    input_path = tmp_path / "cuentas.csv"
    input_path.write_text("id_cuenta\n7\n 7 \n\"7\"\n", encoding="utf-8")
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
        return_value=ApiResult("SUCCESS", title="ok", attempts=1),
    ) as fetch:
        repeated_ids, extra_appearances = process(
            input_path, "batch", config, connection, logging.getLogger("test")
        )
    assert fetch.call_count == 1
    assert (repeated_ids, extra_appearances) == (1, 2)
    row = connection.execute(
        "SELECT appearances FROM accounts "
        "WHERE batch_id = 'batch' AND account_id = '7'"
    ).fetchone()
    assert row[0] == 3
    connection.close()
