from datetime import datetime
from typing import List, Optional
from pydantic import AliasChoices, BaseModel, Field, field_validator
from app.models.chat import MessageRole


class ChatMessageIn(BaseModel):
    content: str = Field(validation_alias=AliasChoices("content", "message"))
    client_message_id: Optional[str] = None


class ChatMessageEdit(BaseModel):
    content: str
    client_message_id: Optional[str] = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content cannot be empty")
        return value


class ChatMessageOut(BaseModel):
    id: int
    user_id: int
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatReply(BaseModel):
    reply: str
    user_message_id: Optional[int] = None
    assistant_message_id: Optional[int] = None


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageOut]
    total: int
    page: int
    page_size: int


class ChatClearResponse(BaseModel):
    cleared_messages: int
    cancelled_pending_intents: int
    cancelled_advisory_sessions: int
