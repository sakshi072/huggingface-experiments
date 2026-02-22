"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class SearchRequest(BaseModel):
    """Request schema for querying the Vector Storage and Retrieval system."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Question to ask the Vector Storage and Retrieval system",
        examples=["What is Machine Learning?"]
    )

    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of chunks to retrieve"
    )

    domain_name: Optional[str] = Field(None, description="Document domain to search")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is machine learning?",
                "top_k": 3,
                "domain": "general"
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
    similarity: float = Field(..., ge=0.0, le=1.0, description="Similarity score")
    file_url: Optional[str] = Field(None, description="Download link")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "Machine learning is a subset of AI...",
                "similarity": 0.89,
                "file_url": "http://localhost:9000/documents/2026/01/10/abc_ml_guide.pdf?X-Amz-..."
            }
        }


class SearchResponse(BaseModel):
    """Response schema for Vector Storage and Retrieval System query."""

    sources: List[SourceReference] = Field(..., description="Source chunks used")
    query_time: float = Field(..., description="Query processing time in seconds")
    search_id: Optional[str] = Field(default=None, description="Search UUID")

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
                "query_time": 1.23,
                "seach_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class SearchResult(BaseModel):
    """Every query search result for analysis."""

    search_id: str = Field(..., description="Query search id")
    query_text: str = Field(..., description="Query searched")
    chunks: List[Dict] = Field(..., description="List of result chunks with similarity")
    embedding_time_ms: float = Field(..., description="Embedding time in ms")
    search_time_ms: float = Field(..., description="DB search time in ms")
    total_processing_time: float = Field(..., description="Total processing time in ms")
    created_at: str = Field(..., description="Upload timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "search_id": "123e4567-e89b-12d3-a456-426614174000",
                "query_text": "What is machine learning",
                "chunks": [
                    {
                        "chunk_text": "Machine learning is a subset of AI...",
                        "similarity": 0.89
                    }
                ],
                "embedding_time_ms": 1.23,
                "search_time_ms": 1.24,
                "total_processing_time": 1.67,
                "created_at": "2026-01-09T15:30:00"
            }
        }

class SearchHistory(BaseModel):
    """Response schema for Search analytics all query searches."""

    search_history: List[SearchResult] = Field(..., description="list of all the search results")

    class Config:
        json_schema_extra = {
            "example": {
                "search_history" : [
                    {
                        "search_id": "123e4567-e89b-12d3-a456-426614174000",
                        "query_text": "What is machine learning",
                        "chunks": [
                            {
                                "chunk_text": "Machine learning is a subset of AI...",
                                "similarity": 0.89
                            }
                        ],
                        "embedding_time_ms": 1.23,
                        "search_time_ms": 1.24,
                        "total_processing_time": 1.67,
                        "created_at": "2026-01-09T15:30:00"
                    }
                ],
            }
        }
 
class UploadStatus(str, Enum):
    """Status of individual file upload"""
    SUCCESS = "success"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"

class FileUploadResult(BaseModel):
    """Response schema for document ingestion."""

    message: Optional[str] = Field(None, description="Status message")
    filename: str = Field(..., description="Uploaded filename")
    status: UploadStatus = Field(..., description="Status of uploaded file")
    document_id: Optional[str] = Field(None, description="Document UUID")
    chunks_created: Optional[int] = Field(None, description="Number of chunks created")
    processing_time: float = Field(..., description="Processing time in seconds")
    error_message: Optional[str] = Field(None, description="Error message (if failed)")
    metadata: Optional[dict] = Field(None, description="Document metadata (pages, format, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Document ingested successfully",
                "filename": "ml_basics.txt",
                "status": "success",
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "chunks_created": 15,
                "processing_time": 3.2,
                "error_message": None,
                "metadata": {
                    "pages": 5,
                    "format": "pdf",
                    "file_size": 204800
                },
                
            }
        }

class BatchUploadResponse(BaseModel):
    """Response for batch file upload"""
    message: str = Field(..., description="Overall status message")
    total_files: int = Field(..., description="Total files submitted")
    successful: int = Field(..., description="Number of successful uploads")
    failed: int = Field(..., description="Number of failed uploads")
    duplicates: int = Field(..., description="Number of duplicate files detected")
    total_processing_time: float = Field(..., description="Total time in seconds")
    results: List[FileUploadResult] = Field(..., description="Individual file results")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Batch upload completed",
                "total_files": 5,
                "successful": 3,
                "failed": 1,
                "duplicates": 1,
                "total_processing_time": 15.7,
                "results": [
                    {
                        "filename": "doc1.pdf",
                        "status": "success",
                        "document_id": "123e4567-e89b-12d3-a456-426614174000",
                        "chunks_created": 42,
                        "processing_time": 3.2,
                        "error_message": None
                    },
                    {
                        "filename": "doc2.pdf",
                        "status": "duplicate",
                        "document_id": "existing-id",
                        "chunks_created": 30,
                        "processing_time": 0.1,
                        "error_message": None
                    },
                    {
                        "filename": "doc3.txt",
                        "status": "failed",
                        "document_id": None,
                        "chunks_created": None,
                        "processing_time": 1.5,
                        "error_message": "Unsupported file type"
                    }
                ]
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
                    "vector_storage_and_retrieval System": "ok",
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

    error: int = Field(..., description="Error Code")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[Dict[str, Any]] = Field(None, description="Additional error context (request_id, error_code, etc.")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "error": 404,
                    "message": "Document not found",
                    "detail": {
                        "request_id": "gen-a1b2c3d4",
                        "error_code": "DOCUMENT_NOT_FOUND",
                        "document_id": "123e4567-e89b-12d3-a456-426614174000"
                    }
                },
                {
                    "error": 400,
                    "message": "File type '.exe' is not supported",
                    "detail": {
                        "request_id": "gen-xyz789",
                        "error_code": "UNSUPPORTED_FILE_TYPE",
                        "received_type": "exe",
                        "supported_types": ["pdf", "docx", "txt", "md"]
                    }
                },
                {
                    "error": 422,
                    "message": "Request validation failed",
                    "detail": {
                        "request_id": "gen-abc123",
                        "error_code": "VALIDATION_ERROR",
                        "errors": [
                            {
                                "field": "query",
                                "message": "field required",
                                "type": "value_error.missing"
                            }
                        ]
                    }
                },
                {
                    "error": 500,
                    "message": "A database error occurred. Please try again later.",
                    "detail": {
                        "request_id": "gen-def456",
                        "error_code": "DATABASE_ERROR"
                    }
                }
            ]
        }
