from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Config:
    base_url: str
    timeout_seconds: float
    max_attempts: int
    backoff_seconds: float
    state_db: Path
    output_xlsx: Path
    log_dir: Path
    log_level: str


def load_config(path: Path) -> Config:
    with path.open("rb") as file:
        data = tomllib.load(file)
    api = data["api"]
    paths = data["paths"]
    logging_config = data.get("logging", {})
    config = Config(
        base_url=str(api["base_url"]).rstrip("/"),
        timeout_seconds=float(api["timeout_seconds"]),
        max_attempts=int(api["max_attempts"]),
        backoff_seconds=float(api["backoff_seconds"]),
        state_db=Path(paths["state_db"]),
        output_xlsx=Path(paths["output_xlsx"]),
        log_dir=Path(paths["log_dir"]),
        log_level=str(logging_config.get("level", "INFO")).upper(),
    )
    if config.max_attempts < 1 or config.timeout_seconds <= 0:
        raise ValueError("max_attempts debe ser >= 1 y timeout_seconds positivo")
    return config
