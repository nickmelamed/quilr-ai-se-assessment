"""End-to-end HTTP checks: success, standardized 429, and sanitized 502 payloads."""

import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient

import gateway
from providers import FakeProvider
from rate_limiter import SlidingWindowRateLimiter
from router import CompletionRouter

client = TestClient(gateway.app)


def _build_router(tmp_path, primary_mode: str = "ok") -> CompletionRouter:
    db_path = tmp_path / "rate_limiter.db"
    rate_limiter = SlidingWindowRateLimiter(str(db_path))
    asyncio.run(rate_limiter.init())
    return CompletionRouter(
        primary=FakeProvider(primary_mode, response="from primary"),
        secondary=FakeProvider("ok", response="from secondary"),
        rate_limiter=rate_limiter,
    )


def test_completions_returns_a_successful_response(tmp_path):
    with patch("gateway.completion_router", new=_build_router(tmp_path)):
        response = client.post(
            "/v1/completions",
            json={"tenant_key": "t1", "prompt": "hi", "estimated_tokens": 100},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "primary"
    assert body["text"] == "from primary"


def test_completions_rate_limited_returns_standardized_429_payload(tmp_path):
    with patch("gateway.completion_router", new=_build_router(tmp_path)):
        response = client.post(
            "/v1/completions",
            json={"tenant_key": "t2", "prompt": "hi", "estimated_tokens": 50_001},
        )

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["type"] == "rate_limited"
    assert "retry_after_seconds" in body["error"]


def test_completions_provider_exception_returns_sanitized_502(tmp_path):
    with patch(
        "gateway.completion_router", new=_build_router(tmp_path, primary_mode="raise")
    ):
        response = client.post(
            "/v1/completions",
            json={"tenant_key": "t3", "prompt": "hi", "estimated_tokens": 100},
        )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["type"] == "internal_error"
    assert "hunter2" not in str(body)
    assert "traceback" not in str(body)
