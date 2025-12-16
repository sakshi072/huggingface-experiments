import os 
import logging
from typing import Dict, Optional
from huggingface_hub import InferenceClient
from .models import HistoryMessage
from pymongo import MongoClient # New Import
from pymongo.server_api import ServerApi
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from contextlib import contextmanager

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

MONGO_POOL_CONFIG = {
    # Connection Pool Size
    "maxPoolSize": int(os.environ.get("MONGO_MAX_POOL_SIZE", "50")),
    "minPoolSize": int(os.environ.get("MONGO_MIN_POOL_SIZE", "10")),

    # Connection Timeouts (milliseconds)
    "connectionTimeoutMS": 10000, # 10 seconds to establish connection
    "serverSelectionTimeoutMS": 5000, # 5 seconds to select server
    "socketTimeoutMS": 45000, # 45 seconds for socket operations

    # Connection Lifecycel
    "maxIdleTimeMS": 300000, # 5 minutes - close idle connection
    "waitQueueTimeoutMS": 10000, # 10 seconds max wait for connection from pool

    # Retry Configuration
    "retryWrites": True, # Automatic retry for write operations
    "retryReads": True, # Automatic retry for read operations

    # Write Concern (for data consistency)
    "w": "majority", # Wait for majority of replica set
    "journal": True, # Wait for journal commit (durability )

    # Read Preference
    "readPreference": "primaryPreferred", # Read from primary if available

    # Server API Version
    "server_api": ServerApi('1')
}

class MongoDBManager:
    """
    Singleton MongoDB Manager with Connection Pooling
    
    Why Singleton?
    - Ensures ONE connection pool per application instance
    - Prevents connection pool exhaustion
    - Thread-safe connection sharing
    """
    _instance: Optional['MongoDBManager'] = None
    _client: Optional[MongoClient] = None 
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self):
        """Initialize MongoDB connection with production settings"""
        if self._client is not None:
            logger.warning("MongoDB already initialized")
            return
        
        if not MONGO_URI:
            logger.error("FATAL: MONGO_URI not set")
            raise ValueError("MONGO_URI environment variable required")
        
        try: 
            logger.info("Initializing MongoDB connection pool...")
            logger.info(f"Pool Config: maxPoolSize={MONGO_POOL_CONFIG['maxPoolSize']}, "
                       f"minPoolSize={MONGO_POOL_CONFIG['minPoolSize']}")

            # Create client with connection pooling
            self._client = MongoClient(MONGO_URI, **MONGO_POOL_CONFIG)

            # Test connection
            self._client.admin.command('ping')

            # Get database
            self._db = self._client[DB_NAME]

            logger.info(f"✅ MongoDB connected successfully to database: {DB_NAME}")
            logger.info(f"✅ Connection pool initialized with {MONGO_POOL_CONFIG['maxPoolSize']} max connections")
        
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"❌ FATAL: MongoDB connection failed: {e}")
            self._client = None
            self._db = None
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during MongoDB init: {e}")
            raise

    @property
    def client(self) -> MongoClient:
        """Get MongoDB client (connection pool)"""
        if self._client is None:
            raise RuntimeError("MongoDB not initialized. Call initialize() first.")
        return self._client
    
    @property 
    def db(self):
        """Get database instance"""
        if self._db is None:
            raise RuntimeError("MongoDB not initialized. Call initialize() first.")
        return self._db

    def health_check(self) -> bool:
        """
        Check MongoDB connection health
        
        Use Case: Health check endpoint, monitoring
        """
        try: 
            self._client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_connection_stats(self) -> Dict:
        """
        Get connection pool statistics
        
        Use Case: Monitoring, debugging connection issues
        """
        try:
            stats = self._client.server_info()
            pool_options = self._client.options.pool_options

            return {
                "connected": True,
                "max_pool_size": pool_options.max_pool_size,
                "min_pool_size": pool_options.min_pool_size,
                "database": DB_NAME,
                "server_version": stats.get("version"),
            }
        except Exception as e:
            logger.error(f"Failed to get connection stats: {e}")
            return {"connected": False, "error": str(e)}

    def close(self):
        """Close MongoDB connection (graceful shutdown)"""
        if self._client:
            logger.info("Closing MongoDB connection pool...")
            self._client.close()
            self._client = None
            self._db = None
            logger.info("✅ MongoDB connection closed")

# Initialize singleton instance
mongo_manager = MongoDBManager()

def get_db():
    """Get database instance - initialize if needed"""
    if mongo_manager._db is None:
        mongo_manager.initialize()
    return mongo_manager._db

@contextmanager
def mongo_session():
    """
    Context manager for MongoDB operations
    
    Use Case: Transactions, cleanup
    """
    try:
        yield get_db()
    except Exception as e:
        logger.error(f"MongoDB session error: {e}")
        raise

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