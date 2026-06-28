from pydantic import BaseModel, Field


class ConversationEvent(BaseModel):
    event_id: str
    conversation_id: str
    run_id: str | None = None
    type: str
    payload: dict[str, object] = Field(default_factory=dict)
