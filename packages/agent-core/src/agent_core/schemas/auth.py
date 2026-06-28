from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    user_id: str = "anonymous"
    tenant_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class InternalAuthContext(BaseModel):
    service_id: str = "anonymous-service"
    agent_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
