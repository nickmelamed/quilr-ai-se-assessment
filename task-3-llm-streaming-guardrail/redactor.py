"""Streaming PII redaction.

Detects emails, SSNs, and credit card numbers in an LLM's streamed text
output and replaces them with `[REDACTED]`, including patterns split across
a chunk boundary, without ever buffering the full response.

Each incoming chunk is appended to a small trailing "tail" buffer left over
from the previous chunk. A match is only substituted once it is *confirmed*
final: it must end before the last `HOLDBACK_CHARS` characters of the
buffer, and at least one more character must already exist in the buffer
after it. A match ending exactly at the edge of the currently buffered text
is not trusted, because a greedy quantifier only stops there for lack of
more input, not because the pattern is actually finished (a domain of
"example.co" is a syntactically complete email host right up until the "m"
of "example.com" arrives in the next chunk). Anything not yet confirmed is
kept as raw, unsubstituted text in the tail so it can be re-scanned, with
more context, on the next chunk. The tail stays a small constant, never the
accumulated response, so redaction never re-processes text it has already
emitted.
"""

import re
from collections.abc import AsyncIterator

EMAIL_RE = r"[A-Za-z0-9._%+-]{1,32}@(?:[A-Za-z0-9-]{1,24}\.){1,2}[A-Za-z]{2,12}"
SSN_RE = r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"
CC_RE = r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,7}(?!\d)"

PII_RE = re.compile(f"(?P<email>{EMAIL_RE})|(?P<ssn>{SSN_RE})|(?P<cc>{CC_RE})")

# Longest pattern above (email) matches at most ~95 chars; 100 gives headroom
# so an in-progress match is never longer than the held-back tail.
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
        working = self._tail + chunk
        safe_len = max(0, len(working) - self._holdback_chars)
        for match in PII_RE.finditer(working):
            if match.end() == len(working):
                # Touches the edge of buffered text: might still extend.
                safe_len = min(safe_len, match.start())
            elif match.start() < safe_len < match.end():
                # Confirmed match, but the generic margin would split it.
                safe_len = match.start()

        safe_prefix, self._tail = working[:safe_len], working[safe_len:]
        return PII_RE.sub(_replace, safe_prefix) if safe_prefix else ""

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
