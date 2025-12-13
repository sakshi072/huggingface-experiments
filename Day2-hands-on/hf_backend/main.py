from fastapi import FastAPI, HTTPException, Header, Query, Response
from typing import Optional
import uuid
from . import service
from .models import (
    ChatPrompt, InferenceResponse, HistoryResponse, 
    CreateChatRequest, CreateChatResponse, ChatSessionsResponse,  # Fixed typo
    UpdateTitleRequest, GenerateTitleRequest, GenerateTitleResponse
)
from .config import logger
from fastapi.middleware.cors import CORSMiddleware

# --- FastAPI App Setup ---
app = FastAPI(title="Hugg Chat Inference Service", version="2.0")

# --- CORS Configuration ---
origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper function to validate headers ---
def validate_user_id(user_id: Optional[str]) -> str:
    """Validates that user_id header is present."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing 'user-id' header. Authentication required.")
    return user_id


# --- Smart Title Generation Endpoint ---

@app.post("/chat/generate-title", response_model=GenerateTitleResponse)
async def generate_chat_title(
    request: GenerateTitleRequest,
    user_id: Optional[str] = Header(None, alias="user-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """
    Generates a smart, AI-powered title for a chat conversation.
    Uses the LLM to create concise, meaningful titles.
    """
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    logger.info(f"{log_prefix} Generating smart title for user {user_id[:8]}...")

    try:
        title = await service.generate_smart_title(
            user_id=user_id,
            first_message=request.first_message,
            assistant_response=request.assistant_response,
            request_id=x_request_id,
            correlation_id=x_correlation_id
        )

        return GenerateTitleResponse(title=title, fallback=False)
    
    except Exception as e:
        logger.error(f"{log_prefix} Title generation failed, using fallback: {e}")
        # Return fallback title
        fallback_title = service.generate_fallback_title(request.first_message)
        return GenerateTitleResponse(title=fallback_title, fallback=True)

# --- Chat Session Management Endpoints ---

@app.post("/chat/sessions", response_model=CreateChatResponse)
async def create_chat_session(
    request: CreateChatRequest,
    user_id: Optional[str] = Header(None, alias="user-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Creates a new chat session for the authenticated user."""
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    chat_id = await service.create_chat_session(
        user_id=user_id,
        title=request.title,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return CreateChatResponse(chat_id=chat_id, title=request.title)

@app.get("/chat/sessions", response_model=ChatSessionsResponse)  # Fixed typo
async def get_chat_sessions(
    user_id: Optional[str] = Header(None, alias="user-id"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Retrieves all chat sessions for the authenticated user."""
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    sessions = await service.get_user_chat_sessions(
        user_id=user_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
        limit=limit,
        offset=offset
    )

    return ChatSessionsResponse(sessions=sessions)  # Fixed typo

@app.delete("/chat/sessions/{chat_id}")
async def delete_chat_session(
    chat_id: str,
    user_id: Optional[str] = Header(None, alias="user-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Deletes a specific chat session."""
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    logger.info(chat_id, user_id);

    await service.delete_chat_session(
        user_id=user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return Response(status_code=204)

@app.patch("/chat/sessions/{chat_id}/title")  # Fixed typo: was "/chat/session/"
async def update_chat_title(
    chat_id: str,
    request: UpdateTitleRequest,
    user_id: Optional[str] = Header(None, alias="user-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Updates the title of a chat session."""
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    await service.update_chat_title(
        user_id=user_id,
        chat_id=chat_id,
        title=request.title,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return Response(status_code=204)

# --- Chat Inference Endpoints ---

@app.post("/chat/prompt", response_model=InferenceResponse)
async def chat_prompt(
    request: ChatPrompt,
    user_id: Optional[str] = Header(None, alias="user-id"),
    chat_id: Optional[str] = Header(None, alias="chat-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Receives the user prompt and returns the LLM response."""
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing 'chat-id' header.")

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    logger.info(f"{log_prefix} Received prompt from user {user_id[:8]}... chat {chat_id[:8]}...")

    response_text = await service.generate_response(
        user_id=user_id,
        chat_id=chat_id,
        prompt=request.prompt,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return {"response": response_text}

@app.get("/chat/history", response_model=HistoryResponse)
async def get_chat_history(
    chat_id: Optional[str] = Query(None),
    limit: int = Query(20),
    offset: int = Query(0),
    user_id: Optional[str] = Header(None, alias="user-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Retrieves the chat history for a specific chat."""
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    
    if not chat_id:
        logger.warning(f"{log_prefix} GET /chat/history called without chat_id")
        return {"history": []}
    
    history_list = await service.get_history(
        user_id=user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
        limit=limit,
        offset=offset
    )
    
    logger.info(f"{log_prefix} Retrieved {len(history_list)} messages (limit={limit}, offset={offset})")
    return {"history": history_list}

@app.delete("/chat/history/clear")
async def clear_chat_history(
    chat_id: Optional[str] = Query(None),
    user_id: Optional[str] = Header(None, alias="user-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Clears the chat history for a specific chat."""
    user_id = validate_user_id(user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    
    if not chat_id:
        logger.warning(f"{log_prefix} DELETE /chat/history/clear called without chat_id")
        raise HTTPException(status_code=400, detail="Missing 'chat_id' query parameter.")

    await service.clear_history(
        user_id=user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )
    
    logger.info(f"{log_prefix} Cleared history for chat {chat_id[:8]}...")
    return Response(status_code=204)