from pydantic import BaseModel, Field


class UserMessage(BaseModel):
    type: str = "text"
    content: str


class AttachmentRef(BaseModel):
    file_id: str
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None


class RunRequest(BaseModel):
    conversation_id: str
    client_id: str
    message: UserMessage
    selected_agent_id: str | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)


class BusinessTaskRequest(BaseModel):
    conversation_id: str
    run_id: str
    task_id: str
    client_id: str
    user_message: UserMessage
    selected_agent_id: str | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)
    client_context_token: str | None = None
