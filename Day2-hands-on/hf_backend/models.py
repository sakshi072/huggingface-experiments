from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# Internal History Model

class HistoryMessage(BaseModel):
    """Model for messages stored internally in the chat history."""
    session_id: str
    role: str = Field(..., description="Role: 'system', 'user', 'assistant'")
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Method to easily get the format required by the Hugging Face/OpenAI API
    def to_inference_format(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}

# ---- API Models ----

class ChatPrompt(BaseModel):
    """Model for the POST request body."""
    prompt: str

class InferenceResponse(BaseModel):
    """Model for the POST response body."""
    response: str

class HistoryResponse(BaseModel):
    history: List[HistoryMessage]

class CreateChatRequest(BaseModel):
    """Model for creating a new chat session."""
    title: Optional[str] = "New Chat"

class CreateChatResponse(BaseModel):
    """Response when creating a new chat."""
    chat_id: str
    title: str

class ChatSessionMetadata(BaseModel):
    """Metadata about a chat session."""
    chat_id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int

class ChatSessionsResponse(BaseModel):  # Fixed typo: was "ChatSessionsReposne"
    """Response containing list of chat sessions."""
    sessions: List[ChatSessionMetadata]

class UpdateTitleRequest(BaseModel):
    """Request to update chat title."""
    title: str

class GenerateTitleRequest(BaseModel):
    """Request to generate a smart title using AI."""
    first_message: str
    assistant_response: Optional[str] = None

class GenerateTitleResponse(BaseModel):
    """Response containing the generated title."""
    title: str
    fallback: bool = False 