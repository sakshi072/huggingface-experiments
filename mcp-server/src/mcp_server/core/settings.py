from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import HttpUrl

class Settings(BaseSettings):
    # Server settings
    ENV: str = "development"
    PORT: int = 8002

    # RAG Microservice Settings
    RETRIEVAL_BASE_URL: HttpUrl
    RETRIEVAL_TIMEOUT: float = 30.0

    # Auth0 Settings
    AUTH0_DOMAIN:str
    AUTH0_AUDIENCE:str
    AUTH0_CLIENT_SECRET: str
    AUTH0_CLIENT_ID: str

    @property
    def auth0_token_url(self) -> str:
        """Auto-computed JWKS URL"""
        return f"https://{self.AUTH0_DOMAIN}/oauth/token"

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

    RETRIEVAL_TLS_CA_CERT: str = "/etc/retrieval/client-certs/ca.crt"
    RETRIEVAL_TLS_CLIENT_CERT:str = "/etc/retrieval/client-certs/tls.crt"
    RETRIEVAL_TLS_CLIENT_KEY: str = "/etc/retrieval/client-certs/tls.key"
    retrieval_timeout: float = 30.0
    retrieval_retires: int = 3

settings = Settings()