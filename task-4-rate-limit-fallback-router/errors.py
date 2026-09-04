"""Standardized, sanitized gateway error payload.

Every failure path in this module (rate limiting, provider failures, unexpected
exceptions) is surfaced to the caller as a `GatewayError`, never a raw exception.
`GatewayError.to_payload()` is the single place that defines what a client ever sees,
so no upstream stack trace or internal exception message can leak through it.
"""

from typing import Literal

ErrorType = Literal["rate_limited", "upstream_unavailable", "internal_error"]

_STATUS_CODES: dict[ErrorType, int] = {
    "rate_limited": 429,
    "upstream_unavailable": 502,
    "internal_error": 502,
}


class GatewayError(Exception):
    """A sanitized error to return to the caller, with a fixed HTTP status code."""

    def __init__(
        self,
        error_type: ErrorType,
        message: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = _STATUS_CODES[error_type]
        self.retry_after_seconds = retry_after_seconds

    def to_payload(self) -> dict:
        """Build the JSON body returned to the caller."""
        payload: dict = {"error": {"type": self.error_type, "message": self.message}}
        if self.retry_after_seconds is not None:
            payload["error"]["retry_after_seconds"] = self.retry_after_seconds
        return payload
