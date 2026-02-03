"""MongoDB document models."""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import datetime
from bson import ObjectId


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


class MessageDocument(BaseModel):
    """
    Individual message document

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
    user_id: str
    role: Literal["system", "user", "assistant"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # For efficient pagination
    sequence: int  # Message sequence number in chat

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )


class ChatMetadataDocument(BaseModel):
    """
    Metadata document structure

    Enhanced with additional tracking fields
    """
    chat_id: str
    user_id: str
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = 0

    # Track last message for preview
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None

    deleted: bool = False
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )
