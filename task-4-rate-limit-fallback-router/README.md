# Task 4 — Rate-Limiting & Model Fallback Router

A resilient completion-routing module for an LLM Gateway: a token-aware sliding window
rate limiter backed by on-disk SQLite, and primary/secondary provider failover on a
`429` or a 3000ms timeout, all wrapped in a standardized, sanitized error payload.

- `rate_limiter.py` — `SlidingWindowRateLimiter`, the core of the task: an
  `aiosqlite`-backed sliding window limiter keyed by tenant.
- `providers.py`; the `Provider` protocol plus `FakeProvider`, a configurable stand-in
  model endpoint (`"ok"` / `"rate_limited"` / `"slow"` / `"raise"`). No real API key is
  wired up, the same scoping `task-3-llm-streaming-guardrail` uses for its stub provider.
- `router.py` — `CompletionRouter`, which enforces the rate limit, then races the primary
  provider against a timeout, failing over to the secondary on `429`/timeout, and
  sanitizing every other failure.
- `errors.py` — `GatewayError`, the single type every failure path raises, and the one
  place that defines the JSON payload a caller ever sees.
- `schemas.py` — `CompletionRequest` / `CompletionResponse` pydantic models.
- `gateway.py` — a thin FastAPI wrapper (`POST /v1/completions`) demonstrating the router
  end-to-end; the routing logic itself has no FastAPI dependency.

## Setup

```bash
cd task-4-rate-limit-fallback-router
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + pytest/black/ruff
```

## Run

```bash
uvicorn gateway:app --port 8400
```

```bash
curl -X POST http://localhost:8400/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"tenant_key": "demo", "prompt": "hi", "estimated_tokens": 1000}'
```

## Test

```bash
pytest
black --check .
ruff check .
```

## Design Decisions

### Async concurrency handling and timeout race conditions

`CompletionRouter.complete` races the primary provider's coroutine against the 3000ms
budget with `asyncio.wait_for`; whichever loses (a real timeout, or the provider
returning first) determines the path without blocking on the other. A `429` from the
provider (`ProviderHTTPError(status_code=429)`) and an `asyncio.TimeoutError` are the only
two outcomes that fall through to the secondary; every other exception from the primary
is treated as a hard failure and sanitized immediately, per the assessment's "raised
upstream exception" test case, rather than silently retried on the secondary. The
secondary call is wrapped in the same `wait_for`, so a hung secondary can't leave the
request hanging indefinitely either.
`tests/test_router_failover.py::test_primary_timeout_fails_over_to_secondary` exercises
this with a `FakeProvider("slow", delay_seconds=1.0)` against a shortened
`timeout_seconds=0.05`, so the test doesn't actually wait out a real timeout.

### Accurate rate-limiter state eviction and token tracking logic

The limiter stores one row per accepted request (`tenant_key, ts, tokens`) rather than a
fixed per-minute bucket, so the window slides continuously instead of resetting on a clock
boundary. A tenant that used its full budget at `t=0` can use it again incrementally as
those rows age past 60 seconds, not all at once when a bucket flips. `check_and_record`
evicts every row older than the window before summing and deciding admission
(`DELETE ... WHERE ts <= cutoff`), which is both the eviction logic being scored and what
keeps the table from growing unbounded. The check-sum-insert sequence for a given tenant
runs under a per-tenant `asyncio.Lock`, so two concurrent requests that would each
individually fit but not together can't both be admitted; one of two concurrent 30,000
token requests against the 50,000 budget is rejected, not both accepted
(`tests/test_rate_limiter.py::test_concurrent_requests_for_the_same_tenant_are_serialized`).
A rejected request is never recorded, so retrying the same tenant for the exact
still-available headroom succeeds
(`tests/test_rate_limiter.py::test_request_that_would_exceed_the_limit_is_rejected_and_not_recorded`).
Boundary eviction is tested by inserting a row with a timestamp just past the 60s cutoff
directly (`tests/test_rate_limiter.py::test_expired_rows_are_evicted_from_the_window`)
rather than sleeping a full minute in a test.

### Graceful fallback mechanics and standardized error sanitization

Every failure path — rate limiting, a primary/secondary provider outage, or an unexpected
exception — raises the same `GatewayError`, whose `to_payload()` is the only place a
response body is constructed from an error. Provider exceptions are logged to stderr
(`print(..., file=sys.stderr)`) for operator visibility, but only a fixed, generic message
ever reaches `GatewayError`'s `message` field. The raw exception object itself never
flows into the payload. `tests/test_router_failover.py::test_primary_raised_exception_is_sanitized_and_does_not_fail_over`
and `test_both_providers_down_returns_sanitized_upstream_unavailable` both use a
`FakeProvider("raise")` that raises a `RuntimeError` containing a fake secret
(`"db password=hunter2"`) and assert that string never appears in the resulting payload.
`gateway.py` maps `GatewayError` to its `status_code`/payload via a single
`@app.exception_handler(GatewayError)`, plus a catch-all `Exception` handler so even a bug
elsewhere in the stack can't leak a raw traceback body to the client.

## Known Limitations

- **Client-declared token cost.** `estimated_tokens` is supplied by the caller on
  `CompletionRequest`, not derived from a real tokenizer against the prompt (analogous to
  how a real LLM API caller supplies `max_tokens`). A caller that under-declares its token
  usage can exceed the intended budget; a production system would reconcile against the
  provider's actual reported usage after the fact.
- **Single-process rate limiting.** The per-tenant `asyncio.Lock` that makes
  check-then-insert atomic lives in this process's memory. Multiple gateway instances
  sharing the same SQLite file would each enforce the limit independently rather than
  coordinating, so the effective limit would be `50,000 * instance_count`. Scoped this way
  deliberately for a take-home; a multi-instance deployment would need a
  transaction-level or advisory-lock approach at the database layer instead.
- **Fake providers.** `FakeProvider` stands in for real primary/secondary model endpoints
  (no API key wired up), the same scoping used in `task-3-llm-streaming-guardrail`'s stub
  provider. Swapping in real HTTP calls would mean replacing `Provider.complete`'s body
  with an `httpx` request; the router's timeout/failover/sanitization logic is written
  against the `Provider` protocol and wouldn't need to change.
