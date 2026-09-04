"""Streaming PII redaction.

Detects emails, SSNs, and credit card numbers in an LLM's streamed text
output and replaces them with `[REDACTED]`, including patterns split across
a chunk boundary, without ever buffering the full response.

Each incoming chunk is appended to a small trailing "tail" buffer
left over from the previous chunk, the combined text is redacted in one
regex pass, and everything except the last `HOLDBACK_CHARS` characters is
emitted immediately. The held-back tail is short enough that it can only
ever contain an in-progress (not yet complete) match, so a pattern that
straddles a chunk boundary always ends up whole in some future scan of
tail + next chunk, and only its (now redacted) window can be re-scanned;
the buffer is a small constant, never the accumulated response.
"""

import re
from collections.abc import AsyncIterator

EMAIL_RE = r"[A-Za-z0-9._%+-]{1,32}@(?:[A-Za-z0-9-]{1,24}\.){1,2}[A-Za-z]{2,12}"
SSN_RE = r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"
CC_RE = r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,7}(?!\d)"

PII_RE = re.compile(f"(?P<email>{EMAIL_RE})|(?P<ssn>{SSN_RE})|(?P<cc>{CC_RE})")

# Longest pattern above (email) matches at most ~95 chars; 100 gives headroom
# so a partial match is never longer than the held-back tail.
HOLDBACK_CHARS = 100


def luhn_valid(digits: str) -> bool:
    """Return whether `digits` (a string of ASCII digits) passes the Luhn checksum."""
    total = 0
    for i, char in enumerate(reversed(digits)):
        value = int(char)
        if i % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _replace(match: re.Match[str]) -> str:
    if match.lastgroup == "cc":
        digits = re.sub(r"[ -]", "", match.group())
        if not luhn_valid(digits):
            return match.group()
    return "[REDACTED]"


class StreamingPIIRedactor:
    """Redacts PII from a stream of text chunks using a bounded trailing buffer."""

    def __init__(self, holdback_chars: int = HOLDBACK_CHARS) -> None:
        self._holdback_chars = holdback_chars
        self._tail = ""

    def feed(self, chunk: str) -> str:
        """Feed the next chunk in and return the portion now safe to emit."""
        redacted = PII_RE.sub(_replace, self._tail + chunk)
        if len(redacted) <= self._holdback_chars:
            self._tail = redacted
            return ""
        split_at = len(redacted) - self._holdback_chars
        emit, self._tail = redacted[:split_at], redacted[split_at:]
        return emit

    def flush(self) -> str:
        """Redact and return whatever remains once the source stream has ended."""
        redacted = PII_RE.sub(_replace, self._tail)
        self._tail = ""
        return redacted


async def redact_stream(
    source: AsyncIterator[str], *, holdback_chars: int = HOLDBACK_CHARS
) -> AsyncIterator[str]:
    """Wrap a raw text chunk stream, yielding redacted chunks with the same total content."""
    redactor = StreamingPIIRedactor(holdback_chars)
    async for chunk in source:
        emitted = redactor.feed(chunk)
        if emitted:
            yield emitted
    tail = redactor.flush()
    if tail:
        yield tail
