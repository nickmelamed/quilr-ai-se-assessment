from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from gateway import app

client = TestClient(app)

FAKE_DOWNSTREAM_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {"tools": [{"name": "get_weather"}, {"name": "admin_reset_key"}]},
}


def test_tools_list_is_forwarded_and_returned_unmodified():
    with patch(
        "gateway.forward_to_downstream",
        new=AsyncMock(return_value=FAKE_DOWNSTREAM_RESPONSE),
    ) as mock_forward:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": "Bearer viewer-token-xyz"},
        )

    assert response.status_code == 200
    assert response.json() == FAKE_DOWNSTREAM_RESPONSE
    mock_forward.assert_awaited_once()
