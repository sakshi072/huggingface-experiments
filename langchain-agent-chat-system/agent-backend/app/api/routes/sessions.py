"""Chat session management endpoints."""
from fastapi import APIRouter, Depends, Header, Query, Response
from typing import Optional
import uuid
import logging

from app.models import (
    CreateChatRequest, CreateChatResponse, ChatSessionsResponse,
    UpdateTitleRequest
)
from app.services import (
    create_chat_session as create_session,
    get_user_chat_sessions,
    delete_chat_session as delete_session,
    update_chat_title as update_title,
)
from app.api.dependencies import get_current_user_id

router = APIRouter(prefix="/chat/sessions", tags=["sessions"])
logger = logging.getLogger("LangChainBackend")


@router.post("", response_model=CreateChatResponse)
async def create_chat_session(
    request: CreateChatRequest,
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Creates a new chat session for the authenticated user."""
    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    chat_id = await create_session(
        user_id=token_user_id,
        title=request.title,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return CreateChatResponse(chat_id=chat_id, title=request.title)


@router.get("", response_model=ChatSessionsResponse)
async def get_chat_sessions(
    token_user_id: str = Depends(get_current_user_id),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of sessions to return"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
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

    sessions, next_cursor, has_more = await get_user_chat_sessions(
        user_id=token_user_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
        limit=limit,
        cursor=cursor
    )

    return ChatSessionsResponse(
        sessions=sessions,
        next_cursor=next_cursor,
        has_more=has_more
    )


@router.delete("/{chat_id}")
async def delete_chat_session(
    chat_id: str,
    token_user_id: str = Depends(get_current_user_id),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """Deletes a specific chat session."""

    x_request_id = x_request_id or str(uuid.uuid4())
    x_correlation_id = x_correlation_id or str(uuid.uuid4())

    logger.info(f"Deleting chat {chat_id} for user {token_user_id}")

    await delete_session(
        user_id=token_user_id,
        chat_id=chat_id,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return Response(status_code=204)


@router.patch("/{chat_id}/title")
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

    await update_title(
        user_id=token_user_id,
        chat_id=chat_id,
        title=request.title,
        request_id=x_request_id,
        correlation_id=x_correlation_id
    )

    return Response(status_code=204)
