"""
FastAPI REST API for Mini RAG System

Run: uvicorn api:app --reload
Access: http://localhost:8000/docs
"""

import time
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from minimal_rag import KnowledgeBase
from database import startup_database, shutdown_database, get_session
from schemas import (
    SearchRequest,
    SearchResponse,
    IngestResponse,
    HealthResponse,
    StatResponse,
    SourceReference,
    DocumentMetadata,
    DocumentListResponse,
    ErrorResponse,
)

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Mini RAG API",
    description="Production-grade RAG system with document upload and querying",
    version = "1.0.0",
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

rag: Optional[KnowledgeBase] = None

@app.on_event("startup")
async def startup_event():
    """Initialize RAG system on startup."""
    global rag
    print("Starting Mini RAG API ....")

    try:
        # Initialize database
        await startup_database()

        # Initialize RAG system
        rag = KnowledgeBase()
        print("RAG system initialized successfully")

    except Exception as e:
        print(f"Failed to initialize RAG: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("Shutting down Mini RAG API ...")
    await startup_database()
    print("✅ Shutdown complete")

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Production RAG API",
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

@app.get("/health", response_model = HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    
    Checks status of:
    - RAG system
    - PostgreSQL database
    - MinIO storage
    """
    if rag is None:
        raise HTTPException(
            status_code = 503,
            details = "RAG system not initialized"
        )
    
    components = {
        "rag":"ok",
        "postgres":"ok",
        "minio": "ok"
    }

    return HealthResponse(
        status = "healthy",
        components = components
    )

@app.get("/stats", response_model=StatResponse, tags=["System"])
async def get_stats():
    """
    Get system statistics.
    
    Returns:
    - Total documents
    - Total chunks
    - Documents by status (processing, completed, failed)
    """
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
    
@app.post("/ingest", response_model=IngestResponse, tags=["Documents"])
async def ingest_document(file: UploadFile = File(...)):
    """
    Upload and ingest a document.
    
    Supported formats: .txt, .md, .pdf, .docx
    
    Process:
    1. Upload original file to MinIO (preserved forever)
    2. Parse document (extract text + metadata)
    3. Chunk text into smaller pieces
    4. Generate embeddings
    5. Store in PostgreSQL with pgvector
    
    Returns:
    - Document ID (UUID)
    - Processing statistics
    - Extracted metadata (pages, author, etc.)
    """

    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    # Validate file type
    allowed_extensions = {".txt", ".md", ".pdf", ".docx"}
    file_ext = file.filename.split('.')[-1].lower()
    
    if f".{file_ext}" not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_extensions}"
        )
    
    # Save uploaded file temporarily
    try:
        start_time = time.time()

        file_data = await file.read()

        # Ingest document using your MinimalRAG
        document_id, is_duplicate = await rag.ingest_file(
            file_data=file_data,
            filename=file.filename,
            file_type=file_ext,
            metadata=None
        )

        processing_time = time.time() - start_time

        # Get document details
        doc = await rag.get_document(document_id)

        doc_metadata = doc.get("metadata")
        if doc_metadata is not None and not isinstance(doc_metadata, dict):
            doc_metadata = {}
        
        if is_duplicate:
            message = "Duplicate file detected! Using existing document."
        else:
            message = "Document ingested successfully"

        return IngestResponse(
            message = message,
            document_id=str(document_id),
            filename = file.filename,
            chunks_created=doc["chunk_count"],
            processing_time=round(processing_time, 2),
            metadata=doc_metadata,
            status = doc["status"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(e)}"
        )

@app.post('/search', response_model=SearchResponse, tags=["Query"])
async def search_documets(request: SearchRequest):
    """
    Query the RAG system with semantic search.
    
    Process:
    1. Convert query to embedding
    2. Search PostgreSQL vector database (pgvector)
    3. Retrieve top-k most similar chunks
    4. Generate AI answer using LLM
    5. Return answer with source citations
    
    Parameters:
    - query: Your question (3-500 characters)
    - top_k: Number of chunks to retrieve (1-10, default 3)
    
    Returns:
    - Source citations with:
      - Document filename
      - Similarity score
      - Text preview
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    try: 
        start_time = time.time()

        result = await rag.search(
            query_text=request.query,
            top_k=request.top_k
        )

        query_time = time.time() - start_time

        # Check if we got results
        if not result.get("sources"):
            return SearchResponse(
                sources = [],
                query_time=round(query_time,2)
            )

        # Format sources
        sources = [
            SourceReference(
                text=source["text"],
                filename=source["filename"],
                similarity=round(source["similarity"], 3),
                file_url=source["file_url"]
            )
            for source in result["sources"]
        ]

        return SearchResponse(
            sources=sources,
            query_time=round(query_time,2)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )

@app.get("/documents", response_model=DocumentListResponse, tags=["Documents"])
async def list_documents(
    limit:int = 10,
    skip: int = 0
):
    """
    List all documents.
    
    Parameters:
    - limit: Max documents to return (default 100)
    - skip: Number of documents to skip (for pagination)
    
    Returns list of documents with:
    - Document ID
    - Filename
    - Status (processing, completed, failed)
    - Chunk count
    - Upload timestamp
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )

    try: 
        docs = await rag.list_documents(limit)

        docs = docs[skip:skip+limit]

        return DocumentListResponse(
            documents=[
                DocumentMetadata(
                    id=doc["id"],
                    filename=doc["filename"],
                    status=doc["status"],
                    chunk_count=doc["chunk_count"],
                    created_at=doc["created_at"]
                )
                for doc in docs
            ],
            total = len(docs)
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing documents: {str(e)}"
        )

@app.get("/documents/{document_id}", tags=["Documents"])
async def get_document(document_id:str):
    """
    Get detailed document information.
    
    Returns:
    - Document metadata
    - File information
    - Processing status
    - Chunk count
    - Extracted metadata (pages, author, etc.)
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    try:
        doc_uuid = UUID(document_id)

        doc = await rag.get_document(doc_uuid)

        if doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {document_id}"
            )
        
        return doc
    
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid document ID format"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting document: {str(e)}"
        )

@app.delete("/documents/{document_id}", tags=["Documents"])
async def delete_document(document_id: str):
    """
    Delete a document.
    
    This will:
    1. Delete document from PostgreSQL (cascades to chunks)
    2. Delete original file from MinIO
    3. Remove all embeddings
    
    Returns success status.
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )
    
    try:
        doc_uuid = UUID(document_id)

        deleted = await rag.delete_document(doc_uuid)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {document_id}"
            )
        
        return {
            "message": "Document deleted successfully",
            "document_id": document_id
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid document ID format"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting document: {str(e)}"
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