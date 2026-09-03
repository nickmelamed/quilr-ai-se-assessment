import pytest
from pydantic import ValidationError

from schemas import JsonRpcRequest, make_error, make_result


def test_valid_request_parses():
    req = JsonRpcRequest.model_validate(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert req.method == "tools/list"
    assert req.params is None


def test_missing_method_fails_validation():
    with pytest.raises(ValidationError):
        JsonRpcRequest.model_validate({"jsonrpc": "2.0", "id": 1})


def test_wrong_jsonrpc_version_fails_validation():
    with pytest.raises(ValidationError):
        JsonRpcRequest.model_validate(
            {"jsonrpc": "1.0", "id": 1, "method": "tools/list"}
        )


def test_make_error_shape():
    err = make_error(1, -32001, "Unauthorized Tool Call")
    assert err == {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32001, "message": "Unauthorized Tool Call"},
    }


def test_make_result_shape():
    result = make_result(1, {"tools": []})
    assert result == {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
