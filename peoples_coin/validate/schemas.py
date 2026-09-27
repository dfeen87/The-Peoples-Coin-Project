"""Request schemas used by the goodwill API."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GoodwillActionSchema(BaseModel):
    """Validate the client-controlled portion of a goodwill submission."""

    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    loves_value: int = Field(ge=1, le=100)
    contextual_data: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    signature: str | None = None
    public_key_pem: str | None = None
