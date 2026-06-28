from typing import Literal

from pydantic import BaseModel, Field

from agent_core.schemas.errors import AgentError


class ClientActionRequest(BaseModel):
    action_id: str
    conversation_id: str
    run_id: str
    agent_id: str
    action_name: str
    contract_version: str = "v1"
    args: dict[str, object] = Field(default_factory=dict)
    timeout_ms: int = 30000


class ClientActionResult(BaseModel):
    action_id: str
    status: Literal["completed", "failed", "rejected", "cancelled", "timeout"]
    result: dict[str, object] = Field(default_factory=dict)
    error: AgentError | None = None
