from unittest.mock import Mock, patch

from rpa_billing.client import fetch_post


def response(status_code: int, payload: dict | None = None) -> Mock:
    result = Mock()
    result.status_code = status_code
    result.json.return_value = payload or {}
    return result


def test_404_is_not_retried() -> None:
    with patch("rpa_billing.client.requests.get", return_value=response(404)) as get:
        result = fetch_post("https://example.test/posts", 999, 1, 3, 0)
    assert result.status == "BUSINESS_NOT_FOUND"
    assert result.attempts == 1
    get.assert_called_once()


def test_500_retries_with_exponential_backoff() -> None:
    sleeps: list[float] = []
    responses = [response(500), response(500), response(200, {"title": "ok"})]
    with patch("rpa_billing.client.requests.get", side_effect=responses):
        result = fetch_post("https://example.test/posts", 1, 1, 3, 1, sleeps.append)
    assert result.status == "SUCCESS"
    assert result.attempts == 3
    assert sleeps == [1, 2]


def test_408_is_retried() -> None:
    sleeps: list[float] = []
    responses = [response(408), response(200, {"title": "ok"})]
    with patch("rpa_billing.client.requests.get", side_effect=responses):
        result = fetch_post("https://example.test/posts", 1, 1, 3, 1, sleeps.append)
    assert result.status == "SUCCESS"
    assert result.attempts == 2
    assert sleeps == [1]


def test_429_uses_retry_after() -> None:
    first = response(429)
    first.headers = {"Retry-After": "7"}
    sleeps: list[float] = []
    with patch(
        "rpa_billing.client.requests.get",
        side_effect=[first, response(200, {"title": "ok"})],
    ):
        result = fetch_post("https://example.test/posts", 1, 1, 3, 1, sleeps.append)
    assert result.status == "SUCCESS"
    assert result.attempts == 2
    assert sleeps == [7]


def test_429_caps_retry_after_at_60_seconds() -> None:
    first = response(429)
    first.headers = {"Retry-After": "3600"}
    sleeps: list[float] = []
    with patch(
        "rpa_billing.client.requests.get",
        side_effect=[first, response(200, {"title": "ok"})],
    ):
        result = fetch_post("https://example.test/posts", 1, 1, 3, 1, sleeps.append)
    assert result.status == "SUCCESS"
    assert result.attempts == 2
    assert sleeps == [60]


def test_401_is_configuration_error_and_not_retried() -> None:
    with patch("rpa_billing.client.requests.get", return_value=response(401)) as get:
        result = fetch_post("https://example.test/posts", 1, 1, 3, 0)
    assert result.status == "CONFIGURATION_ERROR"
    assert result.attempts == 1
    get.assert_called_once()
