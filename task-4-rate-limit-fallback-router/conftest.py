"""Ensures the task-4-rate-limit-fallback-router package root is importable from
tests/, and provides a fresh on-disk SQLite rate limiter per test.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rate_limiter import SlidingWindowRateLimiter


@pytest.fixture
async def limiter(tmp_path: Path) -> SlidingWindowRateLimiter:
    """A SlidingWindowRateLimiter backed by a fresh on-disk SQLite file per test."""
    db_path = tmp_path / "rate_limiter.db"
    rate_limiter = SlidingWindowRateLimiter(str(db_path))
    await rate_limiter.init()
    return rate_limiter
