"""LLM Gateway completions endpoint: rate limiting + primary/secondary failover.

Run standalone with:

    uvicorn gateway:app --port 8400

No real LLM API key is wired up; `primary`/`secondary` are `FakeProvider` instances
(see `providers.py`), the same "no credentials wired up" scoping used in
task-3-llm-streaming-guardrail.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from errors import GatewayError
from providers import FakeProvider
from rate_limiter import SlidingWindowRateLimiter
from router import CompletionRouter
from schemas import CompletionRequest, CompletionResponse

DB_PATH = "rate_limiter.db"

rate_limiter = SlidingWindowRateLimiter(DB_PATH)
completion_router = CompletionRouter(
    primary=FakeProvider("ok", response="Response from the primary model."),
    secondary=FakeProvider("ok", response="Response from the secondary model."),
    rate_limiter=rate_limiter,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await rate_limiter.init()
    yield


app = FastAPI(title="Rate-Limiting & Model Fallback Router", lifespan=lifespan)


@app.exception_handler(GatewayError)
async def gateway_error_handler(_: Request, exc: GatewayError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    fallback = GatewayError("internal_error", "An unexpected error occurred.")
    return JSONResponse(status_code=fallback.status_code, content=fallback.to_payload())


@app.post("/v1/completions")
async def completions(req: CompletionRequest) -> CompletionResponse:
    return await completion_router.complete(req)
