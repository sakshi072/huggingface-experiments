from fastapi import FastAPI, HTTPException, Header, Query, Response
from typing import Optional, List

from . import service
from .models import ChatPrompt, InferenceResponse, HistoryResponse
from .config import logger

# --- FastAPI App Setup ---
app = FastAPI(title="Hugg Chat Inference Service", version="1.0")

# --- API Endpoints ---

@app.post("/chat/prompt", response_model=InferenceResponse)
async def chat_prompt(
    request: ChatPrompt,
    session_id: Optional[str] = Header(None, description="The unique session ID for history tracking.")
):
    """
    Receives the user prompt, tracks history by session_id header, and returns ONLY the LLM response.
    """
    if not session_id:
        logger.error("POST /chat/prompt failed: Missing 'session-id' header.")
        raise HTTPException(status_code=400, detail="Missing 'session-id' header.")

    logger.info(f"Received prompt from session {session_id[:8]}...")

    response_text = await service.generate_response(
        session_id=session_id,
        prompt=request.prompt
    )

    return {"response": response_text}

@app.get("/chat/history", response_model=HistoryResponse)
async def get_chat_history(
    session_id: Optional[str] = Query(None, description="The unique session ID for history tracking.")
):
    """
    Retrieves the full chat history for the given session ID via URL query parameter.
    """
    if not session_id:
        logger.warning("GET /chat/history called without session_id in query.")
        return {"history": []}
    
    history_list = await service.get_history(session_id)
    logger.info(f"Retrieved history ({len(history_list)} messages) for session {session_id[:8]}...")
    return {"history": history_list}

@app.delete("/chat/history/clear")
async def clear_chat_history(
    session_id: Optional[str] = Query(None, description="The unique session ID to clear.")
):
    """
    Removes the entire chat history for the given session ID from MongoDB using the service layer.
    """
    if not session_id:
        logger.warning("DELETE /chat/history/clear called without session_id in query.")
        raise HTTPException(status_code=400, detail="Missing 'session_id' query parameter.")

    await service.clear_history(session_id)
    logger.info(f"Clear history requested for session {session_id[:8]}...")
    return Response(status_code=204) # 204 No Content success
