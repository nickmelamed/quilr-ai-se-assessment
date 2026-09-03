"""Deterministic fake customer data for the get_customer_record mock backend."""

import hashlib

_STATUSES = ["active", "past_due", "suspended", "closed"]
_PLANS = ["basic", "pro", "enterprise"]


def generate_customer_record(customer_id: str) -> dict:
    """Deterministically fabricate a customer record for a well-formatted ``customer_id``.

    No real datastore backs this tool; the same ``customer_id`` always yields the
    same record, seeded from a hash of the ID so results are reproducible in tests.
    """
    digest = hashlib.sha256(customer_id.encode()).digest()
    return {
        "customer_id": customer_id,
        "name": f"Customer {customer_id[-5:]}",
        "email": f"{customer_id.lower()}@example.com",
        "status": _STATUSES[digest[0] % len(_STATUSES)],
        "plan": _PLANS[digest[1] % len(_PLANS)],
        "lifetime_value_usd": round(digest[2] * 37.5, 2),
    }
