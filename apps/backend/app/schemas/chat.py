"""Pydantic schemas"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = None
    cart_session_id: str | None = None
    user_id: str = ""
    image_url: str | None = None
    context: dict | None = None


class SSEToken(BaseModel):
    type: str  # text / tool_start / tool_end / card / error
    content: str
    metadata: dict | None = None
