from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from typing import List, Dict
from .config import (
    HF_CLIENT, MODEL_ID, 
    SYSTEM_MESSAGE_INFERENCE, logger, MAX_TOKENS, TEMPERATURE
)
from .models import HistoryMessage
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
    session_id:str,
    prompt:str
) -> str:
    """
    Manages history, calls the LLM, updates history, and returns only the response text.
    """

    # 1. Initialize history for a new session (it will start empty)
    history_message = await run_in_threadpool(MONGO_CHAT_CLIENT.get_history, session_id)

    # 2. Prepare and append the new user message to the STORE
    user_message = HistoryMessage(
        session_id=session_id,
        role="user",
        content=prompt
    )
    history_message.append(user_message)
    logger.debug(f"Appended user message to history for session: {session_id[:8]}...")

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
            session_id=session_id,
            role="assistant",
            content=response_text
        )

        await run_in_threadpool(MONGO_CHAT_CLIENT.save_messages, session_id, [user_message, assistant_message])
        logger.info(f"Successfully generated and stored response for session: {session_id[:8]}...")

        return response_text

    except (ConnectionError, RuntimeError) as e:
        error_message = HistoryMessage(
            session_id=session_id,
            role="assistant",
            content="LLM inference failed for session"
        )
        await run_in_threadpool(MONGO_CHAT_CLIENT.save_messages, session_id, [user_message, error_message])
        detail_msg = f"LLM inference failure. {str(e)}"

        logger.error(f"Failed to generate response for session {session_id[:8]}...: {detail_msg}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "LLM_INFERENCE_FAILED", "message": detail_msg}
        )
        
async def get_history(session_id:str) -> List[HistoryMessage]:
    """Retrieves the chat history for a given session ID."""

    # If session is new or invalid, return an empty list
    try: 
        history_list = await run_in_threadpool(MONGO_CHAT_CLIENT.get_history, session_id)

        if not history_list:
            logger.warning(f"No history found for session: {session_id[:8]}...")
            return []
        
        return history_list
        
    except Exception as e:
        # Catch any exceptions during MongoDB I/O and raise a clean HTTPException
        logger.error(f"Failed to retrieve history for {session_id[:8]}...: {e}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "DATABASE_ERROR", "message": f"Failed to retrieve chat history from database: {e}"}
        )

async def clear_history(session_id:str):
    """Removes the chat history for a given session ID from MongoDB."""
    try:
        await run_in_threadpool(MONGO_CHAT_CLIENT.clear_history, session_id)
    except Exception as e:
        logger.error(f"Failed to clear history for {session_id[:8]}...: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DATABASE_ERROR", "message": f"Failed to clear chat history from database: {e}"}
        )

    