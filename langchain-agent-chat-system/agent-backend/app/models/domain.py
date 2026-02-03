"""Domain models for the application."""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Dict, Optional, Literal
from datetime import datetime


class HistoryMessage(BaseModel):
    """Model for messages stored internally in the chat history."""
    session_id: str = Field(..., min_length=1, max_length=100)
    role: Literal["system", "user", "assistant"] = Field(
        ...,
        description="Role: 'system', 'user', 'assistant'"
    )
    content: str = Field(..., min_length=1, max_length=50000)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    metadata: Optional[Dict] = Field(default_factory=dict)
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()},
        populate_by_name=True
    )

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is not just whitespace"""
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace")
        return v.strip()

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        """Ensure timestamp is not in future"""
        if v > datetime.utcnow():
            raise ValueError("Timestamp cannot be in the future")
        return v

    # Method to easily get the format required by the Hugging Face/OpenAI API
    def to_inference_format(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class ChatSessionMetadata(BaseModel):
    """Metadata about a chat session."""
    chat_id: str
    user_id: str
    title: str = Field(..., max_length=200)
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(ge=0)

    last_message_preview: Optional[str] = Field(default=None, max_length=100)

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )


class CursorInfo(BaseModel):
    """
    Cursor information for pagination

    Why encode cursor?
    - Hide internal implementation details
    - Allow cursor format changes without breaking API
    - Prevent cursor manipulation
    """
    field: str
    value: str
    direction: Literal["forward", "backward"] = "forward"
