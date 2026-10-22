from dataclasses import dataclass
import time
from typing import Callable

import requests


@dataclass(frozen=True)
class ApiResult:
    status: str
    title: str = ""
    body: str = ""
    error: str = ""
    attempts: int = 0


def fetch_post(
    base_url: str,
    account_id: int,
    timeout: float,
    max_attempts: int,
    backoff_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> ApiResult:
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(f"{base_url}/{account_id}", timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as error:
            if attempt == max_attempts:
                return ApiResult("TECHNICAL_FAILED", error=str(error), attempts=attempt)
            sleep(backoff_seconds * 2 ** (attempt - 1))
            continue

        if response.status_code == 404:
            return ApiResult("BUSINESS_NOT_FOUND", error="HTTP 404", attempts=attempt)
        if 500 <= response.status_code <= 599:
            if attempt == max_attempts:
                return ApiResult(
                    "TECHNICAL_FAILED",
                    error=f"HTTP {response.status_code}",
                    attempts=attempt,
                )
            sleep(backoff_seconds * 2 ** (attempt - 1))
            continue
        if 400 <= response.status_code <= 499:
            return ApiResult("BUSINESS_ERROR", error=f"HTTP {response.status_code}", attempts=attempt)
        try:
            payload = response.json()
            return ApiResult(
                "SUCCESS",
                title=str(payload.get("title", "")),
                body=str(payload.get("body", "")),
                attempts=attempt,
            )
        except (ValueError, AttributeError) as error:
            if attempt == max_attempts:
                return ApiResult("TECHNICAL_FAILED", error=str(error), attempts=attempt)
            sleep(backoff_seconds * 2 ** (attempt - 1))
    raise RuntimeError("La política de reintentos terminó sin resultado")
