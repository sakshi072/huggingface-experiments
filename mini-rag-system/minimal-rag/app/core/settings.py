"""
Centralized configuration using Pydantic Settings

Benefits:
1. Type-safe configuration (autocomplete + validation)
2. Automatic .env loading (no manual load_dotenv())
3. Validation at startup (fail fast with clear errors)
4. Single source of truth for all config
5. Environment-aware (dev/staging/prod)
"""

from functools import lru_cache
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSettings(BaseSettings):
    """
    PostgreSQL database configuration
    Separate class for logical grouping
    """

    # Required fields (will raise error if missing)
    db:str = Field(..., description="Database name")
    user:str = Field(..., description="Database user")
    password:str = Field(..., description="Database password")

    # Optional with defaults
    host:str = Field(default="localhost", description="Database host")
    port:int = Field(default=5432, description="Database port")

    # Computed Property
    @property
    def url(self) -> str:
        """
        Build database url dynamically
        """
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="POSTGRES_",
        case_sensitive=False,
        extra="ignore"
    )

class MinIOSettings(BaseSettings):
    """MinIo object storage configuration"""

    endpoint:str = Field(default="localhost:9000")
    root_user:str = Field(default="minioadmin")
    root_password:str = Field(default="minioadmin")
    bucket:str = Field(default="document-storage")
    secure:bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MINIO_",
        case_sensitive=False,
        extra="ignore"
    )

class MCPTLSSettings(BaseSettings):
    """Langchain Mcp server TLS"""

    tls_ca_cert:str = Field(default="/etc/retrieval/server-certs/ca.crt")
    tls_client_cert:str = Field(default="/etc/retrieval/server-certs/tls.crt")
    tls_client_key:str = Field(default="/etc/retrieval/server-certs/tls.key")
    timeout:float = 30.0
    retries:int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MCP_",
        case_sensitive=False,
        extra="ignore"
    )

class Auth0Settings(BaseSettings):
    """
    Auth0 JWT validation configuration
    
    Why validate domain?
    - Ensures it's a valid Auth0 domain format
    - Catches typos at startup, not at runtime
    """

    domain:str = Field(..., description="Auth0 tenant domain")
    audience:str = Field(..., description="API identifier")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v:str) -> str:
        """
        Validate Auth0 domain format
        
        Example validation:
        - Valid: "dev-abc123.us.auth0.com"
        - Invalid: "https://dev-abc123.us.auth0.com" (no protocol)
        """
        if v.startswith("http://") or v.startswith("htpps://"):
            raise ValueError("AUTH0_DOMAIN should not include protocol")
        return v
    
    @property
    def issuer(self) -> str:
        """Auto-computed issuer URL"""
        return f"https://{self.domain}/"
    
    @property
    def jwks_url(self) -> str:
        """Auto-computed JWKS URL"""
        return f"https://{self.domain}/.well-known/jwks.json"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AUTH0_",
        case_sensitive=False,
        extra="ignore"
    )

class EmbeddingSettings(BaseSettings):
    """
    Embedding and chunking configuration
    
    Why validate ranges?
    - chunk_size must be reasonable (too small = poor context, too large = slow)
    - overlap must be less than chunk_size
    """

    model:str = Field(default='sentence-transformers/all-MiniLM-L6-v2', description="Embedding model name")
    chunking_strategy:Literal["recursive_split", "semantic_chunking", "hybrid_chunking"] = Field(
        default="recursive_split",
        description="Chunking strategy to use"
    )
    chunk_size:int = Field(
        default=512,
        ge=100,
        le=2048,
        description="Chunk size in characters"
    )
    chunk_overlap:int = Field(
        default=50,
        ge=0,
        description="Overlap between chunks"
    )
    
    @field_validator("chunk_overlap")
    @classmethod
    def validate_overlap(cls, v:int, info) -> int:
        """Ensure overlap is less than chunk size"""
        chunk_size = info.data.get("chunk_size", 512)
        if v>=chunk_size:
            raise ValueError(f"chunk_overlap ({v}) must be < chunk size ({chunk_size})")
        return v
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore"
    )

class ReRankSettings(BaseSettings):
    """
    Reranking configuration
    """
    strategy: Literal["similarity", "quality", "hybrid", "mmr", "combined"] = Field(
        default="combined"
    )
    quality_weight:float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Quality score weight (0-1)"
    )
    alpha: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Dense vs sparse weight (0-1)"
    )
    lambda_param: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="MMR diversity parameter (0-1)"
    )
    max_chunks_per_doc: int = Field(
        default=2,
        ge=1,
        description="Max chunks per document"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RERANK_",
        case_sensitive=False,
        extra="ignore"
    )

class FeatureFlagSettings(BaseSettings):
    """
    Feature flags for A/B testing
    """
    semantic_chunking: bool = Field(
        default=False,
        description="Use semantic chunking"
    )
    
    reranking: bool = Field(
        default=False,
        description="Enable reranking"
    )
    
    rerank_multiplier: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Fetch multiplier for reranking"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FEATURE_",
        case_sensitive=False,
        extra="ignore"
    )

class Settings(BaseSettings):
    """
    Main settings class - aggregates all configuration
    """
    env:Literal["development", "staging", "production"] = Field(
        default="development"
    )
    debug:bool = Field(default=True)

    # Nested Settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    auth0: Auth0Settings = Field(default_factory=Auth0Settings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rerank:ReRankSettings = Field(default_factory=ReRankSettings)
    featureflags:FeatureFlagSettings = Field(default_factory=FeatureFlagSettings)
    mcptls: MCPTLSSettings = Field(default_factory=MCPTLSSettings)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="_",
        extra="ignore",
        case_sensitive=False
    )

@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance
    
    - Settings only loaded once (performance)
    - Same instance reused everywhere (consistency)
    - Can be easily mocked in tests
    """
    return Settings()

settings = get_settings()