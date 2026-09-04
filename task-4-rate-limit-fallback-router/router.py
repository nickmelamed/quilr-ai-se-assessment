"""Resilient completion router: rate limiting + primary/secondary failover.

`CompletionRouter.complete` is the single entry point: it enforces the tenant's
token budget, races the primary provider against a timeout, falls over to the
secondary on a 429 or timeout, and turns every other failure into a sanitized
`GatewayError` rather than letting a raw exception escape.
"""

import asyncio
import sys

from errors import GatewayError
from providers import Provider, ProviderHTTPError
from rate_limiter import SlidingWindowRateLimiter
from schemas import CompletionRequest, CompletionResponse


class CompletionRouter:
    """Ties the rate limiter and primary/secondary providers together."""

    def __init__(
        self,
        primary: Provider,
        secondary: Provider,
        rate_limiter: SlidingWindowRateLimiter,
        *,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._rate_limiter = rate_limiter
        self._timeout_seconds = timeout_seconds

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        """Route a completion request, failing over and sanitizing errors as needed."""
        await self._rate_limiter.check_and_record(req.tenant_key, req.estimated_tokens)

        try:
            text = await asyncio.wait_for(
                self._primary.complete(req.prompt), timeout=self._timeout_seconds
            )
            return CompletionResponse(
                text=text, provider="primary", tokens_used=req.estimated_tokens
            )
        except asyncio.TimeoutError:
            pass  # falls through to secondary below
        except ProviderHTTPError as exc:
            if exc.status_code != 429:
                print(f"primary provider raised {exc!r}", file=sys.stderr)
                raise GatewayError(
                    "internal_error", "The upstream provider failed unexpectedly."
                ) from exc
            # 429 falls through to secondary below
        except Exception as exc:
            print(f"primary provider raised {exc!r}", file=sys.stderr)
            raise GatewayError(
                "internal_error", "The upstream provider failed unexpectedly."
            ) from exc

        try:
            text = await asyncio.wait_for(
                self._secondary.complete(req.prompt), timeout=self._timeout_seconds
            )
            return CompletionResponse(
                text=text, provider="secondary", tokens_used=req.estimated_tokens
            )
        except Exception as exc:
            print(f"secondary provider failed: {exc!r}", file=sys.stderr)
            raise GatewayError(
                "upstream_unavailable",
                "Both primary and secondary providers are currently unavailable.",
            ) from exc
