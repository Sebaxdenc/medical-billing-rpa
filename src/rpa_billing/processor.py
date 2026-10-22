import csv
import logging
import sqlite3
from pathlib import Path

from .client import fetch_post
from .config import Config
from .storage import TERMINAL_STATUSES, get, save


def normalize(raw: str) -> str:
    return raw.strip().strip('"').strip()


def read_unique_ids(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or "id_cuenta" not in reader.fieldnames:
            raise ValueError("El CSV debe tener la columna id_cuenta")
        result: list[str] = []
        seen: set[str] = set()
        for row in reader:
            account_id = normalize(row.get("id_cuenta", ""))
            if account_id not in seen:
                seen.add(account_id)
                result.append(account_id)
        return result


def process(input_path: Path, config: Config, connection: sqlite3.Connection, logger: logging.Logger) -> None:
    for raw_id in read_unique_ids(input_path):
        previous = get(connection, raw_id)
        if previous is not None and previous["status"] in TERMINAL_STATUSES:
            logger.info("Omitido %s: estado terminal %s", raw_id, previous["status"])
            continue
        if not raw_id.isdigit() or int(raw_id) < 1:
            save(connection, {
                "account_id": raw_id, "status": "INVALID_INPUT", "title": "",
                "body": "", "error": "Debe ser un entero positivo", "attempts": 0,
            })
            logger.warning("ID inválido: %r", raw_id)
            continue
        result = fetch_post(
            config.base_url, int(raw_id), config.timeout_seconds,
            config.max_attempts, config.backoff_seconds,
        )
        save(connection, {
            "account_id": raw_id, "status": result.status, "title": result.title,
            "body": result.body, "error": result.error, "attempts": result.attempts,
        })
        logger.info("%s -> %s (intentos=%s)", raw_id, result.status, result.attempts)
