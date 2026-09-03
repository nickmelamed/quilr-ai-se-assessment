"""Mock downstream MCP server.

Speaks JSON-RPC 2.0 over a single HTTP endpoint. Exists purely so the gateway proxy
has something real to forward requests to; run standalone with:

    uvicorn downstream_server:app --port 8100
"""

import logging
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from schemas import (
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcRequest,
    make_error,
    make_result,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("downstream_server")

app = FastAPI(title="Mock Downstream MCP Server")

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_weather",
        "description": "Look up the current weather for a city.",
    },
    {
        "name": "admin_reset_key",
        "description": "Rotate the API key for the current tenant. Admin only.",
    },
]


def _handle_tools_list() -> dict[str, Any]:
    return {"tools": TOOLS}


def _handle_tools_call(params: dict[str, Any] | None) -> dict[str, Any]:
    name = (params or {}).get("name")
    if name == "get_weather":
        city = (params or {}).get("arguments", {}).get("city", "an unknown city")
        return {"content": [{"type": "text", "text": f"It's sunny in {city}."}]}
    if name == "admin_reset_key":
        return {"content": [{"type": "text", "text": "new-api-key-c0ffee"}]}
    return {"content": [{"type": "text", "text": f"Executed {name}"}]}


@app.post("/rpc")
async def rpc(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        rpc_request = JsonRpcRequest.model_validate(body)
    except ValidationError:
        return JSONResponse(
            make_error(body.get("id"), INVALID_REQUEST, "Invalid Request")
        )

    logger.info(
        "downstream received method=%s id=%s", rpc_request.method, rpc_request.id
    )

    if rpc_request.method == "tools/list":
        return JSONResponse(make_result(rpc_request.id, _handle_tools_list()))
    if rpc_request.method == "tools/call":
        return JSONResponse(
            make_result(rpc_request.id, _handle_tools_call(rpc_request.params))
        )

    return JSONResponse(
        make_error(
            rpc_request.id, METHOD_NOT_FOUND, f"Method not found: {rpc_request.method}"
        )
    )
