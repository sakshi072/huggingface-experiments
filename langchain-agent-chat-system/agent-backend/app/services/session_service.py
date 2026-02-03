"""Session service - handles chat session management."""
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from typing import List, Optional, Tuple
import logging

from app.models import HistoryMessage, ChatSessionMetadata
from app.infrastructure.database.repository.chat_repository import MONGO_CHAT_CLIENT

logger = logging.getLogger("LangChainBackend")


async def create_chat_session(
    user_id: str,
    title: str,
    request_id: str,
    correlation_id: str
) -> str:
    """Creates a new chat session document in MongoDB."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}]"

    try:
        chat_id = await run_in_threadpool(
            MONGO_CHAT_CLIENT.create_chat_session,
            user_id,
            title
        )

        if not chat_id:
            logger.error(f"{log_prefix} Failed to create chat session - no chat_id returned")
            raise HTTPException(
                status_code=500,
                detail="Failed to create chat session"
            )

        logger.info(f"{log_prefix} Created new chat session {chat_id[:8]}... with title: {title}")
        return chat_id

    except Exception as e:
        logger.error(f"{log_prefix} Failed to create chat session: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to create chat session: {e}"}
        )


async def get_user_chat_sessions(
    user_id: str,
    request_id: str,
    correlation_id: str,
    limit: int,
    cursor: Optional[str]
) -> Tuple[List[ChatSessionMetadata], Optional[str], bool]:
    """
    Get user's chat sessions with cursor-based pagination

    Returns: (sessions, next_cursor, has_more)
    """
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}]"

    try:
        sessions, next_cursor, has_more = await run_in_threadpool(
            MONGO_CHAT_CLIENT.get_user_chat_sessions,
            user_id,
            limit,
            cursor
        )
        logger.info(f"{log_prefix} Retrieved {len(sessions)} chat sessions.")
        return sessions, next_cursor, has_more
    except Exception as e:
        logger.error(f"{log_prefix} Failed to retrieve user sessions: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to retrieve chat sessions: {e}"}
        )


async def delete_chat_session(
    user_id: str,
    chat_id: str,
    request_id: str,
    correlation_id: str
):
    """Deletes a specific chat session for the authenticated user."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership,
        chat_id,
        user_id
    )

    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized delete attempt - user does not own this chat")
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: You do not own this chat session"
        )

    try:
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.delete_chat_session,
            chat_id,
            user_id
        )
        logger.info(f"{log_prefix} Chat session deleted successfully.")
    except Exception as e:
        logger.error(f"{log_prefix} Failed to delete chat session: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to delete chat session: {e}"}
        )


async def update_chat_title(
    user_id: str,
    chat_id: str,
    title: str,
    request_id: str,
    correlation_id: str
):
    """Updates the title of a chat session for the authenticated user."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership,
        chat_id,
        user_id
    )

    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized update attempt - user does not own this chat")
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: You do not own this chat session"
        )

    try:
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.update_chat_title,
            chat_id,
            user_id,
            title
        )
        logger.info(f"{log_prefix} Chat session title updated to: {title}")
    except Exception as e:
        logger.error(f"{log_prefix} Failed to update chat title: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to update chat title: {e}"}
        )


async def get_history(
    user_id: str,
    chat_id: str,
    request_id: str,
    correlation_id: str,
    limit: int,
    cursor: Optional[str]
) -> Tuple[List[HistoryMessage], Optional[str], bool]:
    """
    Get chat history with cursor-based pagination

    Returns: (messages, next_cursor, has_more)
    """
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership,
        chat_id,
        user_id
    )

    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized history access attempt")
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: You do not own this chat session"
        )

    try:
        history_list, next_cursor, has_more = await run_in_threadpool(
            MONGO_CHAT_CLIENT.get_history,
            chat_id,
            limit,
            cursor
        )

        if not history_list:
            logger.info(f"{log_prefix} No history found (empty chat)")
            return [], None, False

        logger.info(f"{log_prefix} Retrieved {len(history_list)} messages")
        return history_list, next_cursor, has_more

    except Exception as e:
        logger.error(f"{log_prefix} Failed to retrieve history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "DATABASE_ERROR",
                "message": "Failed to retrieve chat history from database"
            }
        )


async def clear_history(
    user_id: str,
    chat_id: str,
    request_id: str,
    correlation_id: str
):
    """Removes the chat history for a given session ID from MongoDB."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership,
        chat_id,
        user_id
    )

    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized clear attempt")
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: You do not own this chat session"
        )

    try:
        await run_in_threadpool(MONGO_CHAT_CLIENT.clear_history, chat_id)
        logger.info(f"{log_prefix} History cleared successfully.")
    except Exception as e:
        logger.error(f"{log_prefix} Failed to clear history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "DATABASE_ERROR",
                "message": "Failed to clear chat history from database"
            }
        )
