import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from huggingface_hub import InferenceClient
from starlette.concurrency import run_in_threadpool
from typing import Dict, List, Any

# --- Configuration ---
# NOTE: This API key must be available in the environment where the backend is run.
HF_TOKEN = os.environ.get("HF_TOKEN", "")
MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
API_BASE_URL = "https://router.huggingface.co/v1/"
MAX_TOKENS = 50
TEMPERATURE = 0.7

# Define the initial system message
SYSTEM_MESSAGE = {
    "role": "system",
    "content": "You are friendly, detail oriented and concise AI assistant named 'HUGG'. Keep your answers accurate and brief."
}

# --- State Management (In-Memory History Store) ---
# Stores the chat history for each unique user ID.
# Key: user_id (str) | Value: List[Dict[str, str]] (Message history)
# NOTE: In a production environment, this would be replaced by a proper database (e.g., Redis, PostgreSQL)
chat_history_store: Dict[str, List[Dict[str, str]]] = {}

# --- Data Model for API Request Body ----
class ChatPrompt(BaseModel):
    user_id:str
    prompt:str

# --- Hugging Face Client Initialization Function ---

def initialize_hf_client() -> InferenceClient | None:
    """
    Initializes and returns the Hugging Face InferenceClient.
    Returns None if the HF_TOKEN is missing or initialization fails.
    """
    if not HF_TOKEN:
        print("FATAL: HF_TOKEN environment variable not set in backend.")
        return None

    try: 
        # The client uses the OpenAI compatibility layer for chat completions
        client = InferenceClient(
            base_url=API_BASE_URL,
            api_key=HF_TOKEN
        )
        print("Hugging Face InferenceClient initialized.")
        return client
    
    except Exception as e:
        print(f"Error initializing InferenceClient: {e}")
        return None
    
# --- Global Client Setup ---
# Initialize the client globally when the app starts.
hf_client = initialize_hf_client()


# --- FastAPI App Setup ---
app = FastAPI(title="Hugg Chat Inference Service", version="1.0")


# --- Core Inference Logic ---

def sync_call_hf_api(
    client: InferenceClient | None, 
    messages: list, 
    model: str, 
    max_tokens: int, 
    temperature: float, 
) -> str:
    """
    Performs the synchronous blocking call to the Hugging Face API.
    """

    # Pass the complete history list to maintain context
    completion = client.chat.completions.create(
        model = model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False
    )
    return completion.choices[0].message.content

async def async_call_hf_api(
    client: InferenceClient | None, 
    messages: list, 
    model: str, 
    max_tokens: int, 
    temperature: float, 
) -> str:
    """
    Wraps the synchronous API call using run_in_threadpool to make it non-blocking.
    """
    if client is None: 
        raise HTTPException(status_code=503, detail="LLM service is unavailable: Backend client failed to initialize due to missing key or connection error.")

    try: 
        # This moves the blocking synchronous function to an external thread, 
        # allowing the FastAPI event loop to continue processing other requests.
        response_text = await run_in_threadpool(
            sync_call_hf_api,
            client,
            messages=messages,
            model = model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response_text

    except Exception as e:
        # Raise an HTTPException immediately on failure
        raise HTTPException(status_code=500, detail=f"LLM inference failed. Error: {e}")

# --- API Endpoint ---
@app.post("/chat/complete")
async def chat_prompt(request: ChatPrompt):
    """
    Receives the chat history and returns the LLM response.
    """

    user_id = request.user_id
    prompt = request.prompt

    # 1. Initialize history for the user if it doesn't exist
    if user_id not in chat_history_store:
        chat_history_store[user_id] = [SYSTEM_MESSAGE]
    
    user_message = {"role":"user", "content":prompt}
    chat_history_store[user_id].append(user_message)

    try:
        full_context = chat_history_store[user_id]
        response_text = await async_call_hf_api(
            client=hf_client,
            messages=full_context,
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )

        assistant_message = {"role":"assistant", "content": response_text}
        chat_history_store[user_id].append(assistant_message)

        return {"response": response_text, "full_history": chat_history_store[user_id]}

    except HTTPException as e:
        chat_history_store[user_id].pop()
        raise e
    except Exception as e:
        # This catches errors not explicitly handled in call_hf_api
        chat_history_store[user_id].pop()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")


