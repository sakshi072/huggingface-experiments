from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Optional, Tuple
from .config import (
    HF_CLIENT, MODEL_ID, 
    SYSTEM_MESSAGE_INFERENCE, logger, MAX_TOKENS, TEMPERATURE
)
from .models import HistoryMessage, ChatSessionMetadata
from .mongodb_client_handler import MONGO_CHAT_CLIENT

def sync_call_hf_api(
    messages: List[Dict[str, str]]
) -> str:
    """Performs the synchronous blocking call to the Hugging Face API."""

    if HF_CLIENT is None:
        raise ConnectionError("Hugging Face client is not initialized.")
    
    logger.debug(f"Calling LLM with context length: {len(messages)}")
    try:
        completion = HF_CLIENT.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stream=False
        )

        return completion.choices[0].message.content

    except Exception as e:
        logger.error(f"External LLM API Error during call: {e}", exc_info=True)
        raise RuntimeError(f"External LLM API call failed: {e}")


async def generate_response(
    user_id: str,
    chat_id: str,
    prompt: str,
    request_id: str,
    correlation_id: str
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

    # 2. Get recent history for context (fetch enough for context window)
    # Using cursor=None to get most recent messages
    history_messages, _, _ = await run_in_threadpool(
        MONGO_CHAT_CLIENT.get_history, 
        chat_id,
        limit=50,
        cursor=None
    )

    # 3. Prepare and append the new user message
    user_message = HistoryMessage(
        session_id=chat_id,
        role="user",
        content=prompt
    )
    history_messages.append(user_message)
    logger.debug(f"{log_prefix} Appended user message to history.")

    # 4. CRITICAL: Construct the inference context list
    # The context list MUST START with the system message
    inference_context = [SYSTEM_MESSAGE_INFERENCE]
    inference_context.extend([
        msg.to_inference_format()
        for msg in history_messages
    ])

    try:
        # 5. Call the synchronous API in a thread pool
        response_text = await run_in_threadpool(
            sync_call_hf_api,
            messages=inference_context
        )

        # 6. Prepare and append the assistant's response
        assistant_message = HistoryMessage(
            session_id=chat_id,
            role="assistant",
            content=response_text
        )

        await run_in_threadpool(
            MONGO_CHAT_CLIENT.save_messages, 
            chat_id, 
            user_id, 
            [user_message, assistant_message]
        )
        
        logger.info(f"{log_prefix} Successfully generated and stored response.")
        return response_text

    except (ConnectionError, RuntimeError) as e:
        error_message = HistoryMessage(
            session_id=chat_id,
            role="assistant",
            content="LLM inference failed for session"
        )
        await run_in_threadpool(
            MONGO_CHAT_CLIENT.save_messages, 
            chat_id, 
            user_id, 
            [user_message, error_message]
        )
        detail_msg = f"LLM inference failure. {str(e)}"

        logger.error(f"{log_prefix} Failed to generate response for session: {detail_msg}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "LLM_INFERENCE_FAILED", "message": detail_msg}
        )


async def generate_smart_title(
    user_id: str,
    first_message: str,
    assistant_response: str = None,
    request_id: str = None, 
    correlation_id: str = None
) -> str:
    """
    Uses the LLM to generate a concise, meaningful title for a chat.
    """
    log_prefix = f"[RID:{request_id[:8] if request_id else 'N/A'}] [CID:{correlation_id[:8] if correlation_id else 'N/A'}] [UID:{user_id[:8]}]"
    
    try: 
        if assistant_response:
            title_prompt = (
                f"Based on this conversation, generate a short, concise title (maximum 50 characters):\n\n"
                f"User: {first_message}\n"
                f"Assistant: {assistant_response}\n\n"
                f"Generate ONLY the title, nothing else. Keep it under 50 characters."
            )
        else:
            title_prompt = (
                f"Generate a short, concise title (maximum 50 characters) for a conversation starting with:\n\n"
                f"\"{first_message}\"\n\n"
                f"Generate ONLY the title, nothing else. Keep it under 50 characters."
            )
        
        title_context = [
            {
                "role": "system",
                "content": "You are a helpful assistant that generates concise, descriptive titles for conversations. Respond with ONLY the title, no explanations or extra text."
            },
            {
                "role": "user",
                "content": title_prompt
            }
        ]

        logger.debug(f"{log_prefix} Generating AI title...")

        if HF_CLIENT is None:
            raise ConnectionError("Hugging Face client is not initialized.")

        completion = await run_in_threadpool(
            lambda: HF_CLIENT.chat.completions.create(
                model=MODEL_ID,
                messages=title_context,
                max_tokens=30,
                temperature=0.7,
                stream=False
            )
        )

        generated_title = completion.choices[0].message.content.strip()
        generated_title = generated_title.strip('"\'')

        prefixes_to_remove = ["Title:", "Chat:", "Conversation:"]
        for prefix in prefixes_to_remove:
            if generated_title.startswith(prefix):
                generated_title = generated_title[len(prefix):].strip()

        if len(generated_title) > 50:
            generated_title = generated_title[:47] + "..."
        
        if len(generated_title) < 3:
            logger.warning(f"{log_prefix} Generated title too short, using fallback")
            generated_title = generate_fallback_title(first_message)
        
        logger.info(f"{log_prefix} Generated AI title: '{generated_title}'")
        return generated_title
        
    except Exception as e:
        logger.error(f"{log_prefix} Failed to generate AI title: {e}", exc_info=True)
        return generate_fallback_title(first_message)


def generate_fallback_title(message: str) -> str:
    """
    Generate a fallback title by truncating the message intelligently.
    """
    cleaned = message.strip().replace('\n', ' ').replace('\r', '')
    cleaned = ' '.join(cleaned.split())
    
    if len(cleaned) <= 50:
        return cleaned
    
    truncated = cleaned[:47]
    last_space = truncated.rfind(' ')
    
    if last_space > 30:
        return truncated[:last_space] + '...'
    
    return truncated + '...'


# --- Chat Session Management Functions ---

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
            return [], None, False  # FIXED: Return tuple, not just list
        
        logger.info(f"{log_prefix} Retrieved {len(history_list)} messages")
        return history_list, next_cursor, has_more  # FIXED: Use correct variable name
        
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