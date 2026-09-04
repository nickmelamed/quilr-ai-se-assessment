"""Request/response models for the completions router."""

from typing import Literal

from pydantic import BaseModel, Field


class CompletionRequest(BaseModel):
    """An incoming completion request routed through the gateway."""

    tenant_key: str
    prompt: str
    estimated_tokens: int = Field(gt=0)


class CompletionResponse(BaseModel):
    """A successful completion, annotated with which provider served it."""

    text: str
    provider: Literal["primary", "secondary"]
    tokens_used: int
