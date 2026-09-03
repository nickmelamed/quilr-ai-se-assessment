# Task 1 — MCP Server with Strict Validation & Transport Handling

A stdio-transport MCP server (official `mcp` Python SDK, `mcp` 2.1.1) exposing two tools:

- `get_customer_record(customer_id: str)` — `customer_id` must match `^CUST-\d{5}$`.
- `trigger_refund(customer_id: str, amount: float, reason: str)` — `amount` must be
  positive, `reason` must be at least 10 characters.

Both tools are mocked since there's no real backend. `get_customer_record` deterministically
fabricates a record for any well-formatted ID; `trigger_refund` simulates approval and
returns a generated `refund_id`.

## Setup

```bash
cd task-1-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + pytest/black/ruff
```

## Run

```bash
python server.py
```

The server speaks JSON-RPC over stdio, as it's meant to be launched by an MCP client (e.g.
`mcp.client.stdio.stdio_client`), not driven by hand. Startup and every tool invocation
are logged to stderr; stdout is left untouched until a client sends a JSON-RPC message.

## Test

```bash
pytest
black --check .
ruff check .
```

## Design Decisions

### STDIO Isolation

Every line in `server.py`, `schemas.py`, and `mock_data.py` that needs to report anything
goes through a single `logging.Logger` configured with `logging.basicConfig(stream=sys.stderr, ...)`
at module load. There is no `print()` anywhere in the source. This is checked two ways,
not just asserted:

- `tests/test_stdio_isolation.py` parses each source file's AST and fails the build if any
  `Call` node resolves to a bare `print`. This is a static guarantee that survives future edits.
- `tests/test_server_stdio.py::test_stdout_is_pure_json_rpc` spawns the real server as a
  subprocess, drives a hand-framed JSON-RPC handshake over its actual stdout pipe, and
  asserts every single line `json.loads()` cleanly. If anything
  ever leaked onto stdout, this test fails immediately regardless of whether it also came
  from `print()`, a misconfigured logger, or a third-party dependency.

### Protocol Compliance

The MCP spec's usual convention is that tool execution errors are reported inside a
successful JSON-RPC response as `CallToolResult(isError=True)`, so the calling LLM can see
and react to them, reserving true top-level JSON-RPC error responses for protocol-level
problems (unknown method, malformed request). This assessment explicitly asks for the
opposite: invalid tool input rejected with standard JSON-RPC error codes (`-32602`).

To do that deliberately, each tool handler validates its arguments against a Pydantic
model itself and, on failure, raises `mcp.shared.exceptions.MCPError(INVALID_PARAMS, message)`
(`INVALID_PARAMS` from `mcp.types`, value `-32602`). In `mcp` 2.1.1, raising `MCPError` from
inside an `@mcp.tool()` handler is caught by the SDK's dispatcher and re-emitted as a
genuine top-level JSON-RPC error frame. I confirmed this empirically (see
`tests/test_server_stdio.py`, which asserts the client's `session.call_tool()` call raises
an `MCPError` with `.error.code == INVALID_PARAMS`, not that it returns a result with
`is_error=True`). Validation failures are also logged (to stderr) before the error is
raised, so the rejection is visible in server logs without touching the response itself.

Successful calls return a plain `dict`, which the SDK serializes as JSON in the tool
result's text content. There was no custom result-shaping needed for this scope.

### Validation

Both input schemas live in `schemas.py` as Pydantic `BaseModel`s using field-level
constraints rather than hand-written `if` checks, so the validation rules are declarative
and read the same as the spec:

- `customer_id: str = Field(pattern=r"^CUST-\d{5}$")` (shared by both tools)
- `amount: float = Field(gt=0)` rejects zero and negative values
- `reason: str = Field(min_length=10)`

`tests/test_schemas.py` exercises the edge cases named in the assessment directly against
these models (valid vs. malformed `customer_id` — wrong digit count, lowercase prefix,
missing hyphen, whitespace; zero/negative `amount`; `reason` at the 9-vs-10-character
boundary), independent of the server/transport layer. `tests/test_server_stdio.py` then
confirms the same invalid inputs, when sent as real tool calls, surface as `-32602` errors
end-to-end.

## Known Environment Note

Built and tested against Python 3.14.6. The `mcp` SDK's high-level server class was
renamed from `FastMCP` to `MCPServer` (`mcp.server.mcpserver.MCPServer`) in the 2.x line
used here. Figured this is worth flagging since most public examples/tutorials still reference the old
`FastMCP` name from `mcp` 1.x.
