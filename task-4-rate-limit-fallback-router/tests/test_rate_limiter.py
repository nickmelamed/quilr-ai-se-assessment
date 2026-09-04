"""Sliding window rate limiter: admission, boundary eviction, and concurrency."""

import asyncio
import time

import aiosqlite
import pytest

from errors import GatewayError
from rate_limiter import SlidingWindowRateLimiter


async def test_requests_under_the_limit_are_admitted_and_accumulate(limiter):
    await limiter.check_and_record("tenant-a", 20_000)
    await limiter.check_and_record("tenant-a", 20_000)
    # 40,000 used; a third request within budget should still be admitted.
    await limiter.check_and_record("tenant-a", 5_000)


async def test_request_that_would_exceed_the_limit_is_rejected_and_not_recorded(
    limiter,
):
    await limiter.check_and_record("tenant-b", 49_000)

    with pytest.raises(GatewayError) as exc_info:
        await limiter.check_and_record("tenant-b", 2_000)

    assert exc_info.value.error_type == "rate_limited"
    assert exc_info.value.retry_after_seconds is not None

    # The rejected request must not have been recorded: there's still exactly
    # 1,000 tokens of headroom left, not 1,000 - 2,000.
    await limiter.check_and_record("tenant-b", 1_000)
    with pytest.raises(GatewayError):
        await limiter.check_and_record("tenant-b", 1)


async def test_tenants_are_isolated(limiter):
    await limiter.check_and_record("tenant-c", 50_000)

    # A different tenant starts with a fresh budget.
    await limiter.check_and_record("tenant-d", 50_000)


async def test_expired_rows_are_evicted_from_the_window(tmp_path):
    db_path = tmp_path / "rate_limiter.db"
    rate_limiter = SlidingWindowRateLimiter(
        str(db_path), limit_tokens=50_000, window_seconds=60.0
    )
    await rate_limiter.init()

    # Backdate a row to just past the window edge, simulating a request that
    # happened over a minute ago, without sleeping in the test.
    stale_ts = time.time() - 61.0
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            "INSERT INTO usage (tenant_key, ts, tokens) VALUES (?, ?, ?)",
            ("tenant-e", stale_ts, 49_000),
        )
        await db.commit()

    # If the stale row still counted, this would exceed the 50,000 budget.
    await rate_limiter.check_and_record("tenant-e", 49_000)


async def test_concurrent_requests_for_the_same_tenant_are_serialized(limiter):
    results = await asyncio.gather(
        limiter.check_and_record("tenant-f", 30_000),
        limiter.check_and_record("tenant-f", 30_000),
        return_exceptions=True,
    )

    successes = [r for r in results if r is None]
    failures = [r for r in results if isinstance(r, GatewayError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].error_type == "rate_limited"
