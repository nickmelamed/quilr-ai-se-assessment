"""Bearer token -> role extraction for the mock gateway.

Note that a real deployment would validate against an identity provider; for this assessment a
static in-memory map is sufficient.
"""

TOKEN_ROLES: dict[str, str] = {
    "admin-token-abc": "admin",
    "viewer-token-xyz": "viewer",
}


def extract_role(authorization_header: str | None) -> str | None:
    """Parse an `Authorization: Bearer <token>` header and resolve it to a role.

    Returns None if the header is missing, doesn't use the Bearer scheme, or the
    token isn't recognized. Callers treat None as "unauthenticated".
    """
    if not authorization_header:
        return None

    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()
    return TOKEN_ROLES.get(token)
