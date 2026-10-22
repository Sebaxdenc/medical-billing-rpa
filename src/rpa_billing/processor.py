import csv
from collections import Counter
from datetime import date
import hashlib
import logging
import sqlite3
from pathlib import Path

from .client import fetch_post
from .config import Config
from .storage import TERMINAL_STATUSES, get, save


def normalize(raw: str) -> str:
    return raw.strip().strip('"').strip()


def read_unique_ids(path: Path) -> list[str]:
    return list(read_id_counts(path))


def read_id_counts(path: Path) -> dict[str, int]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or "id_cuenta" not in reader.fieldnames:
            raise ValueError("El CSV debe tener la columna id_cuenta")
        counts: Counter[str] = Counter()
        for row in reader:
            account_id = normalize(row.get("id_cuenta", ""))
            counts[account_id] += 1
        return dict(counts)


def batch_id_for(path: Path, batch_date: date | None = None) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return f"{batch_date or date.today():%Y-%m-%d}-{digest}"


def process(
    input_path: Path,
    batch_id: str,
    config: Config,
    connection: sqlite3.Connection,
    logger: logging.Logger,
) -> tuple[int, int]:
    id_counts = read_id_counts(input_path)
    repeated_ids = sum(1 for count in id_counts.values() if count > 1)
    extra_appearances = sum(count - 1 for count in id_counts.values() if count > 1)
    for raw_id, appearances in id_counts.items():
        if appearances > 1:
            logger.warning("ID %s aparece %s veces en el CSV", raw_id, appearances)
        previous = get(connection, batch_id, raw_id)
        if previous is not None and previous["status"] in TERMINAL_STATUSES:
            logger.info("Omitido %s: estado terminal %s", raw_id, previous["status"])
            continue
        if not raw_id.isdigit():
            save(connection, {
                "batch_id": batch_id,
                "account_id": raw_id, "appearances": appearances,
                "status": "INVALID_INPUT", "title": "",
                "body": "", "error": "Debe ser un entero no negativo", "attempts": 0,
            })
            logger.warning("ID inválido: %r", raw_id)
            continue
        result = fetch_post(
            config.base_url, int(raw_id), config.timeout_seconds,
            config.max_attempts, config.backoff_seconds,
        )
        save(connection, {
            "batch_id": batch_id,
            "account_id": raw_id, "appearances": appearances,
            "status": result.status, "title": result.title,
            "body": result.body, "error": result.error, "attempts": result.attempts,
        })
        logger.info("%s -> %s (intentos=%s)", raw_id, result.status, result.attempts)
    return repeated_ids, extra_appearances
