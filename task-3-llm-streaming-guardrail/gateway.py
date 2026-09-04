"""LLM Gateway streaming endpoint.

Routes a text-generation request to the stub LLM provider and streams the
response back to the client as plain text, redacting PII from the stream in
real time via `redactor.redact_stream`.

Run standalone with:

    uvicorn gateway:app --port 8200
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from redactor import redact_stream
from schemas import GenerateRequest
from stub_provider import StubLLMProvider

app = FastAPI(title="LLM Gateway Streaming Guardrail")


@app.post("/v1/generate")
async def generate(req: GenerateRequest) -> StreamingResponse:
    provider_stream = StubLLMProvider().stream(req.prompt)
    return StreamingResponse(redact_stream(provider_stream), media_type="text/plain")
