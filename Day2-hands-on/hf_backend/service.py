from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Optional
from .config import (
    HF_CLIENT, MODEL_ID, 
    SYSTEM_MESSAGE_INFERENCE, logger, MAX_TOKENS, TEMPERATURE
)
from .models import HistoryMessage, ChatSessionMetadata
from .mongodb_client_handler import MONGO_CHAT_CLIENT

def sync_call_hf_api(
    messages: List[Dict[str,str]]
) -> str:
    """Performs the synchronous blocking call to the Hugging Face API."""

    if HF_CLIENT is None:
        raise ConnectionError("Hugging Face client is not initialized.")
    
    logger.debug(f"Calling LLM with context length: {len(messages)}")
    try:
        completion = HF_CLIENT.chat.completions.create(
            model = MODEL_ID,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=False
        )

        return completion.choices[0].message.content

    except Exception as e:
        logger.error(f"External LLM API Error during call: {e}", exc_info=True)
        # Re-raise as a standard Python RuntimeError for the threadpool wrapper to catch
        # This keeps the error handling chain clean: General Python Error -> RuntimeError
        raise RuntimeError(f"External LLM API call failed: {e}")


async def generate_response(
    user_id:str,
    chat_id:str,
    prompt:str,
    request_id:str,
    correlation_id:str
) -> str:
    """
    Manages history, calls the LLM, updates history, and returns only the response text.
    """

    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    # 1. Verify user owns this chat
    is_owner = await run_in_threadpool(
        MONGO_CHAT_CLIENT.verify_chat_ownership, 
        chat_id, 
        user_id
    )

    if not is_owner:
        logger.error(f"{log_prefix} Unauthorized access attempt - user does not own this chat")
        raise HTTPException(
            status_code=403, 
            detail="Unauthorized access to chat session"
        )


    # 2. Initialize history for a new session (it will start empty)
    history_message = await run_in_threadpool(MONGO_CHAT_CLIENT.get_history, chat_id)

    # 2. Prepare and append the new user message to the STORE
    user_message = HistoryMessage(
        session_id=chat_id,
        role="user",
        content=prompt
    )
    history_message.append(user_message)
    logger.debug(f"{log_prefix} Appended user message to history.")

    # 3. CRITICAL: Construct the inference context list
    # The context list MUST START with the system message
    inference_context = [SYSTEM_MESSAGE_INFERENCE]
    inference_context.extend([
        msg.to_inference_format()
        for msg in history_message
    ])

    try:
        # 4. Call the synchronous API in a thread pool
        response_text = await run_in_threadpool(
            sync_call_hf_api,
            messages=inference_context
        )

        # 5. Prepare and append the assistant's response to the STORE
        assistant_message = HistoryMessage(
            session_id=chat_id,
            role="assistant",
            content=response_text
        )

        await run_in_threadpool(MONGO_CHAT_CLIENT.save_messages, chat_id, [user_message, assistant_message])
        
        # 6. Update chat metadata (timestamp and message count)
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.update_chat_metadata, 
            chat_id, 
            user_id
        )
        logger.info(f"{log_prefix} Successfully generated and stored response.")
        return response_text

    except (ConnectionError, RuntimeError) as e:
        error_message = HistoryMessage(
            session_id=chat_id,
            role="assistant",
            content="LLM inference failed for session"
        )
        await run_in_threadpool(MONGO_CHAT_CLIENT.save_messages, chat_id, [user_message, error_message])
        detail_msg = f"LLM inference failure. {str(e)}"

        logger.error(f"{log_prefix} Failed to generate response for session: {detail_msg}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "LLM_INFERENCE_FAILED", "message": detail_msg}
        )

# --- Chat Session Management Functions ---

async def create_chat_session(
    user_id:str,
    title: str,
    request_id:str,
    correlation_id:str
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
    user_id:str,
    request_id:str,
    correlation_id:str
) -> List[ChatSessionMetadata]:
    """Retrieves all chat sessions for a specific user."""
    
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}]"

    try:
        sessions = await run_in_threadpool(
            MONGO_CHAT_CLIENT.get_user_chat_sessions,
            user_id
        )
        logger.info(f"{log_prefix} Retrieved {len(sessions)} chat sessions.")
        return sessions
    except Exception as e:
        logger.error(f"{log_prefix} Failed to retrieve user sessions: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to retrieve chat sessions: {e}"}
        )

async def delete_chat_session(
    user_id:str,
    chat_id:str,
    request_id:str,
    correlation_id:str
):
    """Deletes a specific chat session for the authenticated user."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"
    
    # Verify ownership before deletion
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
    user_id:str,
    chat_id:str,
    title:str,
    request_id:str,
    correlation_id:str
):
    """Updates the title of a chat session for the authenticated user."""
    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"
    
    # Verify ownership before updating
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
    user_id:str,
    chat_id:str,
    request_id:str,
    correlation_id:str,
    limit: int = 10,
    offset: int = 0
) -> List[HistoryMessage]:
    """Retrieves the chat history for a given session ID."""

    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    # Verify ownership
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

    # If session is new or invalid, return an empty list
    try: 
        history_list = await run_in_threadpool(MONGO_CHAT_CLIENT.get_history, chat_id, limit, offset)

        if not history_list:
            logger.info(f"{log_prefix} No history found (empty chat or invalid offset)")
            return []
        
        logger.info(f"{log_prefix} Retrieved {len(history_list)} messages")
        return history_list
        
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
    request_id:str,
    correlation_id:str
):
    """Removes the chat history for a given session ID from MongoDB."""

    log_prefix = f"[RID:{request_id[:8]}] [CID:{correlation_id[:8]}] [UID:{user_id[:8]}] [CHAT:{chat_id[:8]}]"

    # Verify ownership
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

        await run_in_threadpool(
            MONGO_CHAT_CLIENT.reset_message_count,
            chat_id,
            user_id
        )
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

    