"""Stub LLM provider.

Simulates a text-generation provider that streams its response back in fixed
size chunks, standing in for a real LLM API so the gateway can be exercised
end-to-end without any provider credentials wired up.
"""

import asyncio
from collections.abc import AsyncIterator


class StubLLMProvider:
    """Yields a canned completion in fixed-width chunks, as if streamed from an LLM."""

    async def stream(
        self, prompt: str, *, chunk_size: int = 16, delay: float = 0.0
    ) -> AsyncIterator[str]:
        """Stream a canned response embedding `prompt`, sliced into `chunk_size`-char chunks.

        `delay` (seconds) is applied between chunks; it defaults to 0 so tests
        run instantly, but a demo run can pass a small delay to make the
        streaming visibly incremental over curl.
        """
        response = (
            f"Sure, here is what I found for '{prompt}'. "
            "Let me know if you need anything else."
        )
        for start in range(0, len(response), chunk_size):
            if delay:
                await asyncio.sleep(delay)
            yield response[start : start + chunk_size]
