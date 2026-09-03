"""Pydantic input models for the customer-service MCP tools."""

from pydantic import BaseModel, Field

CUSTOMER_ID_PATTERN = r"^CUST-\d{5}$"


class GetCustomerRecordParams(BaseModel):
    """Input schema for the ``get_customer_record`` tool."""

    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)


class TriggerRefundParams(BaseModel):
    """Input schema for the ``trigger_refund`` tool."""

    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    amount: float = Field(gt=0)
    reason: str = Field(min_length=10)
