"""Request schema for the LLM Gateway streaming endpoint."""

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    """Body of a POST to /v1/generate."""

    prompt: str
