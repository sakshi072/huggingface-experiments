from fastapi import FastAPI, HTTPException, Header, Query, Response
from typing import Optional
import uuid
from . import service
from .models import ChatPrompt, InferenceResponse, HistoryResponse
from .config import logger

# --- FastAPI App Setup ---
app = FastAPI(title="Hugg Chat Inference Service", version="1.0")

# --- API Endpoints ---

@app.post("/chat/prompt", response_model=InferenceResponse)
async def chat_prompt(
    request: ChatPrompt,
    session_id: Optional[str] = Header(None, description="The unique session ID for history tracking."),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID", description="Unique ID for this specific API request."),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID", description="ID to track related requests across services.")
):
    """
    Receives the user prompt, tracks history by session_id header, and returns ONLY the LLM response.
    """
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"

    if not session_id:
        logger.error(f"{log_prefix} POST /chat/prompt failed: Missing 'session-id' header.")
        raise HTTPException(status_code=400, detail="Missing 'session-id' header.")
    
    logger.info(f"{log_prefix} Received prompt from session {session_id[:8]}...")

    response_text = await service.generate_response(
        session_id=session_id,
        prompt=request.prompt,
        request_id=x_request_id,
        correlation_id = x_correlation_id
    )

    return {"response": response_text}

@app.get("/chat/history", response_model=HistoryResponse)
async def get_chat_history(
    session_id: Optional[str] = Query(None, description="The unique session ID for history tracking."),
    limit: int = Query(20, description="The maximum number of messages to retrieve in one request."),
    offset: int = Query(0, description="The number of messages to skip from the newest message (for pagination)."),
    x_request_id: Optional[str] = Query(None, alias="X-Request-ID", description="Unique ID for this specific API request."),
    x_correlation_id: Optional[str] = Query(None, alias="X-Correlation-ID", description="ID to track related requests across services.")
):
    """
    Retrieves the full chat history for the given session ID via URL query parameter.
    """
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    
    if not session_id:
        logger.warning(f"{log_prefix} GET /chat/history called without session_id in query.")
        return {"history": []}
    
    history_list = await service.get_history(
        session_id=session_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
        limit=limit,
        offset=offset
        )
    logger.info(f"{log_prefix} Retrieved history segment (limit={limit}, offset={offset}). Messages returned: {len(history_list)}")
    return {"history": history_list}

@app.delete("/chat/history/clear")
async def clear_chat_history(
    session_id: Optional[str] = Query(None, description="The unique session ID to clear."),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID", description="Unique ID for this specific API request."),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID", description="ID to track related requests across services.")
):
    """
    Removes the entire chat history for the given session ID from MongoDB using the service layer.
    """
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    
    if not session_id:
        logger.warning(f"{log_prefix} DELETE /chat/history/clear called without session_id in query.")
        raise HTTPException(status_code=400, detail="Missing 'session_id' query parameter.")

    await service.clear_history(
        session_id=session_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id
        )
    logger.info(f"{log_prefix} Clear history requested for session {session_id[:8]}...")
    return Response(status_code=204) # 204 No Content success
