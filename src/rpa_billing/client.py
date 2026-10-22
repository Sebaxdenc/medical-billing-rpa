from dataclasses import dataclass
from email.utils import parsedate_to_datetime
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


def retry_after_seconds(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None


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
        if response.status_code in (401, 403):
            return ApiResult(
                "CONFIGURATION_ERROR",
                error=f"HTTP {response.status_code}",
                attempts=attempt,
            )
        if response.status_code in (408, 429) or 500 <= response.status_code <= 599:
            if attempt == max_attempts:
                return ApiResult(
                    "TECHNICAL_FAILED",
                    error=f"HTTP {response.status_code}",
                    attempts=attempt,
                )
            delay = (
                retry_after_seconds(response)
                if response.status_code == 429
                else None
            )
            sleep(delay if delay is not None else backoff_seconds * 2 ** (attempt - 1))
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
