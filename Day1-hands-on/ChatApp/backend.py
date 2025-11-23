import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from huggingface_hub import InferenceClient
from starlette.concurrency import run_in_threadpool

# --- Configuration ---
# NOTE: This API key must be available in the environment where the backend is run.
HF_TOKEN = os.environ.get("HF_TOKEN", "")
MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
API_BASE_URL = "https://router.huggingface.co/v1/"
MAX_TOKENS = 50
TEMPERATURE = 0.7

# --- Data Model for API Request Body ----
class ChatRequest(BaseModel):
    messages: list

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
async def chat_complete(request: ChatRequest):
    """
    Receives the chat history and returns the LLM response.
    """
    try:
        response_text = await async_call_hf_api(
            client=hf_client,
            messages=request.messages,
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )
        return {"response": response_text}
    except HTTPException as e:
        raise e
    except Exception as e:
        # This catches errors not explicitly handled in call_hf_api
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")


