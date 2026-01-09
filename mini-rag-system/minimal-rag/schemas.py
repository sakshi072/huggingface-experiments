"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional

# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class QueryRequest(BaseModel):
    """Request schema for querying the RAG system."""

    query:str = Field(
        ...,
        min_lenght = 3,
        max_length = 500,
        description = "Question to as the RAG system",
        examples = ["What is Machine Learnign?"]
    )

    top_k: int = Field(
        default = 3,
        ge = 1,
        le = 10,
        description="Number of chunks to retrieve"
    )

    class Config:
        json_schema_extra = {
            "example":{
                "query": "What is machine learning?",
                "top_k": 3
            }
        }

class IngestRequest(BaseModel):
    pass
# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class SourceReference(BaseModel):
    """Source chunk reference in query response."""

    text:str = Field(..., description="Retrieved text chunk")
    source:str = Field(..., description="Source filename")
    chunk_index:int = Field(..., description="Chunk index in document")
    similarity:float = Field(..., ge=0.0, le=1.0, description="Similarity score")

    class Config:
        json_schema_extra = {
            "example":{
                "text": "Machine learning is a subset of AI...",
                "source": "ml_basics.txt",
                "chunk_index": 0,
                "similarity": 0.89
            }
        }

class QueryResponse(BaseModel):
    """Response schema for RAG query."""

    answer:str = Field(..., description="Generate Answer")
    sources: List[SourceReference] = Field(..., description="Source chunks used")
    query_time: float = Field(..., description="Query processing time in seconds")

    class Config:
        json_schema_extra = {
            "example":{
                "answer": "Machine learning is a subset of artificial intelligence...",
                "sources": [
                    {
                        "text": "Machine learning enables systems to learn...",
                        "source": "ml_basics.txt",
                        "chunk_index": 0,
                        "similarity": 0.89
                    }
                ],
                "query_time": 1.23
            }
        }


class IngestResponse(BaseModel):
    """Response schema for document ingestion."""

    message: str = Field(..., description="Status message")
    filename: str = Field(..., description="Uploaded filename")
    chunks_created: int = Field(..., description="Number of chunks create")
    processing_time: float = Field(..., description="Processing time in secodns")

    class Config:
        json_schema_extra ={
            "example":{
                "message": "Document ingested successfully",
                "filename": "ml_basics.txt",
                "chunks_created": 15,
                "processing_time": 3.2
            }
        }

class HealthResponse(BaseModel):
    """Health check response."""

    status:str = Field(..., description="Overall status")
    components: dict = Field(..., description="Component statuses")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "components": {
                    "vector_db": "ok",
                    "llm": "ok"
                }
            }
        }

class StatResponse(BaseModel):
    """System statistics response."""

    total_chunks: int = Field(..., description="Total chunks in databases")
    collection_name: str = Field(..., description="Vector collection name")

    class Config:
        json_schema_extra = {
            "example": {
                "total_chunks": 127,
                "collection_name": "documents"
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
