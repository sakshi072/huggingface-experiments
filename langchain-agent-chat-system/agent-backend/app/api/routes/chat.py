"""Chat inference and history endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Header, Query, Response
from typing import Optional
import uuid
import logging

from app.models import (
    ChatPrompt, InferenceResponse, HistoryResponse,
    GenerateTitleRequest, GenerateTitleResponse
)
from app.services import (
    get_history,
    clear_history,
    generate_smart_title,
    generate_fallback_title,
)
from app.api.dependencies import get_current_user_id
from app.infrastructure.observability.request_logger import log_request
from app.services.chat_service import generate_response_stream, generate_response_standard
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("langchain-agent-backend")


@router.post("/generate-title", response_model=GenerateTitleResponse)
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
        title = await generate_smart_title(
            user_id=token_user_id,
            first_message=request.first_message,
            assistant_response=request.assistant_response,
            request_id=x_request_id,
            correlation_id=x_correlation_id
        )

        return GenerateTitleResponse(title=title, fallback=False)

    except Exception as e:
        logger.error(f"{log_prefix} Title generation failed, using fallback: {e}")
        fallback_title = generate_fallback_title(request.first_message)
        return GenerateTitleResponse(title=fallback_title, fallback=True)


@router.post("/stream")
async def chat_streaming(
    request: ChatPrompt,
    token_user_id: str = Depends(get_current_user_id),
    chat_id: Optional[str] = Header(None, alias="chat-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Receives the user prompt and returns the LLM response."""
    log_request(f"ENDPOINT HIT: {request.prompt[:50]}")
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing 'chat-id' header.")

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    logger.info(f"{log_prefix} Received prompt from user {token_user_id[:8]}... chat {chat_id[:8]}...")

    # Streaming agent response
    # It returns an 'AsyncGenerator' object immediately.
    generator_instance = generate_response_stream(
        user_id=token_user_id,
        chat_id=chat_id,
        prompt=request.prompt,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )

    # Return the StreamingResponse with headers to disable proxy buffering
    return StreamingResponse(
        generator_instance,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disables nginx buffering
            "Connection": "keep-alive",
        }
    )

@router.post("", response_model=InferenceResponse)
async def chat_standard(
    request: ChatPrompt,
    token_user_id: str = Depends(get_current_user_id),
    chat_id: Optional[str] = Header(None, alias="chat-id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID"),
):
    """Receives the user prompt and returns the LLM response."""
    log_request(f"ENDPOINT HIT: {request.prompt[:50]}")
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing 'chat-id' header.")

    log_prefix = f"[RID:{x_request_id[:8]}] [CID:{x_correlation_id[:8]}]"
    logger.info(f"{log_prefix} Received prompt from user {token_user_id[:8]}... chat {chat_id[:8]}...")

    # Getting results after the llm call runs completely
    response_text = await generate_response_standard(
        user_id=token_user_id,
        chat_id=chat_id,
        prompt=request.prompt,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return InferenceResponse(response=response_text)

@router.get("/history", response_model=HistoryResponse)
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

    history_list, next_cursor, has_more = await get_history(
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
        next_cursor=next_cursor,
        has_more=has_more
    )


@router.delete("/history/clear")
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

    await clear_history(
        user_id=token_user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    logger.info(f"{log_prefix} Cleared history for chat {chat_id[:8]}...")
    return Response(status_code=204)
