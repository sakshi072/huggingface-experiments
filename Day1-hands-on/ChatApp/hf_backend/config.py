import os 
import logging
from typing import Dict, List
from huggingface_hub import InferenceClient
from .models import HistoryMessage
from pymongo import MongoClient # New Import
from pymongo.server_api import ServerApi

# --- Logging Setup ---
# Configure a basic logger for the application
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HuggBackend")

# --- Configuration ---
HF_TOKEN = os.environ.get("HF_TOKEN", "")
MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
API_BASE_URL = "https://router.huggingface.co/v1/"
MAX_TOKENS = 50
TEMPERATURE = 0.7

# --- MongoDB Configuration ---
# NOTE: Replace with your actual connection details
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = os.environ.get("MONGO_DB_NAME")

try:
    MONGO_CLIENT = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    MONGO_CLIENT.admin.command('ping')
    MONGO_DB = MONGO_CLIENT[DB_NAME]
    logger.info(f"Successfully connected to MongoDB database: {DB_NAME}")
except Exception as e:
    logger.error(f"FATAL: Could not connect to MongoDB at {MONGO_URI}. History functions will be disabled. Error: {e}")
    # Set to None if connection fails
    MONGO_DB = None

# Define the initial system message using the HistoryMessage model
SYSTEM_MESSAGE_INFERENCE: Dict[str, str] = {
    "role": "system",
    "content": "You are friendly, detail oriented and concise AI assistant named 'HUGG'. Keep your answers accurate and brief."
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