import streamlit as st
import httpx # New Import for Asynchronous HTTP Client
import uuid # Used for session ID
import anyio # New Import to run async code in Streamlit
from typing import List, Dict, Any

# --- Custom Exception for Error Propagation ---
class FetchHistoryError(Exception):
    """Custom exception to wrap and propagate human-readable errors from history fetching."""
    pass

# --- Configuration ---
# NOTE: Adjust this URL based on where your FastAPI backend is running.
POST_URL = "http://localhost:8000/chat/prompt" # For sending prompt
GET_URL = "http://localhost:8000/chat/history" # For fetching history
CLEAR_URL = "http://localhost:8000/chat/history/clear" # New URL for clearing history
HISTORY_LIMIT =6 # Number of messages to fetch per pagination request

# --- 1. Initialization ---

# We will use a unique session ID for the user
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
SESSION_ID = st.session_state.session_id

# Temporary state for processing lock and prompt storage
if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False
if '_temp_prompt' not in st.session_state:
    st.session_state._temp_prompt = None
# New state for history error tracking
if 'history_error' not in st.session_state:
    st.session_state.history_error = None
# Initialize messages, which will be overwritten by the GET call.
# Messages now hold the full HistoryMessage dictionary structure.
if "messages" not in st.session_state:
    st.session_state.messages = []
if 'history_offset' not in st.session_state:
    st.session_state.history_offset = 0 # Offset for next oldest messages
if 'has_more_history' not in st.session_state:
    st.session_state.has_more_history = True
if 'initial_load_complete' not in st.session_state:
    st.session_state.initial_load_complete = False
if 'correlation_id' not in st.session_state:
    st.session_state.correlation_id = str(uuid.uuid4())

def run_async_task(task_func, *args):
    """Synchronous wrapper for running async functions."""
    return anyio.run(task_func, *args)

async def async_handle_backend_error(response: httpx.Response) -> str:
    """Helper to extract meaningful, human-readable error message from 4xx/5xx responses."""

    try:
        # Try to parse a JSON error body from the backend (FastAPI's HTTPException format)
        error_data = response.json()
        if isinstance(error_data, dict) and 'detail' in error_data:
            detail = error_data['detail']

            if isinstance(detail, dict) and 'message' in detail:
                # Human-readable message from backend logic (good UX)
                return f"Server Error ({response.status_code}): {detail['message']}"

            return f"Server Error ({response.status_code}): {detail}"
        # Fallback if the error response is not in the expected JSON format
        return f"Server Error ({response.status_code}): {response.reason_phrase}"

    except:
        # Fallback if response is not JSON parseable
        return f"Server Error ({response.status_code}): Could not parse error details."   


async def async_clear_history():
    """Sends a DELETE request to clear the history for the current session."""
    final_clear_url = f"{CLEAR_URL}?session_id={SESSION_ID}"

    headers = {
        "X-Correlation-ID": st.session_state.correlation_id
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            st.toast("Clearing chat history...", icon="🗑️")
            response = await client.delete(final_clear_url, headers=headers)
            response.raise_for_status()

            # On success (204 No Content), clear local state immediately
            st.session_state.messages = []
            st.session_state.history_offset = 0
            st.session_state.has_more_history = True # Reset pagination
            st.session_state.initial_load_complete = False
            st.toast("Chat history cleared!", icon="✅")
    
    except httpx.HTTPStatusError as e:
        error_msg = await async_handle_backend_error(e.response)
        st.error(f"Failed to clear history: {error_msg}")

    except httpx.RequestError as e:
        st.error(f"Connection Error: Failed to clear history. (Check if FastAPI is running)")
    
    except Exception as e:
        st.error(f"An unexpected error occurred while clearing history: {e}")


# --- 2. Streamlit UI Setup ---

st.set_page_config(page_title="Hugg Chatbot", layout="centered")

# Use columns for layout: Title/Caption on the left, Button on the right
col1, col2 = st.columns([3, 1])

with col1:
    st.title("🤖 Hugg: AI Assistant")
    st.caption(f"Session ID: {SESSION_ID[:8]}...")
    st.caption("Backend: FastAPI | Persistence: MongoDB")

with col2:
    if st.button("Clear History", use_container_width=True, disabled=st.session_state.is_processing or len(st.session_state.messages) == 0):
        if st.session_state.messages: # Only proceed if there are messages to clear
            st.session_state.is_processing = True
            run_async_task(async_clear_history)
            st.session_state.is_processing = False
            # Rerun to display cleared state
            st.rerun()

# --- 3. Communication Logic (HTTP Request to FastAPI Backend) ---

async def async_get_ai_response_from_backend(user_prompt: str) -> str:
    """Sends prompt via POST and expects only the inference response text."""
    headers = {
        "session-id": SESSION_ID,
        "X-Correlation-ID": st.session_state.correlation_id
    }
    payload = {"prompt": user_prompt}

    try: 
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Send the request to the backend
            response = await client.post(POST_URL, json=payload, headers=headers)
            response.raise_for_status()

            return response.json().get("response", "Error: Backend response missing 'response' field.")

    except httpx.HTTPStatusError as e:
        # 2a. Catch HTTP Status Errors (4xx, 5xx) raised by raise_for_status
        # Use the helper to format the error from the response body
        return await async_handle_backend_error(e.response)

    except httpx.RequestError as e:
        # 2b. Catch Connection/Network Errors (e.g., DNS, Timeout)
        return f"Connection Error: Failed to communicate with backend service at {POST_URL}. (Check if FastAPI is running)"
    
    except Exception as e:
        # Handle any other unexpected Python exceptions
        return f"An unexpected client-side error occurred: {e}"

async def async_fetch_history(limit:int, offset:int, append:bool) -> List[Dict[str,Any]]:
    """Fetches the full history (HistoryMessage structure) from the backend GET endpoint."""
    # Generate new IDs for the GET request (separate request lifecycle)
    current_request_id = str(uuid.uuid4())
    # Reuse correlation ID
    correlation_id = st.session_state.correlation_id

    final_get_url = f"{GET_URL}?session_id={SESSION_ID}&limit={limit}&offset={offset}&X-Request-ID={current_request_id}&X-Correlation-ID={correlation_id}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(final_get_url)
            response.raise_for_status()
            
            history_response = response.json().get("history", [])
            if not isinstance(history_response, list):
                raise FetchHistoryError("Backend returned history in an invalid format.")
            
            is_end_of_history = len(history_response) < limit
            if is_end_of_history:
                st.session_state.has_more_history = False
            
            if append:
                # Deduplication: Use a composite key (role + content) to prevent duplicates due to offset errors.
                
                # 1. Create a set of keys for all currently displayed messages
                existing_keys = set((m.get('role', 'unknown'), m.get('content', '')) for m in st.session_state.messages)
                
                # 2. Filter the newly fetched history (older messages) to keep only unique ones
                unique_new_messages = []
                for msg in history_response:
                    key = (msg.get('role', 'unknown'), msg.get('content', ''))
                    if key not in existing_keys:
                        unique_new_messages.append(msg)
                        
                # 3. Prepend only unique older messages
                st.session_state.messages = unique_new_messages + st.session_state.messages
                
                # 4. Update offset based on how many unique messages were actually added
                st.session_state.history_offset += len(unique_new_messages)
                
            else:
                # Initial load or new messages overwrite the state
                st.session_state.messages = history_response
                st.session_state.history_offset = len(history_response)
            
            return st.session_state.messages
            # --- END PAGINATION LOGIC REFINED ---
                

    except httpx.HTTPStatusError as e:
        # Catch HTTP Status Errors (4xx, 5xx) raised by raise_for_status
        error_msg = await async_handle_backend_error(e.response)
        raise FetchHistoryError(error_msg)

    except httpx.RequestError as e:
        # Catch Connection/Network Errors
        raise FetchHistoryError(f"Connection Error: Failed to fetch history. (Check if FastAPI is running)")
    
    except Exception as e:
        # Handle any other unexpected Python exceptions
        raise FetchHistoryError(f"An unexpected client-side error occurred while fetching history: {e}")   

# --- 4. History Refresh Logic (Run on every rerun) ---
# Container for all chat messages to enable scroll detection
# chat_container = st.container(height=500, border=True)

def initial_history_load():
    if st.session_state.is_processing or st.session_state.initial_load_complete:
        return
    try:
        run_async_task(async_fetch_history, HISTORY_LIMIT, 0, False)
        st.session_state.initial_load_complete = True
    except FetchHistoryError as e:
        st.session_state.history_error = str(e)
        st.error(st.session_state.history_error)

initial_history_load()

# Display history error if present
if st.session_state.history_error:
    st.error(st.session_state.history_error)

# Displays the current history fetched
# We display messages in their fetched order (oldest to newest)
if st.session_state.has_more_history and st.session_state.initial_load_complete and len(st.session_state.messages) > 0:
    if st.button("Load More History", use_container_width=True, disabled=st.session_state.is_processing):
        st.session_state.is_processing = True
        st.session_state.history_error = None # Clear previous error
        
        # Fetch older history (append=True) using the current offset
        try:
            run_async_task(async_fetch_history, HISTORY_LIMIT, st.session_state.history_offset, True)
        except FetchHistoryError as e:
            st.session_state.history_error = str(e)
        
        st.session_state.is_processing = False
        st.rerun()
# Display status messages when history is fully loaded or empty
elif st.session_state.initial_load_complete and not st.session_state.has_more_history:
    # Check if there are any messages to display "fully loaded" or "start chatting"
    if len(st.session_state.messages) > 0:
        st.caption("--- History fully loaded ---")
    else:
        st.caption("--- Start chatting to begin your history ---")

# Displays the current history fetched
for message in st.session_state.messages:
    # 💡 IMPORTANT: Extracting 'role' and 'content' from the full HistoryMessage dict
    role = message.get('role', 'unknown')
    content = message.get('content', 'Error: Message content missing.')
    avatar = "👤" if role == "user" else "🤖"
    with st.chat_message(role, avatar=avatar):
        st.markdown(content)

# --- 5. Handle New Input (In-Memory Logic + Backend Call) ---

if prompt := st.chat_input("Ask Hugg something...", disabled=st.session_state.is_processing):

    # 1. Start Processing: Set state to True and trigger a rerun to disable the input field
    st.session_state._temp_prompt = prompt
    st.session_state.is_processing = True
    st.session_state.correlation_id = str(uuid.uuid4())

    st.rerun()

# 6. Process the Response (This runs on the subsequent rerun)
if st.session_state.is_processing and st.session_state._temp_prompt:

    user_prompt_to_send = st.session_state._temp_prompt

    with st.chat_message("user", avatar="👤"):
        st.markdown(user_prompt_to_send)

    # Get AI Response from FastAPI Backend
    with st.spinner("Hugg is thinking..."):
        # context_messages = st.session_state.messages
        backend_response = run_async_task(async_get_ai_response_from_backend, user_prompt_to_send)

    with st.chat_message("assistant", avatar="🤖"):
        if backend_response.startswith(("Connection Error:", "Server Error:")):
            st.error(backend_response)
        else:
            st.markdown(backend_response)

    # 6. Unlock the input and trigger final rerun
    st.session_state.history_offset = 0
    st.session_state.has_more_history = True 
    st.session_state.initial_load_complete = False 

    st.session_state._temp_prompt = None # Clear temporary storage
    st.session_state.is_processing = False
    st.rerun()