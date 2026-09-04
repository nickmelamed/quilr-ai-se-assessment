"""HTTP-level check that the full pipeline (provider -> redactor -> response)
streams redacted text back to the client."""

from fastapi.testclient import TestClient

from gateway import app

client = TestClient(app)


def test_generate_redacts_pii_in_streamed_response():
    prompt = "email me at test.user@example.com re: ssn 123-45-6789"

    with client.stream("POST", "/v1/generate", json={"prompt": prompt}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "[REDACTED]" in body
    assert "test.user@example.com" not in body
    assert "123-45-6789" not in body


def test_generate_returns_the_full_plain_text_response():
    # Starlette's in-process TestClient drains an async generator eagerly
    # (there's no real network delay to force separate reads), so it can't
    # assert chunk-by-chunk streaming behavior (covered directly against redact_stream() in tests/test_redactor.py) 
    # This just confirms the endpoint returns the right content end-to-end.
    prompt = (
        "no secrets in this one, just a long plain sentence with lots of extra words"
    )

    with client.stream("POST", "/v1/generate", json={"prompt": prompt}) as response:
        assert response.headers["content-type"].startswith("text/plain")
        body = "".join(response.iter_text())

    assert prompt in body
