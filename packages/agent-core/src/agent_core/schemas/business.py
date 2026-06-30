from typing import Literal

from pydantic import BaseModel, Field

from agent_core.schemas.errors import AgentError
from agent_core.schemas.ui import UiDescriptor


class DeliveryDirective(BaseModel):
    mode: Literal["passthrough", "summarize", "compose"] = "summarize"
    final: bool = True
    needs_master_summary: bool = True


class BusinessResultEnvelope(BaseModel):
    status: Literal["completed", "failed", "cancelled", "timeout"]
    agent_id: str
    run_id: str
    task_id: str
    result_type: str
    result: dict[str, object] = Field(default_factory=dict)
    ui: UiDescriptor | None = None
    delivery: DeliveryDirective = Field(default_factory=DeliveryDirective)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    error: AgentError | None = None


class BusinessProgressEvent(BaseModel):
    type: Literal["business.progress"] = "business.progress"
    agent_id: str
    run_id: str
    task_id: str
    message: str
    status: Literal["running", "completed"] = "running"
