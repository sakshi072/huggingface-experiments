from fastapi import FastAPI, HTTPException, Header, Query, Response, APIRouter, Depends
from typing import Optional
import uuid
from contextlib import asynccontextmanager

from . import service
from .models import (
    ChatPrompt, InferenceResponse, HistoryResponse, 
    CreateChatRequest, CreateChatResponse, ChatSessionsResponse,  # Fixed typo
    UpdateTitleRequest, GenerateTitleRequest, GenerateTitleResponse,
    HealthCheckResponse, PaginationParams
)
from .config import logger, mongo_manager
from fastapi.middleware.cors import CORSMiddleware
from .auth0 import get_current_user_id

# ===== APPLICATION LIFECYCLE =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management
    
    STARTUP:
    - Initialize MongoDB connection pool
    - Verify connections
    
    SHUTDOWN:
    - Close MongoDB connections gracefully
    - Clean up resources
    """
    logger.info("🚀 Starting HUGG Chat Backend...")
    try:
        mongo_manager.initialize()
        logger.info("✅ Application startup complete")
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise
    
    yield

    logger.info("🔻 Shutting down HUGG Chat Backend...")
    try:
        mongo_manager.close()
        logger.info("✅ Graceful shutdown complete")
    except Exception as e:
        logger.error(f"⚠️ Shutdown error: {e}")

# --- FastAPI App Setup ---
app = FastAPI(
    title="Hugg Chat Inference Service", 
    version="2.0",
    description="Production-ready chat API with cursor pagination and connection pooling",
    lifespan=lifespan)

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

# ===== HEALTH CHECK ENDPOINT (NEW) =====

@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint for monitoring
    
    Use Case:
    - Load balancer health checks
    - Kubernetes liveness/readiness probes
    - Monitoring systems
    """
    db_healthy = mongo_manager.health_check()
    db_stats = mongo_manager.get_connection_stats()

    return HealthCheckResponse(
        status = "healthy" if db_healthy else "unhealthy",
        database = db_stats
    )

# --- Smart Title Generation Endpoint ---

@app.post("/chat/generate-title", response_model=GenerateTitleResponse)
async def generate_chat_title(
    request: GenerateTitleRequest,
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """
    Generates a smart, AI-powered title for a chat conversation.
    Uses the LLM to create concise, meaningful titles.
    """

    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    logger.info(f"{log_prefix} Generating smart title for user {token_user_id[:8]}...")

    try:
        title = await service.generate_smart_title(
            user_id=token_user_id,
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
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Creates a new chat session for the authenticated user."""
    # validated_user_id = validate_user_id_match(user_id, token_user_id)
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    chat_id = await service.create_chat_session(
        user_id=token_user_id,
        title=request.title,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return CreateChatResponse(chat_id=chat_id, title=request.title)

@app.get("/chat/sessions", response_model=ChatSessionsResponse)  # Fixed typo
async def get_chat_sessions(
    token_user_id: str = Depends(get_current_user_id),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of sessions to return"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    # offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """
    Get user's chat sessions with cursor-based pagination
    
    Cursor pagination provides:
    - Consistent results even when data changes
    - Better performance for large datasets
    - No skipped/duplicate results during pagination
    
    Usage:
    - First page: GET /chat/sessions?limit=20
    - Next page: GET /chat/sessions?limit=20&cursor=<next_cursor>
    
    Response includes:
    - sessions: List of chat sessions
    - next_cursor: Token for next page (null if no more results)
    - has_more: Boolean indicating if more results exist
    """
    
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    sessions, next_cursor, has_more = await service.get_user_chat_sessions(
        user_id=token_user_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
        limit=limit,
        cursor=cursor
    )

    return ChatSessionsResponse(
        sessions=sessions,
        next_cursor=next_cursor,
        has_more=has_more)  # Fixed typo

@app.delete("/chat/sessions/{chat_id}")
async def delete_chat_session(
    chat_id: str,
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Deletes a specific chat session."""

    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    logger.info(f"Deleting chat {chat_id} for user {token_user_id}");

    await service.delete_chat_session(
        user_id=token_user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return Response(status_code=204)

@app.patch("/chat/sessions/{chat_id}/title")  # Fixed typo: was "/chat/session/"
async def update_chat_title(
    chat_id: str,
    request: UpdateTitleRequest,
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Updates the title of a chat session."""
    
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    await service.update_chat_title(
        user_id=token_user_id,
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
    token_user_id: str = Depends(get_current_user_id),
    chat_id: Optional[str] = Header(None, alias="chat-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Receives the user prompt and returns the LLM response."""
    
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing 'chat-id' header.")

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    logger.info(f"{log_prefix} Received prompt from user {token_user_id[:8]}... chat {chat_id[:8]}...")

    response_text = await service.generate_response(
        user_id=token_user_id,
        chat_id=chat_id,
        prompt=request.prompt,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return InferenceResponse(response=response_text)

@app.get("/chat/history", response_model=HistoryResponse)
async def get_chat_history(
    chat_id: Optional[str] = Query(None),
    limit: int = Query(20),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Retrieves the chat history for a specific chat."""
    
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    
    if not chat_id:
        logger.warning(f"{log_prefix} GET /chat/history called without chat_id")
        return HistoryResponse(history=[], has_more=False)
    
    
    history_list, next_cursor, has_more = await service.get_history(
        user_id=token_user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
        limit=limit,
        cursor=cursor
    )
    
    logger.info(f"{log_prefix} Retrieved {len(history_list)} messages (limit={limit}, cursor={cursor})")
    return HistoryResponse(
            history=history_list,
            has_more=len(history_list) == limit  # Best guess
        )

@app.delete("/chat/history/clear")
async def clear_chat_history(
    chat_id: Optional[str] = Query(None),
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Clears the chat history for a specific chat."""
    
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    
    if not chat_id:
        logger.warning(f"{log_prefix} DELETE /chat/history/clear called without chat_id")
        raise HTTPException(status_code=400, detail="Missing 'chat_id' query parameter.")

    await service.clear_history(
        user_id=token_user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )
    
    logger.info(f"{log_prefix} Cleared history for chat {chat_id[:8]}...")
    return Response(status_code=204)

@app.get("/admin/connection-stats")
async def get_connection_stats(
    token_user_id: str = Depends(get_current_user_id)
):
    """
    Get MongoDB connection pool statistics
    
    Use Case: Debugging, monitoring
    Note: Should be protected with admin role in production
    """
    return mongo_manager.get_connection_stats()