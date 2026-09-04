# Quilr AI Solutions Engineer Assessment

Take-home technical assessment for the AI Solutions Engineer role at Quilr, covering four
independent tasks in Python. The original assessment document is included as `source.pdf`.

Each task is self-contained in its own folder, with its own `requirements.txt`, `tests/`,
and `README.md`. See the per-task README for setup instructions, usage, and a "Design
Decisions" section mapping the implementation to that task's evaluation criteria.

- [`task-1-mcp-server/`](task-1-mcp-server/README.md) — MCP server over stdio exposing
  customer-record and refund tools, with Pydantic validation and strict stdout/JSON-RPC
  isolation.
- [`task-2-mcp-gateway-proxy/`](task-2-mcp-gateway-proxy/README.md) — HTTP/JSON-RPC
  reverse proxy in front of a mock downstream MCP server, enforcing role-based
  authorization on tool calls.
- [`task-3-llm-streaming-guardrail/`](task-3-llm-streaming-guardrail/README.md) — Async
  streaming proxy that redacts PII in real time, including patterns split across chunk
  boundaries.
- [`task-4-rate-limit-fallback-router/`](task-4-rate-limit-fallback-router/README.md) —
  Token-aware sliding window rate limiter backed by SQLite, with timeout/429 failover to
  a secondary provider.

See `CLAUDE.md` for the full set of conventions followed across all four tasks.
