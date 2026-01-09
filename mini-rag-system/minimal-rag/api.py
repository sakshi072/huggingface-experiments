"""
FastAPI REST API for Mini RAG System

Run: uvicorn api:app --reload
Access: http://localhost:8000/docs
"""

import time
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from minimal_rag import MinimalRAG
from schemas import (
    QueryRequest,
    QueryResponse,
    IngestResponse,
    HealthResponse,
    StatResponse,
    ErrorResponse,
    SourceReference
)

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Mini RAG API",
    description="Production-grade RAG system with document upload and querying",
    version = "0.3.0",
    docs_url = "/docs",
    redoc_url = "/redoc"
)

# Add CORS middleware (allows web apps to call this API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Global RAG Instance (initialized on startup)
# ============================================================================

rag: Optional[MinimalRAG] = None

@app.on_event("startup")
async def startup_event():
    """Initialize RAG system on startup."""
    global rag
    print("Starting Mini RAG API ....")

    try:
        rag = MinimalRAG()
        print("RAG system initialized successfully")
    except Exception as e:
        print(f"Failed to initialize RAG: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("Shutting down Mini RAG API ...")

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Mini RAG API",
        "version": "0.3.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "POST /ingest": "Upload document",
            "POST /query": "Ask questions",
            "GET /health": "Health check",
            "GET /stats": "System statistics"
        }
    }

@app.get("/health", response_model = HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    
    Returns system status and component health.
    """
    if rag is None:
        raise HTTPException(
            status_code = 503,
            details = "RAG system not initialized"
        )
    
    components = {
        "vector_db": "ok",
        "llm": "ok"
    }

    return HealthResponse(
        status = "healthy",
        components = components
    )

@app.get("/stats", response_model=StatResponse, tags=["System"])
async def get_stats():
    """
    Health check endpoint.
    
    Returns system status and component health.
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    stats = rag.get_stats()

    return StatResponse(
        total_chunks=stats["total_chunks"],
        collection_name=stats["collection"]
    )
    
@app.post("/ingest", response_model=IngestResponse, tags=["Documents"])
async def ingest_document(file: UploadFile = File(...)):
    """
    Upload and ingest a document.
    
    Supported formats: .txt, .md, .pdf (future)
    
    The document will be:
    1. Saved temporarily
    2. Chunked into smaller pieces
    3. Embedded into vectors
    4. Stored in ChromaDB
    
    Returns processing statistics.
    """

    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    # Validate file type
    allowed_extensions = {".txt", ".md"}
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_extensions}"
        )
    
    # Save uploaded file temporarily
    try:
        start_time = time.time()

        with tempfile.NamedTemporaryFile(
            mode='wb',
            suffix = file_ext,
            delete=False
        ) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name
        
        # Ingest the file
        chunks_created = rag.ingest_file(temp_path)

        # Clean up temp file
        Path(temp_path).unlink()

        processing_time = time.time() - start_time

        return IngestResponse(
            message = "Document ingested successfully",
            filename = file.filename,
            chunks_created=chunks_created,
            processing_time=processing_time
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(e)}"
        )

@app.post('/query', response_model=QueryResponse, tags=["Query"])
async def query_documets(request: QueryRequest):
    """
    Query the RAG system.
    
    Send a question and get an AI-generated answer based on your documents.
    
    The system will:
    1. Convert your question to embeddings
    2. Find similar document chunks
    3. Generate answer using LLM (if enabled)
    4. Return answer with source citations
    
    Parameters:
    - query: Your question (3-500 characters)
    - top_k: Number of document chunks to retrieve (1-10)
    
    Returns answer with sources and processing time.
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    try: 
        start_time = time.time()

        result = rag.query(
            question=request.query,
            top_k=request.top_k
        )

        query_time = time.time() - start_time

        # Format sources
        sources = [
            SourceReference(
                text = source["chunk"],
                source = source["source"],
                chunk_index= source["chunk_index"],
                similarity=round(source["similarity"], 3)
            )
            for source in result["sources"]
        ]

        return QueryResponse(
            answer=result["answer"],
            sources=sources,
            query_time=query_time
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )

# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with consistent format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            detail = None
        ).dict()
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc)
        ).dict()
    )

# ============================================================================
# Run with: uvicorn api:app --reload --host 0.0.0.0 --port 8000
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)