from datetime import datetime
from typing import List
from pydantic import AliasChoices, BaseModel, Field
from app.models.chat import MessageRole


class ChatMessageIn(BaseModel):
    content: str = Field(validation_alias=AliasChoices("content", "message"))


class ChatMessageOut(BaseModel):
    id: int
    user_id: int
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatReply(BaseModel):
    reply: str


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageOut]
    total: int
    page: int
    page_size: int
