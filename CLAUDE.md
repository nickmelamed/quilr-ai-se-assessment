# CLAUDE.md — Quilr AI Solutions Engineer Assessment

## Context
This repo is a take-home technical assessment for an AI Solutions Engineer role at Quilr. It contains 4 independent tasks covering MCP servers,
MCP gateway proxies, LLM gateway streaming guardrails, and rate-limiting/fallback routing.
Each task will be reviewed by a human engineer, followed by a 30-minute call to discuss
the implementation; therefore, code should be correct, idiomatic, and easy to explain out loud, not just passing. 

**Note**: The original assessment document is located in the repo root as `source.pdf`.

## Global Conventions

- **Language: Python, consistently, across all four tasks.** Don't mix in TypeScript
  even though the MCP SDK supports it; a reviewer skimming four folders should see one
  coherent stack.
- **Per-task isolation:** each `task-N-*/` folder is self-contained with its own
  `requirements.txt`, its own `tests/`, and its own `README.md`. Don't import across task
  folders or share a virtualenv/requirements file at the root.
- **Type hints + docstrings** on all public functions. Prefer `pydantic` models for any
  structured input/output validation.
- **Testing:** `pytest` in every `tests/` folder. Prioritize the edge cases named in each
  task's "Evaluation Criteria" over incidental extra features. A few sharp tests beat a
  large suite of shallow ones.
- **Formatting:** `black` + `ruff`, default settings, no custom config unless a task needs it.
- **Dependencies:** keep minimal. Standard library and one or two well-known packages per
  task (e.g. `mcp`, `pydantic`, `fastapi`/`starlette`, `httpx`, `aiosqlite`).
- **Per-task README:** after implementing a task, update its `README.md` with a short
  "Design Decisions" section that explicitly maps to that task's evaluation criteria
  bullets (from the assessment PDF at the repo root).
  This is what I'll be discussing on the follow-up call, so keep it accurate to what was
  actually built, not aspirational.
- **Commits:** one logical commit per meaningful step within a task (schema/validation,
  core logic, tests, README) rather than one giant commit per folder. Conventional
  commit style (`feat(task-1): add strict schema validation`) is fine. I will have to push the commits manually, so when you create them, notify me and I will tell you to proceed accordingly. 

## Task 1 — `task-1-mcp-server/`
MCP server (official `mcp` Python SDK) over **stdio transport**, exposing two tools:

- `get_customer_record(customer_id: str)` — must match `^CUST-\d{5}$`.
- `trigger_refund(customer_id: str, amount: float, reason: str)` — `amount` must be a
  positive float; `reason` must be at least 10 characters.

Requirements:
- Validate inputs with **Pydantic** models; reject invalid input with standard MCP
  JSON-RPC error codes (e.g. `-32602 Invalid params`), not generic exceptions.
- **stdout must carry only JSON-RPC messages.** All logging/debug output goes to
  **stderr**. Grep the final implementation for stray `print()`/`console.log` before
  calling this done — that's the #1 thing being scored here.

Tests should cover: valid vs. malformed `customer_id`, zero/negative `amount`,
`reason` under 10 chars, and confirming no non-JSON-RPC output ever hits stdout.

## Task 2 — `task-2-mcp-gateway-proxy/`
HTTP/JSON-RPC reverse proxy sitting between an agent client and a **mock downstream MCP
server** (build the mock too — the repo needs to run end-to-end with one command).

Requirements:
- Read `Authorization: Bearer <token>`; map it to a role (`admin` / `viewer`). A simple
  in-memory token→role dict is fine for the mock.
- `tools/list` → forward transparently to downstream, return its response unmodified.
- `tools/call` → inspect `params.name`. If it starts with `admin_`, require role
  `admin`. If unauthorized, **intercept before calling downstream** and return JSON-RPC
  error `-32001: Unauthorized Tool Call`.

Tests should cover: admin token calling an `admin_*` tool (allowed), viewer token
calling an `admin_*` tool (blocked with `-32001`, downstream never invoked — assert this
with a mock/spy), and a non-`admin_` tool call from a viewer (allowed).

## Task 3 — `task-3-llm-streaming-guardrail/`
Async streaming proxy in front of an LLM provider (a stub/mock provider that yields
chunks is fine if no real API key is wired up) that redacts PII from the stream in
real time before it reaches the client.

Requirements:
- Detect and redact emails, SSNs, and credit card numbers → replace with `[REDACTED]`.
- **Must work even when a PII pattern is split across two chunk boundaries** — this is
  the actual hard part of the task, not simple full-text regex. Use a small trailing
  buffer/overlap window, not full-response accumulation.
- Must not buffer the entire response in memory, and must not meaningfully hurt
  time-to-first-token or overall stream latency.

Tests should cover: PII fully inside one chunk, PII split across a chunk boundary,
and a stream with no PII passing through unmodified with minimal added latency.

## Task 4 — `task-4-rate-limit-fallback-router/`
Resilient routing module for an LLM Gateway.

Requirements:
- **Token-aware sliding window rate limiter**: max 50,000 tokens/minute per tenant API
  key, backed by **on-disk SQLite** (`aiosqlite`), not in-memory only.
- If the primary model endpoint returns `429` or doesn't respond within **3000ms**,
  automatically fail over to a secondary backup provider.
- Error responses must be a standardized gateway error payload — never leak raw
  upstream stack traces or internal exception details to the caller.

Tests should cover: rate limiter eviction/window logic near the boundary, primary
`429` triggering failover, primary timeout (use a fake slow provider) triggering
failover, and a raised upstream exception producing a sanitized error payload.

## What NOT to do
- Don't fabricate requirements not in the spec. Always ask instead of guessing.
- Don't silently swap the agreed Python stack for a "cleaner" TS implementation.
- Don't over-engineer (no message queues, no Redis, no k8s manifests). Remember these are
  scoped take-home tasks, not production infra.
- Don't write README "Design Decisions" sections that describe things not actually
  in the code.
- If at any point you are unsure where to proceed, ask me. 