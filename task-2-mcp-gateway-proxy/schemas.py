"""JSON-RPC 2.0 request/error models shared by the gateway and the mock downstream server."""

from typing import Any, Literal

from pydantic import BaseModel

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
UNAUTHORIZED_TOOL_CALL = -32001


class JsonRpcRequest(BaseModel):
    """A single JSON-RPC 2.0 request object."""

    jsonrpc: Literal["2.0"]
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


def make_error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    """Build a spec-shaped JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def make_result(request_id: str | int | None, result: Any) -> dict[str, Any]:
    """Build a spec-shaped JSON-RPC 2.0 success response."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
