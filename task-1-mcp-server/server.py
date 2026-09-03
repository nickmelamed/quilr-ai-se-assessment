"""MCP server exposing customer-service tools over stdio.

stdout is reserved exclusively for JSON-RPC traffic managed by the ``mcp`` SDK.
All logging goes to stderr; this module must never call print().
"""

import logging
import sys
import uuid

from pydantic import ValidationError

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS

from mock_data import generate_customer_record
from schemas import GetCustomerRecordParams, TriggerRefundParams

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("task1-mcp-server")

mcp = MCPServer("task1-customer-service")


def _invalid_params_message(exc: ValidationError) -> str:
    """Flatten a Pydantic ValidationError into a single JSON-RPC error message."""
    parts = [
        f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    ]
    return "; ".join(parts)


@mcp.tool()
def get_customer_record(customer_id: str) -> dict:
    """Look up a customer record by ID (format: CUST-XXXXX)."""
    try:
        params = GetCustomerRecordParams(customer_id=customer_id)
    except ValidationError as exc:
        logger.info("rejected get_customer_record: %s", exc)
        raise MCPError(INVALID_PARAMS, _invalid_params_message(exc)) from exc

    logger.info("get_customer_record: %s", params.customer_id)
    return generate_customer_record(params.customer_id)


@mcp.tool()
def trigger_refund(customer_id: str, amount: float, reason: str) -> dict:
    """Issue a refund for a customer. amount must be positive; reason needs 10+ chars."""
    try:
        params = TriggerRefundParams(customer_id=customer_id, amount=amount, reason=reason)
    except ValidationError as exc:
        logger.info("rejected trigger_refund: %s", exc)
        raise MCPError(INVALID_PARAMS, _invalid_params_message(exc)) from exc

    logger.info("trigger_refund: %s amount=%s", params.customer_id, params.amount)
    return {
        "refund_id": str(uuid.uuid4()),
        "status": "approved",
        "customer_id": params.customer_id,
        "amount": params.amount,
        "reason": params.reason,
    }


if __name__ == "__main__":
    logger.info("starting task1-mcp-server on stdio transport")
    mcp.run()
