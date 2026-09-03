"""MCP Security Gateway Proxy.

Sits between an agent client and the downstream mock MCP server. Forwards
`tools/list` transparently and enforces admin-only authorization on any
`tools/call` whose tool name starts with `admin_`, intercepting unauthorized
calls before the downstream server is ever contacted.

Run standalone with:

    uvicorn gateway:app --port 8000
"""

import logging
import os
import sys
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from auth import extract_role
from schemas import (
    INVALID_REQUEST,
    UNAUTHORIZED_TOOL_CALL,
    JsonRpcRequest,
    make_error,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("gateway")

DOWNSTREAM_URL = os.environ.get("DOWNSTREAM_URL", "http://localhost:8100/rpc")

app = FastAPI(title="MCP Security Gateway Proxy")


async def forward_to_downstream(body: dict[str, Any]) -> dict[str, Any]:
    """Forward a JSON-RPC payload to the downstream MCP server and return its response."""
    async with httpx.AsyncClient() as client:
        response = await client.post(DOWNSTREAM_URL, json=body)
        return response.json()


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    body = await request.json()

    try:
        rpc_request = JsonRpcRequest.model_validate(body)
    except ValidationError:
        return JSONResponse(
            make_error(body.get("id"), INVALID_REQUEST, "Invalid Request")
        )

    role = extract_role(request.headers.get("authorization"))

    if rpc_request.method == "tools/call":
        tool_name = (rpc_request.params or {}).get("name", "")
        if tool_name.startswith("admin_") and role != "admin":
            logger.warning(
                "blocked unauthorized tool call: tool=%s role=%s", tool_name, role
            )
            return JSONResponse(
                make_error(
                    rpc_request.id, UNAUTHORIZED_TOOL_CALL, "Unauthorized Tool Call"
                )
            )

    downstream_response = await forward_to_downstream(body)
    return JSONResponse(downstream_response)
