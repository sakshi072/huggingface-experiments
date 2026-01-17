"""
Health and system status endpoints
"""
from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_rag
from app.schemas import HealthResponse, StatResponse

router = APIRouter(prefix="", tags=["System"])


@router.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Mini RAG API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "POST /ingest": "Upload document (PDF, DOCX, TXT, MD)",
            "POST /search": "Search top k similar chunks for user query",
            "GET /documents": "List all documents",
            "GET /documents/{id}": "Get document details",
            "DELETE /documents/{id}": "Delete document",
            "GET /health": "Health check",
            "GET /stats": "System statistics"
        },
        "features": [
            "PostgreSQL vector database (persistent storage)",
            "MinIO object storage (original files preserved)",
            "Document citations",
            "Metadata tracking and versioning",
            "Production-grade architecture"
        ]
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Checks status of:
    - RAG system
    - PostgreSQL database
    - MinIO storage
    """
    rag = get_rag()
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )

    components = {
        "rag": "ok",
        "postgres": "ok",
        "minio": "ok"
    }

    return HealthResponse(
        status="healthy",
        components=components
    )


@router.get("/stats", response_model=StatResponse)
async def get_stats():
    """
    Get system statistics.

    Returns:
    - Total documents
    - Total chunks
    - Documents by status (processing, completed, failed)
    """
    rag = get_rag()
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )

    try:
        stats = await rag.get_stats()

        return StatResponse(
            total_documents=stats["total_documents"],
            total_chunks=stats["total_chunks"],
            status_breakdown=stats["status_breakdown"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting stats: {str(e)}"
        )
