"""
FastAPI REST API for Mini RAG System

Run: uvicorn app.main:app --reload
Access: http://localhost:8001/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import startup_database, shutdown_database
from app.services import KnowledgeBase
from app.schemas import ErrorResponse
from app.api.dependencies import set_rag
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
    logger.info("Starting Mini RAG API...")

    try:
        # Initialize database
        await startup_database()

        # Initialize RAG system
        rag = KnowledgeBase()
        set_rag(rag)
        logger.info("RAG system initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize RAG: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Mini RAG API...")
    await shutdown_database()
    logger.info("Shutdown complete")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Mini RAG API",
    description="Semantic search RAG system with document upload and querying and OAuth 2.0 authentication",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# ============================================================================
# Run with: uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
