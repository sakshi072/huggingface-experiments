from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime
from bson import ObjectId

# Custom types for MongoDB ObjectID
class PyObjectId(str):
    """Custom type for MongoDB ObjectId serialization"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, _):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return str(v)

# Internal History Model

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
        json_encoders={datetime: lambda v:v.isoformat()},
        populate_by_name=True
    )

    @field_validator('content')
    @classmethod
    def validate_content(cls, v:str) -> str:
        """Ensure content is not just whitespace"""
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace")
        return v.strip()
    
    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v:datetime) -> datetime:
        """Ensure timestamp is not in future"""
        if v > datetime.utcnow():
            raise ValueError("Timestamp cannot be in the future")
        return v
    
    # Method to easily get the format required by the Hugging Face/OpenAI API
    def to_inference_format(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}

# ---- API Models ----

class ChatPrompt(BaseModel):
    """Model for the POST request body."""
    prompt: str = Field(..., min_length=1, max_length=10000)

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v:str) -> str:
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
    def validate_title(cls, v:Optional[str]) -> str:
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

# ===== PAGINATION MODELS (NEW) =====

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

# ===== HEALTH CHECK MODEL (NEW) =====

class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: Literal["healthy", "unhealthy"]
    database: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )


# ===== DATABASE DOCUMENT MODELS (NEW) =====

class MessageDocument(BaseModel):
    """
    Individual message document (NEW)
    
    Why separate collection?
    - Avoids 16MB document size limit
    - Better for pagination (can query messages directly)
    - Efficient updates (update one message, not entire array)
    - Better indexing (can index message fields)
    
    Trade-off:
    - More documents = more storage overhead
    - Need to manage references
    - Slightly more complex queries
    
    Decision: Worth it for scalability
    """
    message_id: str = Field(default_factory=lambda: str(ObjectId()))
    chat_id: str
    user_id:str
    role: Literal["system", "user", "assistant"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # For efficient pagination
    sequence: int # Message sequence number in chat

    model_config = ConfigDict(
        json_encoders={datetime: lambda v:v.isoformat()}
    )

class ChatMetadataDocument(BaseModel):
    """
    Metadata document structure
    
    Enhanced with additional tracking fields
    """
    chat_id: str
    user_id: str
    title: str
    create_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = 0

    # NEW: Track last message for preview
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None

    deleted: bool = False
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(
        json_encoders={datetime: lambda v:v.isoformat()}
    )

