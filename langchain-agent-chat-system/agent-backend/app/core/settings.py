from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import HttpUrl

class Settings(BaseSettings):
    #Postgres Settings
    POSTGRES_PASSWORD:str
    POSTGRES_URI:str

    #Mongo
    MONGO_URI:str
    MONGO_DB_NAME:str
    MONGO_MAX_POOL_SIZE:int = 50
    MONGO_MIN_POOL_SIZE:int = 10

    #Auth0 Config for UI
    UI_AUTH0_DOMAIN:str
    UI_AUTH0_AUDIENCE:str
    UI_AUTH0_ALGORITHMS: str = "RS256"

    @property
    def auth0_issuer(self) -> str:
        """Construct issuer URL from domain"""
        return f"https://{self.UI_AUTH0_DOMAIN}/"
    @property
    def auth0_jwks_url(self) -> str:
        return f"https://{self.UI_AUTH0_DOMAIN}/.well-known/jwks.json"
    @property
    def auth0_alogirthm_list(self) -> list[str]:
        return [alg.strip() for alg in self.UI_AUTH0_ALGORITHMS.split(",")]

    #Auth0 config for MCP RAG server
    RETRIEVAL_MCP_CLIENT_ID:str
    RETRIEVAL_MCP_CLIENT_SECRET:str
    RETRIEVAL_MCP_AUDIENCE:str
    RETRIEVAL_MCP_DOMAIN:str

    @property
    def retrieval_mcp_token_url(self) -> list[str]:
        return f"https://{self.RETRIEVAL_MCP_DOMAIN}/oauth/token"
    
    
    #HF, Tavily
    HF_TOKEN:str
    HF_MODEL_ID:str = "meta-llama/Llama-3.2-3B-Instruct"
    HF_API_BASE_URL: HttpUrl = "https://router.huggingface.co/v1/"
    HF_MAX_TOKEN:int = 1024
    HF_TEMPERATURE:float = 0.1
    TAVILY_API_KEY:str

    #Langfuse
    LANGFUSE_SECRET_KEY:str
    LANGFUSE_PUBLIC_KEY:str
    LANGFUSE_BASE_URL: HttpUrl

    #Postgres Langgraph
    POSTGRES_PASSWORD:str
    POSTGRES_URI:str

    #Ollama 
    OLLAMA_BASE_URL:str = "http://localhost:11434"
    OLLAMA_PRIMARY_MODEL:str = "qwen3:8b"
    OLLAMA_FALLBACK_MODEL:str = "llama3.1:8b"
    OLLAMA_TEMPERATURE:float = "0.2"

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()