import httpx
from mcp_server.core.settings import settings
from mcp_server.middleware.auth import get_token
from typing import Annotated, Optional
from pydantic import Field
import ssl
import os
import logging
from enum import Enum
import json

logger = logging.getLogger(__name__)
_SSL_CONTEXT: Optional[ssl.SSLContext] = None

class DomainOptions(str, Enum):
    FINANCE = "finance"
    SYSTEM_DESIGN = "system-design"
    GENERAL = "general"
    HEALTHCARE = "healthcare"
    MEDICAL = "medical"
    LEGAL = "legal"
    MACHINE_LEARNING = "machine-learning"
    TEST = "test"

def _create_ssl_context() -> ssl.SSLContext:
    """Create ssl context for mTLS"""
    try:
        for path, name in [
            (settings.RETRIEVAL_TLS_CA_CERT, "CA certificate"),
            (settings.RETRIEVAL_TLS_CLIENT_CERT, "Client certificate"),
            (settings.RETRIEVAL_TLS_CLIENT_KEY, "Client Key")
        ]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"{name} not found at {path}")
            logger.info(f"Found {name}: {path}")

        context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=settings.RETRIEVAL_TLS_CA_CERT
        )

        context.load_cert_chain(
            certfile=settings.RETRIEVAL_TLS_CLIENT_CERT,
            keyfile=settings.RETRIEVAL_TLS_CLIENT_KEY
        )

        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        # Disable weak ciphers
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')

        logger.info("SSL context created successfully")
        return context
    
    except FileNotFoundError as e:
            logger.error(f"Certificate file missing: {e}")
            raise
    except Exception as e:
        logger.error(f"Failed to create SSL context: {e}")
        raise 

def _get_ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = _create_ssl_context()
    return _SSL_CONTEXT

async def search_knowledge_base(
    query: Annotated[str, Field(description="The search query string", min_length=1)],
    domain_name: DomainOptions,
    top_k: Annotated[
        int, 
        Field(
            default=3, 
            gt=0, 
            le=10, 
            description="Number of results to return",
            serialization_alias="top_k",  # Force the name in output
            validation_alias="top_k"     # Force the name in input
        )
    ] = 3,
) -> str:
    """Semantic search across all documents available."""
    token = await get_token()
    ssl_context = _get_ssl_context()

    target_url = f"{settings.RETRIEVAL_BASE_URL}/search"
    logger.info(f"🚀 RAG Request: {target_url}")
    logger.info(query, domain_name, top_k)

    logger.info("SECRET_VALUE:'skjdncjdscbdjcbdjfcnjdfcj'")

    async with httpx.AsyncClient(base_url=str(settings.RETRIEVAL_BASE_URL), timeout=30.0, verify=ssl_context) as client:
        response = await client.post(
            "/search",
            json={"query": query, "top_k": top_k or 3, "domain_name": domain_name},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.text
