import os
import logging
from typing import Dict
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HuggBackend")

# --- Configuration ---
HF_TOKEN = os.getenv("HF_TOKEN", "")
MODEL_ID = "meta-llama/Llama-3.2-3B-Instruct"
API_BASE_URL = "https://router.huggingface.co/v1/"
MAX_TOKENS = 1024
TEMPERATURE = 0.7

# --- System Message ---
SYSTEM_MESSAGE_INFERENCE: Dict[str, str] = {
    "role": "system",
    "content": "You are HUGG, a helpful AI assistant. Provide clear, accurate answers. You have access to tools. If the user asks a question about internal documents or knowledge you don't have, you MUST use the search_knowledge_base tool. Do not answer from memory if the tool can help."
}

# --- Hugging Face Client Initialization ---
def initialize_hf_client() -> InferenceClient | None:
    """Initializes and returns the Hugging Face InferenceClient."""
    if not HF_TOKEN:
        logger.error("FATAL: HF_TOKEN environment variable not set in backend.")
        return None

    try:
        client = InferenceClient(
            base_url=API_BASE_URL,
            api_key=HF_TOKEN
        )
        logger.info("Hugging Face InferenceClient initialized.")
        return client
    except Exception as e:
        logger.error(f"Error initializing InferenceClient: {e}", exc_info=True)
        return None

# Global Client Setup
HF_CLIENT = initialize_hf_client()
