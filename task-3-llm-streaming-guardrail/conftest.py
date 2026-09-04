"""Ensures the task-3-llm-streaming-guardrail package root is importable from tests/,
and provides a helper for feeding hand-crafted chunk sequences into the redactor.
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


async def chunks(pieces: list[str]) -> AsyncIterator[str]:
    """Yield each string in `pieces` as its own chunk, letting tests pick exact split points."""
    for piece in pieces:
        yield piece
