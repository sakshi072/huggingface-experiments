"""
Document management endpoints
"""
from uuid import UUID
import time
from fastapi import APIRouter, UploadFile, File, Depends
from app.core import require_scope, extract_scopes
from app.api.dependencies import get_vectore_storage_retrieval
from app.schemas import FileUploadResult, DocumentMetadata, DocumentListResponse, BatchUploadResponse, UploadStatus
from app.core.exceptions import (
    ServiceUnavailableException,
    InvalidParameterException,
    DocumentNotFound
)
import logging
from typing import List

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)

@router.post("", response_model=FileUploadResult)
async def ingest_document(
    file: UploadFile = File(...),
    token: dict = Depends(require_scope("search:knowledge"))
):
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
    vector_storage_retrieval = get_vectore_storage_retrieval()
    if vector_storage_retrieval is None:
        raise ServiceUnavailableException("KnowledgeBase", "Not initialized")
    
    client_id = token.get("sub", "unknown")
    scopes = extract_scopes(token)

    logger.info(
        f"Search request from client: {client_id}, scopes: {scopes}"
        )
    return await vector_storage_retrieval.process_single_file(
        file=file,
        domain_name="",
        file_number=1,
        total_files=1
    )

@router.post("/batch", response_model=BatchUploadResponse)
async def batch_ingest_document(
    files: List[UploadFile] = File(...,description="Multiple files to upload (max 20)"),
    domain: str = "general",
    token: dict = Depends(require_scope("search:knowledge"))
):
    """
    Upload and ingest MULTIPLE documents in one request.

    Features:
    - Upload up to 20 files simultaneously
    - Parallel processing (faster than sequential uploads)
    - Individual error handling (one failure doesn't stop others)
    - Duplicate detection per file
    - Detailed results for each file

    Supported formats: .txt, .md, .pdf, .docx

    Returns:
    - Summary statistics (total, successful, failed, duplicates)
    - Individual results for each file with document IDs
    - Total processing time
    """
    vector_storage_retrieval = get_vectore_storage_retrieval()
    if vector_storage_retrieval is None:
        raise ServiceUnavailableException("KnowledgeBase", "Not initialized")
    
    # Validate inputs
    MAX_FILES = 1
    if len(files) > MAX_FILES:
        raise InvalidParameterException("total_files", len(files), f"Maximum {MAX_FILES} files allowed per batch")
    
    client_id = token.get("sub", "unknown")
    scopes = extract_scopes(token)
    logger.info(
        f"Search request from client: {client_id}, scopes: {scopes}"
        )
    
    # Start timing
    batch_start_time = time.time()

    # Process files concurrently
    results = await vector_storage_retrieval.process_files_concurrently(
        files=files,
        domain=domain
    )

    # Calculate statistics
    total_processing_time = time.time() - batch_start_time

    stats = {
        "successful": sum(1 for r in results if r.status == UploadStatus.SUCCESS),
        "failed": sum(1 for r in results if r.status == UploadStatus.FAILED),
        "duplicates": sum(1 for r in results if r.status == UploadStatus.DUPLICATE)
    }

    # Generate summary message
    if stats["successful"] == len(files):
        message = f"All {len(files)} files uploaded successfully"
    elif stats["failed"] == len(files):
        message = f"All {len(files)} files failed to upload"
    else:
        message = (
            f"Batch upload completed: {stats['successful']} successful, "
            f"{stats['failed']} failed, {stats['duplicates']} duplicates"
        )
    
    logger.info(
        f"Batch upload complete: {stats['successful']}/{len(files)} successful "
        f"in {total_processing_time:.2f}s"
    )

    return BatchUploadResponse(
        message=message,
        total_files=len(files),
        successful=stats["successful"],
        failed=stats["failed"],
        duplicates=stats["duplicates"],
        total_processing_time=total_processing_time,
        results=results
    )

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    limit: int = 10, 
    skip: int = 0,
    token: dict = Depends(require_scope("read:documents"))
    ):
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
    vector_storage_retrieval = get_vectore_storage_retrieval()

    if vector_storage_retrieval is None:
        raise ServiceUnavailableException("KnowledgeBase", "Not initialized")

    client_id = token.get("sub", "unknown")
    scopes = extract_scopes(token)

    logger.info(
        f"Search request from client: {client_id}, scopes: {scopes}"
    )

    docs = await vector_storage_retrieval.list_documents(limit=limit + skip)

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


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    token: dict = Depends(require_scope("read:documents"))
    ):
    """
    Get detailed document information.

    Returns:
    - Document metadata
    - File information
    - Processing status
    - Chunk count
    - Extracted metadata (pages, author, etc.)
    """
    vector_storage_retrieval = get_vectore_storage_retrieval()
    if vector_storage_retrieval is None:
        raise ServiceUnavailableException("KnowledgeBase", "Not initialized")

    client_id = token.get("sub", "unknown")
    scopes = extract_scopes(token)

    logger.info(
        f"Search request from client: {client_id}, scopes: {scopes}"
        )

    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise InvalidParameterException("Document_id", document_id, "Document ID not in UUID format")

    doc = await vector_storage_retrieval.get_document(doc_uuid)

    if doc is None:
        raise DocumentNotFound(document_id)
    return doc

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    token: dict = Depends(require_scope("delete:documents"))
    ):
    """
    Delete a document.

    This will:
    1. Delete document from PostgreSQL (cascades to chunks)
    2. Delete original file from MinIO
    3. Remove all embeddings

    Returns success status.
    """
    vector_storage_retrieval = get_vectore_storage_retrieval()
    if vector_storage_retrieval is None:
        raise ServiceUnavailableException("KnowledgeBase", "Not initialized")

    client_id = token.get("sub", "unknown")
    scopes = extract_scopes(token)

    logger.info(
        f"Search request from client: {client_id}, scopes: {scopes}"
    )

    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise InvalidParameterException("Document_id", document_id, "Document ID not in UUID format")

    deleted = await vector_storage_retrieval.delete_document(doc_uuid)

    if not deleted:
        raise DocumentNotFound(document_id)

    return {
        "message": "Document deleted successfully",
        "document_id": document_id
    }
