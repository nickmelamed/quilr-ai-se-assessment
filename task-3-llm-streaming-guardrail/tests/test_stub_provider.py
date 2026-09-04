"""Sanity checks on the stub LLM provider's chunking behavior."""

import pytest

from stub_provider import StubLLMProvider


@pytest.mark.asyncio
async def test_stream_reconstructs_to_full_response():
    provider = StubLLMProvider()
    chunks = [c async for c in provider.stream("hello", chunk_size=5)]
    assert len(chunks) > 1
    assert all(len(c) <= 5 for c in chunks)
    assert "hello" in "".join(chunks)


@pytest.mark.asyncio
async def test_stream_is_deterministic_for_same_prompt():
    provider = StubLLMProvider()
    first = "".join([c async for c in provider.stream("same prompt")])
    second = "".join([c async for c in provider.stream("same prompt")])
    assert first == second
