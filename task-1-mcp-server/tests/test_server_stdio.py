"""Integration tests: run the real server as a subprocess over stdio.

Two angles are covered:
  1. Protocol-level behavior via the official `mcp` client SDK (tools/list,
     valid calls, and confirming invalid input raises a genuine JSON-RPC
     -32602 error rather than a CallToolResult(is_error=True)).
  2. Raw stdout purity: a hand-framed JSON-RPC handshake over the subprocess's
     actual stdout pipe, proving every line is valid JSON with no stray
     print()/log text mixed in -- the direct check for STDIO Isolation.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS

SERVER_PATH = Path(__file__).resolve().parent.parent / "server.py"
PROTOCOL_VERSION = "2026-07-28"


async def _run_client_session():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])
    async with stdio_client(params) as (read, write), ClientSession(
        read, write
    ) as session:
        await session.initialize()

        tools = await session.list_tools()
        tool_names = {t.name for t in tools.tools}
        assert tool_names == {"get_customer_record", "trigger_refund"}

        result = await session.call_tool(
            "get_customer_record", {"customer_id": "CUST-12345"}
        )
        assert result.is_error is False
        record = json.loads(result.content[0].text)
        assert record["customer_id"] == "CUST-12345"

        with pytest.raises(MCPError) as exc_info:
            await session.call_tool(
                "get_customer_record", {"customer_id": "not-a-valid-id"}
            )
        assert exc_info.value.error.code == INVALID_PARAMS

        result = await session.call_tool(
            "trigger_refund",
            {
                "customer_id": "CUST-12345",
                "amount": 42.0,
                "reason": "damaged in transit",
            },
        )
        assert result.is_error is False
        refund = json.loads(result.content[0].text)
        assert refund["status"] == "approved"

        with pytest.raises(MCPError) as exc_info:
            await session.call_tool(
                "trigger_refund",
                {
                    "customer_id": "CUST-12345",
                    "amount": -1.0,
                    "reason": "too short",
                },
            )
        assert exc_info.value.error.code == INVALID_PARAMS


def test_tool_calls_via_client():
    asyncio.run(_run_client_session())


def _send(proc: subprocess.Popen, message: dict) -> None:
    proc.stdin.write((json.dumps(message) + "\n").encode())
    proc.stdin.flush()


def test_stdout_is_pure_json_rpc():
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "purity-test", "version": "0.1"},
                },
            },
        )
        init_line = proc.stdout.readline()
        assert init_line, "server produced no output for initialize"
        json.loads(init_line)  # must parse cleanly as JSON

        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_customer_record",
                    "arguments": {"customer_id": "CUST-99999"},
                },
            },
        )
        call_line = proc.stdout.readline()
        parsed = json.loads(call_line)
        assert "result" in parsed

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_customer_record",
                    "arguments": {"customer_id": "invalid"},
                },
            },
        )
        error_line = proc.stdout.readline()
        parsed = json.loads(error_line)
        assert parsed["error"]["code"] == INVALID_PARAMS
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
