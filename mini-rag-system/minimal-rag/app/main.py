"""
FastAPI REST API for Vector Storage and Retrieval System

Run: uvicorn app.main:app --reload
Access: http://localhost:8001/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import startup_database, shutdown_database
from app.services import KnowledgeBase, storage_service
from app.schemas import ErrorResponse
from app.api.dependencies import set_vectore_storage_retrieval
from app.api.routes import documents, search, health
import logging

logger = logging.getLogger(__name__)

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

# Include routers
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(search.router)


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc)
        ).model_dump()
    )