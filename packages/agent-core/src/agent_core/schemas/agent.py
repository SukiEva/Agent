from pydantic import BaseModel, Field


class AgentDisplay(BaseModel):
    label: str
    description: str
    category: str | None = None
    icon: str | None = None


class AgentCapability(BaseModel):
    name: str
    description: str


class AgentRef(BaseModel):
    agent_id: str
    role: str
    visibility: str = "public"
    base_url: str
    card_url: str | None = None
    display: AgentDisplay | None = None
    capabilities: list[AgentCapability] = Field(default_factory=list)
    healthy: bool = True
    last_error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
