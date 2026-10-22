from collections import Counter
from pathlib import Path
import logging
import sqlite3

from openpyxl import Workbook


def write_excel(connection: sqlite3.Connection, path: Path, batch_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Resultados"
    sheet.append([
        "id_cuenta", "apariciones", "estado", "titulo", "detalle", "error",
        "intentos",
    ])
    for record in connection.execute(
        "SELECT account_id, appearances, status, title, body, error, attempts "
        "FROM accounts WHERE batch_id = ? ORDER BY account_id",
        (batch_id,),
    ):
        sheet.append(list(record))
    workbook.save(path)


def summarize(
    connection: sqlite3.Connection,
    batch_id: str,
    logger: logging.Logger,
    repeated_ids: int,
    extra_appearances: int,
) -> dict[str, int]:
    counts = Counter(
        row[0] for row in connection.execute(
            "SELECT status FROM accounts WHERE batch_id = ?", (batch_id,)
        )
    )
    summary = dict(sorted(counts.items()))
    logger.info(
        "Resumen final: %s; IDs repetidos: %s; apariciones duplicadas adicionales: %s",
        summary,
        repeated_ids,
        extra_appearances,
    )
    return summary
