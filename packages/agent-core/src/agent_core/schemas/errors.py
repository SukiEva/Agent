from pydantic import BaseModel, Field


class AgentError(BaseModel):
    code: str
    message: str
    recoverable: bool = False
    retryable: bool = False
    cancelled: bool = False
    details: dict[str, object] = Field(default_factory=dict)
