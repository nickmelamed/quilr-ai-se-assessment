"""The redaction cases named in the assessment's evaluation criteria:
PII fully inside one chunk, PII split across a chunk boundary, and a
no-PII stream passing through unmodified. Also covers Luhn validation
and the bounded-buffer / linear-scaling properties the design relies on.
"""

import time

import pytest

from conftest import chunks
from redactor import HOLDBACK_CHARS, StreamingPIIRedactor, redact_stream

VALID_VISA = "4111 1111 1111 1111"  # standard Luhn-valid test card number
INVALID_CC = "1234 5678 9012 3456"  # well-formatted, fails Luhn


async def _collect(pieces: list[str]) -> str:
    return "".join([chunk async for chunk in redact_stream(chunks(pieces))])


@pytest.mark.asyncio
async def test_email_fully_inside_one_chunk():
    result = await _collect(["my email is a@b.com thanks"])
    assert result == "my email is [REDACTED] thanks"


@pytest.mark.asyncio
async def test_ssn_fully_inside_one_chunk():
    result = await _collect(["my ssn is 123-45-6789 ok"])
    assert result == "my ssn is [REDACTED] ok"


@pytest.mark.asyncio
async def test_credit_card_fully_inside_one_chunk():
    result = await _collect([f"card {VALID_VISA} end"])
    assert result == "card [REDACTED] end"


@pytest.mark.asyncio
async def test_credit_card_fails_luhn_not_redacted():
    result = await _collect([f"card {INVALID_CC} end"])
    assert result == f"card {INVALID_CC} end"


@pytest.mark.asyncio
async def test_email_split_across_chunk_boundary():
    result = await _collect(["contact john.doe@exam", "ple.com for details"])
    assert result == "contact [REDACTED] for details"


@pytest.mark.asyncio
async def test_ssn_split_across_chunk_boundary():
    result = await _collect(["ssn is 123-4", "5-6789 ok"])
    assert result == "ssn is [REDACTED] ok"


@pytest.mark.asyncio
async def test_credit_card_split_across_chunk_boundary():
    result = await _collect(["card 4111 1111", " 1111 1111 end"])
    assert result == "card [REDACTED] end"


@pytest.mark.asyncio
async def test_greedy_match_at_buffer_edge_is_not_prematurely_redacted():
    """A domain that looks complete ("example.co") right at the edge of the
    buffered text must not be redacted until the stream proves whether it
    keeps extending (".com") or really does end there."""
    result = await _collect(["email me at test.user@example.co", "m or call later"])
    assert result == "email me at [REDACTED] or call later"


@pytest.mark.asyncio
async def test_no_pii_stream_passes_through_unmodified():
    pieces = ["just plain ", "text with ", "no secrets ", "in it at all"]
    result = await _collect(pieces)
    assert result == "".join(pieces)


@pytest.mark.asyncio
async def test_long_stream_emits_incrementally_not_only_at_the_end():
    # A stream well past HOLDBACK_CHARS should start emitting before the
    # source is exhausted, proving redact_stream doesn't buffer the whole
    # response before producing output.
    pieces = ["plain filler text, no secrets here. "] * 10
    seen = []
    async for piece in redact_stream(chunks(pieces)):
        seen.append(piece)
    assert len(seen) > 1


def test_buffer_stays_bounded():
    redactor = StreamingPIIRedactor()
    text = "plain filler text, no secrets here, just words. " * 200
    max_tail_len = 0
    for i in range(0, len(text), 3):
        redactor.feed(text[i : i + 3])
        max_tail_len = max(max_tail_len, len(redactor._tail))
    assert max_tail_len <= HOLDBACK_CHARS + 3


def test_processing_scales_linearly_not_quadratically():
    def time_feed(n_chunks: int) -> float:
        redactor = StreamingPIIRedactor()
        chunk = "plain filler text with no secrets in it, just words. "
        start = time.perf_counter()
        for _ in range(n_chunks):
            redactor.feed(chunk)
        redactor.flush()
        return time.perf_counter() - start

    small = time_feed(500)
    large = time_feed(2000)  # 4x the chunks
    # Quadratic growth would show ~16x; linear work stays close to 4x.
    assert large < small * 8
