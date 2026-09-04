# Task 3 — LLM Gateway Streaming Guardrail (PII Redaction)

An async streaming proxy (FastAPI) that sits in front of an LLM provider and redacts PII
(emails, SSNs, credit card numbers) from the response stream in real time, including PII
patterns split across a chunk boundary. Does so without buffering the full response in memory.

- `stub_provider.py` is a stand-in LLM provider (`StubLLMProvider`): an async generator that
  streams a canned response, embedding the prompt, in fixed-width character chunks. No real
  API key is wired up.
- `redactor.py` is the core of the task: `StreamingPIIRedactor`, a small stateful class that
  redacts PII from a growing text buffer using a bounded trailing "tail," plus `redact_stream`,
  a thin async wrapper that drives it over an incoming chunk stream.
- `gateway.py` is the proxy. A single `POST /v1/generate` route that calls the stub provider
  and streams `redact_stream`'s output back as `text/plain`.
- `schemas.py` is the request model (`GenerateRequest { prompt: str }`).

## Setup

```bash
cd task-3-llm-streaming-guardrail
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + pytest/black/ruff
```

## Run

```bash
uvicorn gateway:app --port 8200
```

```bash
curl -N -X POST http://localhost:8200/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "email me at test.user@example.com or call about ssn 123-45-6789"}'
```

## Test

```bash
pytest
black --check .
ruff check .
```

## Design Decisions

### Efficient asynchronous stream chunking and buffer state management

`StreamingPIIRedactor` holds exactly one piece of state: a `str` tail buffer left over from
the previous chunk. `feed(chunk)` appends the new chunk to that tail, decides how much of the
combined text is safe to emit, and keeps the (small) remainder as the new tail. `redact_stream`
is a thin `async for` wrapper around `feed`/`flush`; the redaction logic itself is synchronous
and does no I/O, so it adds no scheduling overhead beyond the `await` already inherent in
consuming the source stream. `gateway.py` hands `redact_stream`'s output straight to
`StreamingResponse`, so chunks reach the client as soon as the redactor judges them safe,
not after the whole response is generated.

### Performant string/regex pattern matching over partial text streams

All three patterns (email, SSN, credit card) are compiled once into a single alternation
(`PII_RE`), so each buffer refill is one `finditer`/`sub` pass, not three separate scans. Every
quantifier is bounded (`{1,32}`, `{2,12}`, `{1,7}`, etc.). There are no unbounded `+`/`*`
repetitions, so there's no catastrophic-backtracking risk on adversarial input. Credit card
matches are additionally checked against a Luhn checksum (`luhn_valid`) before being redacted;
a well-formatted but Luhn-invalid digit run is left untouched, which meaningfully cuts false
positives against generic long numbers without complicating the streaming logic (Luhn only
runs once a full candidate match exists).

The actual hard part is not the regex, it's deciding when a match is trustworthy. A greedy
regex will happily match "example.co" as a complete email host the instant that's all the
buffer contains. `feed()` handles this by never substituting a match that ends exactly at the edge of the
currently buffered text: it only confirms a match once at least one more character has already
arrived after it (or `flush()` is called because the source has truly ended). An unconfirmed
match's raw text stays in the tail and gets re-scanned, with more context, on the next chunk.
This is exercised directly in
`tests/test_redactor.py::test_greedy_match_at_buffer_edge_is_not_prematurely_redacted`, which
splits `test.user@example.co` / `m or call later` across a chunk boundary. The naive
"redact-then-holdback" version of this code initially got this wrong (redacted `.co` early and
left a stray `m` behind); the fix and the regression test both live in this file's history.

### Memory efficiency and low-latency proxying design

The tail buffer is capped by `HOLDBACK_CHARS` (100, derived from the email pattern's ~95-char
worst case), so memory use is O(1) with respect to stream length. It is never the accumulated
response (`tests/test_redactor.py::test_buffer_stays_bounded` feeds a long no-PII stream and
asserts the tail never exceeds the cap). Each `feed()` call only re-scans that same small
window plus the new chunk, not previously-emitted text, so total work across a stream of
length n is O(n), not O(n²)
(`tests/test_redactor.py::test_processing_scales_linearly_not_quadratically` checks this by
timing 4x the chunks and asserting the runtime doesn't blow up quadratically). Added latency is
one small, constant delay — roughly `HOLDBACK_CHARS` worth of buffering before the first
emit — not a delay that grows with stream length.

## Known Limitations

- `HOLDBACK_CHARS` (100) is a finite cap sized to the longest of the three patterns (email). A
  PII pattern longer than that cap, split exactly at the cap boundary, could partially evade
  redaction. This is an accepted take-home-scope tradeoff rather than a fully general solution.
- SSN matching is dashed-form only (`123-45-6789`); bare 9-digit runs are not treated as SSNs,
  to avoid flagging every ordinary 9-digit number as PII.
- Credit card validation is format + Luhn only. There's no real-world BIN/issuer-range check,
  so some Luhn-valid but non-issued numbers would still be redacted, and this is not a
  substitute for a production-grade PII/PCI scanner.
- The stub provider chunks by fixed character width, not by token or word boundaries. This is
  simpler and still exercises the guardrail's split-boundary handling; it doesn't attempt to
  simulate a specific real provider's actual chunk shapes.
- The proxy streams plain text, not SSE/JSON-framed deltas. Redacting inside a JSON-framed
  delta (where a pattern can also split across a JSON string boundary) was judged out of scope
  for this task.
