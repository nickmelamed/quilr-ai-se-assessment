# Task 2 — MCP Security Gateway Proxy

A lightweight HTTP/JSON-RPC reverse proxy (FastAPI + `httpx`) that sits between an agent
client and a downstream MCP server, and enforces method-level authorization on tool calls.

- `downstream_server.py` is a mock downstream MCP server. Exposes `tools/list` (returns
  `get_weather` and `admin_reset_key`) and `tools/call` over a single `POST /rpc` endpoint.
- `gateway.py` is the proxy. Reads the `Authorization: Bearer <token>` header, maps it to a
  role, and exposes a single `POST /mcp` endpoint:
  - `tools/list` is forwarded to the downstream server and returned unmodified.
  - `tools/call` is inspected: if `params.name` starts with `admin_` and the caller's role
    isn't `admin`, the request is rejected with JSON-RPC error `-32001: Unauthorized Tool
    Call` before the downstream server is ever contacted. Everything else is forwarded.
- `auth.py` is an in-memory `Bearer token -> role` map (`admin-token-abc` -> `admin`,
  `viewer-token-xyz` -> `viewer`).
- `schemas.py` is a shared Pydantic JSON-RPC request model and error/result builders, used by
  both the gateway and the mock downstream server.

## Setup

```bash
cd task-2-mcp-gateway-proxy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + pytest/black/ruff
```

## Run (one command, end-to-end)

```bash
./run.sh
```

This starts the mock downstream server on `:8100` and the gateway proxy on `:8000`.
Ctrl+C stops both. Example requests once it's running:

```bash
# Admin token calling an admin_ tool -> allowed
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer admin-token-abc" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key"}}'

# Viewer token calling an admin_ tool -> blocked, -32001, downstream never called
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer viewer-token-xyz" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"admin_reset_key"}}'

# Viewer token calling a non-admin_ tool -> allowed
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer viewer-token-xyz" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_weather","arguments":{"city":"Berkeley"}}}'
```

## Test

```bash
pytest
black --check .
ruff check .
```

## Design Decisions

### Parsing JSON-RPC wire format structures correctly

Both the gateway and the mock downstream server validate every incoming body against the
same `JsonRpcRequest` Pydantic model (`schemas.py`): `jsonrpc: Literal["2.0"]`, `id`,
`method`, and an optional `params` dict. A body that fails validation (wrong/missing
`jsonrpc` version, missing `method`, etc.) never reaches the routing logic. Instead, it's rejected
immediately with a `-32600 Invalid Request` JSON-RPC error, echoing back whatever `id` was
present in the raw body (`tests/test_jsonrpc_schemas.py`). Responses are built through
`make_result`/`make_error` helpers so every reply has the same `{"jsonrpc": "2.0", "id": ..., ...}` envelope shape.

### Proxy middleware construction and HTTP request/response forwarding

The gateway is a single FastAPI route (`POST /mcp`) with one clearly separated forwarding
function, `forward_to_downstream`, that does the actual `httpx.AsyncClient.post()` call to
the downstream server's URL (configurable via `DOWNSTREAM_URL`, defaulting to
`http://localhost:8100/rpc`). Isolating the network call in one function is what makes it
possible for tests to prove the downstream is never invoked on a blocked
request: `tests/test_gateway_authorization.py` patches `gateway.forward_to_downstream` with
an `AsyncMock` and asserts `mock_forward.assert_not_awaited()` on the blocked case, versus
`assert_awaited_once()` on the allowed ones. `tools/list` and any `tools/call` that clears
authorization take the exact same forwarding path and the downstream's JSON response is
returned to the client byte-for-byte unmodified. The gateway never reshapes a passthrough
response.

### Fine-grained, method-level authorization logic and clean error handling

Authorization only applies to `tools/call`, and only when `params.name` starts with
`admin_`. Every other method (`tools/list`, and anything else) is forwarded transparently.
This mirrors the spec exactly rather than inventing a broader auth policy. The role check
itself (`role != "admin"`) short-circuits before `forward_to_downstream` is called, so an
unauthorized request never touches the network. A missing or unrecognized Bearer token resolves to
`role=None` via `auth.extract_role` (not an exception or an HTTP-level rejection), which
naturally fails the `role == "admin"` check for admin tools while leaving `tools/list` and
non-`admin_` tool calls unaffected. This is the narrowest reading of a spec that only gates
`admin_`-prefixed tools. The three cases named in the assessment (admin token + admin tool
allowed, viewer token + admin tool blocked, viewer token + non-admin tool allowed) are each
directly tested in `tests/test_gateway_authorization.py`, plus two extra cases for the
missing-token behavior described above.

## Known Limitations

- Token→role mapping and the tool catalog are both static in-memory data, appropriate for
  a mock rather than a real IdP/downstream integration.
- Only one downstream server is supported (no load balancing/service discovery), which is out of scope for this task.
