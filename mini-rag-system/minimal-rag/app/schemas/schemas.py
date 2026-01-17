"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class SearchRequest(BaseModel):
    """Request schema for querying the RAG system."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Question to ask the RAG system",
        examples=["What is Machine Learning?"]
    )

    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of chunks to retrieve"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is machine learning?",
                "top_k": 3
            }
        }


class IngestRequest(BaseModel):
    """Request schema for document ingestion (placeholder for metadata)."""
    pass


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class SourceReference(BaseModel):
    """Source chunk reference in query response."""

    text: str = Field(..., description="Retrieved text chunk")
    filename: str = Field(..., description="Source filename")
    similarity: float = Field(..., ge=0.0, le=1.0, description="Similarity score")
    file_url: Optional[str] = Field(None, description="Download link")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "Machine learning is a subset of AI...",
                "filename": "ml_basics.txt",
                "similarity": 0.89,
                "file_url": "http://localhost:9000/documents/2026/01/10/abc_ml_guide.pdf?X-Amz-..."
            }
        }


class SearchResponse(BaseModel):
    """Response schema for RAG query."""

    sources: List[SourceReference] = Field(..., description="Source chunks used")
    query_time: float = Field(..., description="Query processing time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "sources": [
                    {
                        "text": "Machine learning enables systems to learn...",
                        "source": "ml_basics.txt",
                        "similarity": 0.89,
                        "file_url": "http://localhost:9000/documents/2026/01/10/abc_ml_guide.pdf?X-Amz-..."
                    }
                ],
                "query_time": 1.23
            }
        }


class IngestResponse(BaseModel):
    """Response schema for document ingestion."""

    message: str = Field(..., description="Status message")
    document_id: str = Field(..., description="Document UUID")
    filename: str = Field(..., description="Uploaded filename")
    chunks_created: int = Field(..., description="Number of chunks created")
    processing_time: float = Field(..., description="Processing time in seconds")
    metadata: Optional[dict] = Field(None, description="Document metadata (pages, format, etc.)")
    status: str = Field(..., description="Status of uploaded file")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Document ingested successfully",
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "filename": "ml_basics.txt",
                "chunks_created": 15,
                "processing_time": 3.2,
                "metadata": {
                    "pages": 5,
                    "format": "pdf",
                    "file_size": 204800
                },
                "status": "processing"
            }
        }


class DocumentMetadata(BaseModel):
    """Document metadata schema"""

    id: str = Field(..., description="Document UUID")
    filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="Processing status")
    chunk_count: int = Field(..., description="Number of chunks")
    created_at: str = Field(..., description="Upload timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "filename": "report.pdf",
                "status": "completed",
                "chunk_count": 42,
                "created_at": "2026-01-09T15:30:00"
            }
        }


class DocumentListResponse(BaseModel):
    """Response schema for listing documents"""

    documents: List[DocumentMetadata] = Field(..., description="List of documents")
    total: int = Field(..., description="Total document count")

    class Config:
        json_schema_extra = {
            "example": {
                "documents": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "filename": "report.pdf",
                        "status": "completed",
                        "chunk_count": 42,
                        "created_at": "2026-01-09T15:30:00"
                    }
                ],
                "total": 1
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Overall status")
    components: dict = Field(..., description="Component statuses")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "components": {
                    "rag": "ok",
                    "postgres": "ok",
                    "minio": "ok",
                    "llm": "ok"
                }
            }
        }


class StatResponse(BaseModel):
    """Statistics response"""

    total_documents: int = Field(..., description="Total documents in system")
    total_chunks: int = Field(..., description="Total chunks in system")
    status_breakdown: Dict[str, int] = Field(
        ...,
        description="Documents by status"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_documents": 42,
                "total_chunks": 1337,
                "status_breakdown": {
                    "completed": 40,
                    "processing": 1,
                    "failed": 1
                }
            }
        }


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str = Field(..., description="Error Message")
    detail: Optional[str] = Field(None, description="Detailed error information")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Invalid file type",
                "detail": "Only .txt, .pdf, .md files are supported"
            }
        }
