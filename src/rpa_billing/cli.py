import argparse
import logging
from datetime import datetime
from pathlib import Path

from .config import load_config
from .processor import process
from .report import summarize, write_excel
from .storage import connect


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolida cuentas médicas desde una API.")
    parser.add_argument("--input", type=Path, default=Path("cuentas.csv"))
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()
    config = load_config(args.config)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = config.log_dir / f"run-{datetime.now():%Y%m%d-%H%M%S}.log"
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )
    logger = logging.getLogger("rpa_billing")
    connection = connect(config.state_db)
    try:
        process(args.input, config, connection, logger)
        write_excel(connection, config.output_xlsx)
        summarize(connection, logger)
    finally:
        connection.close()
