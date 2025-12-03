from pydantic import BaseModel, Field
from typing import List, Dict, Any
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

