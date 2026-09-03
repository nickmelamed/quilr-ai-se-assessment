"""The three authorization cases named in the assessment's evaluation criteria."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from gateway import app

client = TestClient(app)

FAKE_DOWNSTREAM_RESPONSE = {"jsonrpc": "2.0", "id": 1, "result": {"content": []}}


def _call_tool(token: str, tool_name: str):
    with patch(
        "gateway.forward_to_downstream",
        new=AsyncMock(return_value=FAKE_DOWNSTREAM_RESPONSE),
    ) as mock_forward:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name},
            },
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
    return response, mock_forward


def test_admin_token_calling_admin_tool_is_allowed():
    response, mock_forward = _call_tool("admin-token-abc", "admin_reset_key")

    assert response.status_code == 200
    assert response.json() == FAKE_DOWNSTREAM_RESPONSE
    mock_forward.assert_awaited_once()


def test_viewer_token_calling_admin_tool_is_blocked_without_reaching_downstream():
    response, mock_forward = _call_tool("viewer-token-xyz", "admin_reset_key")

    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32001, "message": "Unauthorized Tool Call"},
    }
    mock_forward.assert_not_awaited()


def test_viewer_token_calling_non_admin_tool_is_allowed():
    response, mock_forward = _call_tool("viewer-token-xyz", "get_weather")

    assert response.status_code == 200
    assert response.json() == FAKE_DOWNSTREAM_RESPONSE
    mock_forward.assert_awaited_once()


def test_missing_token_calling_admin_tool_is_blocked():
    response, mock_forward = _call_tool("", "admin_reset_key")

    assert response.json()["error"]["code"] == -32001
    mock_forward.assert_not_awaited()


def test_missing_token_calling_non_admin_tool_is_allowed():
    response, mock_forward = _call_tool("", "get_weather")

    assert response.json() == FAKE_DOWNSTREAM_RESPONSE
    mock_forward.assert_awaited_once()
