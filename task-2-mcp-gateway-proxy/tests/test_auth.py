from auth import extract_role


def test_valid_admin_token():
    assert extract_role("Bearer admin-token-abc") == "admin"


def test_valid_viewer_token():
    assert extract_role("Bearer viewer-token-xyz") == "viewer"


def test_missing_header():
    assert extract_role(None) is None


def test_malformed_header_no_bearer_prefix():
    assert extract_role("admin-token-abc") is None


def test_malformed_header_wrong_scheme():
    assert extract_role("Basic admin-token-abc") is None


def test_unrecognized_token():
    assert extract_role("Bearer not-a-real-token") is None


def test_bearer_scheme_is_case_insensitive():
    assert extract_role("bearer admin-token-abc") == "admin"
