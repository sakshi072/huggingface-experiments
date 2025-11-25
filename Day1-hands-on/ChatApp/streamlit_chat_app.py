import os
import streamlit as st
import time
import httpx # New Import for Asynchronous HTTP Client
import uuid # Used for session ID
import anyio # New Import to run async code in Streamlit
from typing import List, Dict, Any

# --- Configuration ---
# NOTE: Adjust this URL based on where your FastAPI backend is running.
BACKEND_URL = "http://localhost:8000/chat/complete"


# --- 1. Initialization (Ephemeral Session State) ---

# We will use a unique session ID for the user
if 'user_id' not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())
USER_ID = st.session_state.user_id

# Initialize chat history in session state (in-memory)
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": "You are friendly, detail oriented and concise AI assistant named 'HUGG'. Keep your answers accurate and brief."
        }
    ]

if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False

# Temporary storage for the prompt after the first rerun (only used internally)
if '_temp_prompt' not in st.session_state:
    st.session_state._temp_prompt = None

# --- 2. Streamlit UI Setup ---

st.set_page_config(page_title="Hugg Chatbot", layout="centered")
st.title("🤖 Hugg: AI Assistant (Ephemeral Session)")
st.caption(f"Session User ID: {USER_ID[:8]}...")
st.caption("Backend: FastAPI | Persistence: None (History resets on tab close)")

# --- 3. Communication Logic (HTTP Request to FastAPI Backend) ---

async def async_get_ai_response_from_backend(user_prompt: str) -> List[Dict[str,str]] | str:
    """
    Makes an ASYNC HTTP POST request to the FastAPI backend with the message history.
    """

    payload = {"user_id": USER_ID, "prompt": user_prompt}

    try: 
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Send the request to the backend
            response = await client.post(BACKEND_URL, json=payload)
            response.raise_for_status()

            response_data = response.json()

            full_history = response_data.get("full_history", [])

            if full_history:
                return full_history
            else:
                return "Error: Backend response missing 'response' field."

    except httpx.RequestException as e:
        # Handle connection errors or bad HTTP status codes immediately
        return f"Error: Failed to communicate with backend service at {BACKEND_URL}. ({e})"
    except Exception as e:
        return f"An unexpected error occurred while processing backend response: {e}"

def get_ai_response_from_backend(user_promt: str) -> List[Dict[str,str]] | str:
    """
    Synchronous wrapper to run the async request function using anyio.
    """
    return anyio.run(async_get_ai_response_from_backend, user_promt)


# Display all messages (excluding the initial system message)
for message in st.session_state.messages:
    if message['role'] != 'system':
        avatar = "👤" if message['role'] == "user" else "🤖"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

# --- 5. Handle New Input (In-Memory Logic + Backend Call) ---

if prompt := st.chat_input("Ask Hugg something...", disabled=st.session_state.is_processing):

    # 1. Start Processing: Set state to True and trigger a rerun to disable the input field
    st.session_state._temp_prompt = prompt
    st.session_state.is_processing = True
    # st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

# 6. Process the Response (This runs on the subsequent rerun)
if st.session_state.is_processing and st.session_state._temp_prompt:

    user_prompt_to_send = st.session_state._temp_prompt
    st.session_state.messages.append({"role": "user", "content": user_prompt_to_send})

    with st.chat_message("user", avatar="👤"):
        st.markdown(user_prompt_to_send)

    # Get AI Response from FastAPI Backend
    with st.spinner("Hugg is thinking..."):
        # context_messages = st.session_state.messages
        backend_response = get_ai_response_from_backend(user_prompt_to_send)
    
    # Update State
    if isinstance(backend_response, list):
        st.session_state.messages = backend_response
    else:
        st.session_state.messages.append({"role":"assistant", "content": backend_response})

    # Append Assistant Message to In-Memory History
    # st.session_state.messages.append({"role": "assistant", "content": ai_response})

    # Render the Assistant Message
    # with st.chat_message("assistant", avatar="🤖"):
    #     st.markdown(ai_response)

    # 6. Unlock the input and trigger final rerun
    st.session_state._temp_prompt = None # Clear temporary storage
    st.session_state.is_processing = False
    st.rerun()