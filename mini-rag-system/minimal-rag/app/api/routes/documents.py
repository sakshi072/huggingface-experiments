"""
Document management endpoints
"""
import time
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.api.dependencies import get_rag
from app.schemas import IngestResponse, DocumentMetadata, DocumentListResponse

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", response_model=IngestResponse)
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
    rag = get_rag()
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

    try:
        start_time = time.time()

        file_data = await file.read()

        # Ingest document
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
            message=message,
            document_id=str(document_id),
            filename=file.filename,
            chunks_created=doc["chunk_count"],
            processing_time=round(processing_time, 2),
            metadata=doc_metadata,
            status=doc["status"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(e)}"
        )


@router.get("", response_model=DocumentListResponse)
async def list_documents(limit: int = 10, skip: int = 0):
    """
    List all documents.

    Parameters:
    - limit: Max documents to return (default 10)
    - skip: Number of documents to skip (for pagination)

    Returns list of documents with:
    - Document ID
    - Filename
    - Status (processing, completed, failed)
    - Chunk count
    - Upload timestamp
    """
    rag = get_rag()
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized"
        )

    try:
        docs = await rag.list_documents(limit=limit + skip)

        docs = docs[skip:skip + limit]

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
            total=len(docs)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing documents: {str(e)}"
        )


@router.get("/{document_id}")
async def get_document(document_id: str):
    """
    Get detailed document information.

    Returns:
    - Document metadata
    - File information
    - Processing status
    - Chunk count
    - Extracted metadata (pages, author, etc.)
    """
    rag = get_rag()
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


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """
    Delete a document.

    This will:
    1. Delete document from PostgreSQL (cascades to chunks)
    2. Delete original file from MinIO
    3. Remove all embeddings

    Returns success status.
    """
    rag = get_rag()
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
