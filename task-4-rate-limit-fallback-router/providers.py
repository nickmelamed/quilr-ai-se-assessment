"""Provider interface and a fake implementation for exercising failover paths.

No real LLM API key is wired up here. `FakeProvider` stands in for a primary/
secondary model endpoint, the same "stub provider" scoping used in
task-3-llm-streaming-guardrail. Its `mode` selects which failure case it simulates so
tests can drive the router's failover logic deterministically.
"""

import asyncio
from typing import Literal, Protocol

ProviderMode = Literal["ok", "rate_limited", "slow", "raise"]


class Provider(Protocol):
    """Anything the router can call to produce a completion."""

    async def complete(self, prompt: str) -> str: ...


class ProviderHTTPError(Exception):
    """Raised by a provider to simulate an HTTP error status from the upstream."""

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(message or f"upstream returned {status_code}")
        self.status_code = status_code


class FakeProvider:
    """A configurable stand-in model provider used for tests and local demos."""

    def __init__(
        self,
        mode: ProviderMode = "ok",
        *,
        response: str = "Here is a completion.",
        delay_seconds: float = 0.0,
    ) -> None:
        self._mode = mode
        self._response = response
        self._delay_seconds = delay_seconds
        self.call_count = 0

    async def complete(self, prompt: str) -> str:
        self.call_count += 1
        if self._mode == "ok":
            return self._response
        if self._mode == "rate_limited":
            raise ProviderHTTPError(429, "rate limited by upstream")
        if self._mode == "slow":
            await asyncio.sleep(self._delay_seconds)
            return self._response
        if self._mode == "raise":
            raise RuntimeError(
                "boom: internal upstream traceback line 42, db password=hunter2"
            )
        raise AssertionError(f"unknown provider mode: {self._mode}")
