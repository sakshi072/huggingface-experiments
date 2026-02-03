"""API request and response models."""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime

from .domain import HistoryMessage, ChatSessionMetadata


class ChatPrompt(BaseModel):
    """Model for the POST request body."""
    prompt: str = Field(..., min_length=1, max_length=10000)

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()


class InferenceResponse(BaseModel):
    """Model for the POST response body."""
    response: str


class HistoryResponse(BaseModel):
    history: List[HistoryMessage]
    next_cursor: Optional[str] = None
    has_more: bool = None
    total_count: Optional[int] = None


class CreateChatRequest(BaseModel):
    """Model for creating a new chat session."""
    title: Optional[str] = Field(default="New Chat", max_length=200)

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: Optional[str]) -> str:
        if v:
            v = v.strip()
            if not v:
                return "New Chat"
        return v or "New Chat"


class CreateChatResponse(BaseModel):
    """Response when creating a new chat."""
    chat_id: str
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatSessionsResponse(BaseModel):
    """Response containing list of chat sessions."""
    sessions: List[ChatSessionMetadata]
    next_cursor: Optional[str] = None
    has_more: bool = False
    total_count: Optional[int] = None


class UpdateTitleRequest(BaseModel):
    """Request to update chat title."""
    title: str = Field(..., min_length=1, max_length=200)

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty")
        return v


class GenerateTitleRequest(BaseModel):
    """Request to generate a smart title using AI."""
    first_message: str = Field(..., min_length=1, max_length=1000)
    assistant_response: Optional[str] = Field(default=None, max_length=5000)

    @field_validator('first_message')
    @classmethod
    def validate_first_message(cls, v: str) -> str:
        return v.strip()


class GenerateTitleResponse(BaseModel):
    """Response containing the generated title."""
    title: str
    fallback: bool = False


class PaginationParams(BaseModel):
    """Unified pagination parameters"""
    cursor: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator('limit')
    @classmethod
    def validate_limit(cls, v: int) -> int:
        """Ensure reasonable limit for performance"""
        if v > 100:
            return 100
        return v


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: Literal["healthy", "unhealthy"]
    database: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )
