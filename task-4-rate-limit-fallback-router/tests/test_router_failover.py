"""Router failover: 429, timeout, raised exceptions, and full-outage sanitization."""

import pytest

from errors import GatewayError
from providers import FakeProvider
from router import CompletionRouter
from schemas import CompletionRequest


def make_request(tenant_key: str = "tenant-x") -> CompletionRequest:
    return CompletionRequest(
        tenant_key=tenant_key, prompt="hello", estimated_tokens=100
    )


async def test_primary_success_never_calls_secondary(limiter):
    primary = FakeProvider("ok", response="from primary")
    secondary = FakeProvider("ok", response="from secondary")
    router = CompletionRouter(primary, secondary, limiter)

    response = await router.complete(make_request())

    assert response.provider == "primary"
    assert response.text == "from primary"
    assert secondary.call_count == 0


async def test_primary_429_fails_over_to_secondary(limiter):
    primary = FakeProvider("rate_limited")
    secondary = FakeProvider("ok", response="from secondary")
    router = CompletionRouter(primary, secondary, limiter)

    response = await router.complete(make_request())

    assert response.provider == "secondary"
    assert response.text == "from secondary"


async def test_primary_timeout_fails_over_to_secondary(limiter):
    primary = FakeProvider("slow", delay_seconds=1.0)
    secondary = FakeProvider("ok", response="from secondary")
    router = CompletionRouter(primary, secondary, limiter, timeout_seconds=0.05)

    response = await router.complete(make_request())

    assert response.provider == "secondary"


async def test_primary_raised_exception_is_sanitized_and_does_not_fail_over(limiter):
    primary = FakeProvider("raise")
    secondary = FakeProvider("ok", response="from secondary")
    router = CompletionRouter(primary, secondary, limiter)

    with pytest.raises(GatewayError) as exc_info:
        await router.complete(make_request())

    error = exc_info.value
    assert error.error_type == "internal_error"
    assert "hunter2" not in error.message
    assert "traceback" not in error.message
    payload = error.to_payload()
    assert "hunter2" not in str(payload)
    assert secondary.call_count == 0


async def test_both_providers_down_returns_sanitized_upstream_unavailable(limiter):
    primary = FakeProvider("slow", delay_seconds=1.0)
    secondary = FakeProvider("raise")
    router = CompletionRouter(primary, secondary, limiter, timeout_seconds=0.05)

    with pytest.raises(GatewayError) as exc_info:
        await router.complete(make_request())

    error = exc_info.value
    assert error.error_type == "upstream_unavailable"
    assert "hunter2" not in str(error.to_payload())


async def test_rate_limited_tenant_never_reaches_a_provider(limiter):
    primary = FakeProvider("ok")
    secondary = FakeProvider("ok")
    router = CompletionRouter(primary, secondary, limiter)

    over_limit = CompletionRequest(
        tenant_key="tenant-y", prompt="hi", estimated_tokens=50_001
    )

    with pytest.raises(GatewayError) as exc_info:
        await router.complete(over_limit)

    assert exc_info.value.error_type == "rate_limited"
    assert primary.call_count == 0
    assert secondary.call_count == 0
