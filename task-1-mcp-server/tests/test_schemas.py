"""Unit tests for the Pydantic input schemas."""

import pytest
from pydantic import ValidationError

from schemas import GetCustomerRecordParams, TriggerRefundParams


class TestCustomerIdValidation:
    @pytest.mark.parametrize("customer_id", ["CUST-00000", "CUST-12345", "CUST-99999"])
    def test_valid_customer_id(self, customer_id):
        params = GetCustomerRecordParams(customer_id=customer_id)
        assert params.customer_id == customer_id

    @pytest.mark.parametrize(
        "customer_id",
        [
            "CUST-1234",  # too few digits
            "CUST-123456",  # too many digits
            "cust-12345",  # lowercase prefix
            "CUST-ABCDE",  # non-numeric suffix
            "CUST12345",  # missing hyphen
            "CUST-12345 ",  # trailing whitespace
            " CUST-12345",  # leading whitespace
            "",  # empty
        ],
    )
    def test_malformed_customer_id_rejected(self, customer_id):
        with pytest.raises(ValidationError):
            GetCustomerRecordParams(customer_id=customer_id)


class TestTriggerRefundParams:
    def test_valid_input_accepted(self):
        params = TriggerRefundParams(
            customer_id="CUST-12345", amount=10.0, reason="defective on arrival"
        )
        assert params.amount == 10.0

    @pytest.mark.parametrize("amount", [0, -0.01, -100])
    def test_non_positive_amount_rejected(self, amount):
        with pytest.raises(ValidationError):
            TriggerRefundParams(
                customer_id="CUST-12345", amount=amount, reason="defective on arrival"
            )

    def test_reason_under_ten_chars_rejected(self):
        with pytest.raises(ValidationError):
            TriggerRefundParams(customer_id="CUST-12345", amount=10.0, reason="short")

    def test_reason_at_boundary_nine_chars_rejected(self):
        with pytest.raises(ValidationError):
            TriggerRefundParams(
                customer_id="CUST-12345", amount=10.0, reason="123456789"
            )

    def test_reason_at_boundary_ten_chars_accepted(self):
        params = TriggerRefundParams(
            customer_id="CUST-12345", amount=10.0, reason="1234567890"
        )
        assert params.reason == "1234567890"

    def test_malformed_customer_id_rejected(self):
        with pytest.raises(ValidationError):
            TriggerRefundParams(
                customer_id="not-valid", amount=10.0, reason="defective on arrival"
            )
