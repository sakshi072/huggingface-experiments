"""
FastAPI REST API for Vector Storage and Retrieval System

Run: uvicorn app.main:app --reload
Access: http://localhost:8001/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from app.db import startup_database, shutdown_database
from app.services import KnowledgeBase
from app.utils.document_storage import storage_service
from app.api.dependencies import set_vectore_storage_retrieval
from app.api.routes import documents, search, health
from fastapi.security import HTTPBearer
from app.core.exception_handler import register_exception_handlers
from app.core.middleware import TracingMiddleware
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)

# ============================================================================
# Lifespan Context Manager
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    # Startup
    logger.info("Starting Vector Storage and Retrieval API...")

    try:
        # Initialize database
        await startup_database()

        # Initialize minIO
        storage_service._ensure_bucket_exists()
        logger.info("MinIO Bucket verified on startup.")

        # Initialize Vector Storage and Retrieval system
        vector_storage_retrieval = KnowledgeBase()
        set_vectore_storage_retrieval(vector_storage_retrieval)
        logger.info("Vector Storage and Retrieval system initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize Vector Storage and Retrieval system: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Vector Storage and Retrieval API...")
    await shutdown_database()
    logger.info("Shutdown complete")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Vector Storage and Retrieval API",
    description="Semantic search Vector Storage and Retrieval system with document upload and querying and OAuth 2.0 authentication",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

security = HTTPBearer()

app.add_middleware(TracingMiddleware)
register_exception_handlers(app)

# Include routers
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(search.router)
