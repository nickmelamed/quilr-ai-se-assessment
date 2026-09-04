"""Token-aware sliding window rate limiter, backed by on-disk SQLite.

Each accepted request is recorded as one row (tenant_key, timestamp, tokens). A
tenant's current usage is the sum of `tokens` for rows within the trailing
`window_seconds`, so the window slides continuously instead of resetting on a fixed
clock boundary. Expired rows are evicted on every check, which keeps the table
bounded without a separate cleanup job.
"""

import asyncio
import time
from collections import defaultdict

import aiosqlite

from errors import GatewayError

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS usage (
    tenant_key TEXT NOT NULL,
    ts REAL NOT NULL,
    tokens INTEGER NOT NULL
)
"""
_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_usage_tenant_ts ON usage (tenant_key, ts)
"""


class SlidingWindowRateLimiter:
    """Enforces a max-tokens-per-window budget per tenant, persisted to SQLite."""

    def __init__(
        self,
        db_path: str,
        *,
        limit_tokens: int = 50_000,
        window_seconds: float = 60.0,
    ) -> None:
        self._db_path = db_path
        self._limit_tokens = limit_tokens
        self._window_seconds = window_seconds
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def init(self) -> None:
        """Create the backing table/index if they don't already exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.execute(_CREATE_INDEX)
            await db.commit()

    async def check_and_record(self, tenant_key: str, tokens: int) -> None:
        """Admit `tokens` for `tenant_key`, or raise GatewayError('rate_limited', ...).

        Eviction of expired rows, the usage sum, and the admit decision all happen
        under a per-tenant lock so concurrent requests for the same tenant can't both
        pass a check that only fits one of them.
        """
        async with self._locks[tenant_key]:
            now = time.time()
            cutoff = now - self._window_seconds
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "DELETE FROM usage WHERE tenant_key = ? AND ts <= ?",
                    (tenant_key, cutoff),
                )
                cursor = await db.execute(
                    "SELECT COALESCE(SUM(tokens), 0) FROM usage WHERE tenant_key = ?",
                    (tenant_key,),
                )
                row = await cursor.fetchone()
                current_tokens = row[0] if row else 0

                if current_tokens + tokens > self._limit_tokens:
                    retry_after = await self._retry_after(db, tenant_key, cutoff)
                    await db.commit()
                    raise GatewayError(
                        "rate_limited",
                        f"Tenant '{tenant_key}' exceeded the {self._limit_tokens}"
                        f" token/{int(self._window_seconds)}s rate limit.",
                        retry_after_seconds=retry_after,
                    )

                await db.execute(
                    "INSERT INTO usage (tenant_key, ts, tokens) VALUES (?, ?, ?)",
                    (tenant_key, now, tokens),
                )
                await db.commit()

    async def _retry_after(
        self, db: aiosqlite.Connection, tenant_key: str, cutoff: float
    ) -> float:
        """Seconds until the oldest in-window row expires, freeing up capacity."""
        cursor = await db.execute(
            "SELECT MIN(ts) FROM usage WHERE tenant_key = ?", (tenant_key,)
        )
        row = await cursor.fetchone()
        oldest_ts = row[0] if row and row[0] is not None else None
        if oldest_ts is None:
            return self._window_seconds
        return max(0.0, (oldest_ts - cutoff))
