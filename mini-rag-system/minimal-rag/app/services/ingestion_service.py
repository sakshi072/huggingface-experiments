"""
Document Ingestion Service

Handles:
- Domain management
- Document parsing, chunking, and embedding
- Storage in PostgreSQL with pgvector
"""

import hashlib
import logging
from typing import Dict, List, Optional
from uuid import UUID
import time
import asyncio
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import Document, DocumentChunk, Domain, db_manager
from app.utils.document_parser import DocumentParser
from app.utils.document_storage import storage_service
from app.utils.embeddings import get_shared_embedder, embed_chunks
from app.utils.semantic_chunker import HybridChunker, SemanticChunker
from app.core.settings import settings
from fastapi import UploadFile
from app.core.exceptions import (
    UnsupportedFileTypeException, 
    DocumentException,  
    InsufficientContentException,
    InvalidType
)
from app.schemas import FileUploadResult, UploadStatus

logger = logging.getLogger(__name__)


class IngestionService:
    """Service for document ingestion and domain management."""

    def __init__(self) -> None:
        """Initialize the ingestion service."""
        logger.info("Initializing IngestionService...")

        # Load config from env
        self.embedding_model = settings.embedding.model
        self.chunk_size = settings.embedding.chunk_size
        self.chunk_overlap = settings.embedding.chunk_overlap
        self.chunking_strategy = settings.embedding.chunking_strategy
        # Load embedder
        logger.info(f"  Embedding model: {self.embedding_model}")
        self.embedder = get_shared_embedder(self.embedding_model)

        # Initialize chunker
        logger.info(f"  Chunking strategy: {self.chunking_strategy}")
        self.chunker = self._create_chunker()

        logger.info("IngestionService ready")

    async def process_single_file(
        self,
        file: UploadFile,
        domain:str,
        file_number: int = 1,
        total_files: int = 1
    ) -> FileUploadResult:
        """
        Process a single file in the batch or direct upload
        
        This is called concurrently for each file in the batch.
        Each file gets independent error handling.
        """
        file_start_time = time.time()
        filename = file.filename

        logger.info(f"[{file_number}/{total_files}] Processing: {filename}")

        # Validate file type
        allowed_extensions = {".txt", ".md", ".pdf", ".docx"}
        file_ext = file.filename.split('.')[-1].lower()

        if f".{file_ext}" not in allowed_extensions:
            logger.warning(f"[{file_number}/{total_files}] Skipped (unsupported): {filename}")
            if total_files == 1:
                raise UnsupportedFileTypeException(file_ext, list(allowed_extensions))
            return FileUploadResult(
                filename=filename,
                status=UploadStatus.FAILED,
                error_message=f"Unsupported file type: {file_ext}. Allowed: {', '.join(allowed_extensions)}",
                processing_time=round(time.time() - file_start_time, 2)
            )

        try:
            # Read file data
            file_data = await file.read()

            # Validate file isn't empty
            if len(file_data) == 0:
                return FileUploadResult(
                    filename=filename,
                    status=UploadStatus.FAILED,
                    error_message="File is empty",
                    processing_time=round(time.time() - file_start_time, 2)
                )

            # Ingest document
            document_id, is_duplicate = await self.ingest_file(
                file_data=file_data,
                filename=file.filename,
                file_type=file_ext,
                domain_name=domain,
                metadata=None
            )

            processing_time = time.time() - file_start_time

            # Get document details
            doc = await self.get_document(document_id)

            doc_metadata = doc.get("metadata")
            if doc_metadata is not None and not isinstance(doc_metadata, dict):
                doc_metadata = {}

            if is_duplicate:
                status = UploadStatus.DUPLICATE
                message = "Duplicate file detected! Using existing document."
                logger.info(f"[{file_number}/{total_files}] Duplicate: {filename}")
            else:
                status = UploadStatus.SUCCESS
                message = "Document ingested successfully"
                logger.info(
                    f"[{file_number}/{total_files}] Success: {filename} "
                    f"({doc['chunk_count']} chunks in {processing_time:.2f}s)"
                )

            return FileUploadResult(
                message=message,
                filename=filename,
                status=status,
                document_id=str(document_id),
                chunks_created=doc["chunk_count"],
                processing_time=round(processing_time, 2),
                metadata=doc_metadata,
                error_message=None
            )
        except Exception as e:
            processing_time = time.time() - file_start_time
            error_msg = str(e)

            logger.error(
                f"[{file_number}/{total_files}] Failed: {filename} - {error_msg}"
            )
            if total_files == 1:
                raise DocumentException(f"Error processing document '{filename}': {str(e)}")

            return FileUploadResult(
                filename=filename,
                status=UploadStatus.FAILED,
                error_message=error_msg,
                processing_time=round(processing_time, 2)
            )
        
    async def process_files_concurrently(
        self,
        files: List[UploadFile],
        domain:str
    ) -> List[FileUploadResult]:
        """
        Process multiple files concurrently using asyncio.gather
        """
        tasks = [
            self.process_single_file(file, domain, idx+1, len(files))
            for idx, file in enumerate(files)
        ]

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        final_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(FileUploadResult(
                    filename=files[idx].filename,
                    status=UploadStatus.FAILED,
                    error_message=f"Unexpected error: {str(result)}",
                    processing_time=0.0
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    def _create_chunker(self):
        """Create chunker based on configured strategy."""
        if self.chunking_strategy == "semantic_chunking":
            return SemanticChunker(
                embedder=self.embedder,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
        elif self.chunking_strategy == "hybrid_chunking":
            return HybridChunker(embedder=self.embedder)
        else:
            return RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )

    # =========================================================================
    # Domain Management
    # =========================================================================

    async def ensure_domain(self, session:AsyncSession, domain_name: str) -> UUID:
        """Ensure domain exists, create if not."""
        
        result = await session.execute(
            select(Domain).where(Domain.name == domain_name)
        )
        domain = result.scalar_one_or_none()

        if not domain:
            logger.info(f"Creating new domain: {domain_name}")
            domain = Domain(name=domain_name, min_similarity_threshold=0.5)
            session.add(domain)
            await session.flush()

        return domain.id

    # =========================================================================
    # Document Ingestion
    # =========================================================================

    def _calculate_file_hash(self, file_data: bytes) -> str:
        """Calculate SHA256 hash of file data."""
        return hashlib.sha256(file_data).hexdigest()

    async def ingest_file(
        self,
        file_data: bytes,
        filename: str,
        file_type: str,
        domain_name: str = "general",
        owner_id: Optional[str] = None,
        is_public: bool = False,
        metadata: Optional[Dict] = None,
    ) -> tuple[UUID, bool]:
        """
        Ingest document with chunking and embedding.

        Args:
            file_data: File content as bytes
            filename: Original filename
            file_type: File extension (pdf, docx, txt, md)
            domain_name: Target domain (default: 'general')
            owner_id: Owner user ID (for access control)
            is_public: Whether document is publicly accessible
            metadata: Optional metadata

        Returns:
            Tuple of (document_id, is_duplicate)
        """
        logger.info(f"Ingesting: {filename} -> {domain_name}")

        async with db_manager.session() as session:
            domain_id = await self.ensure_domain(session, domain_name)
            file_hash = self._calculate_file_hash(file_data)

            # Check for duplicates
            existing = await session.execute(
                select(Document).where(
                    and_(
                        Document.file_hash == file_hash,
                        Document.domain_id == domain_id,
                    )
                )
            )

            if existing_doc := existing.scalar_one_or_none():
                if existing_doc.status == "completed":
                    logger.info(f"Duplicate detected: {existing_doc.id}")
                    return existing_doc.id, True
                else:
                    # Clean up failed/processing document
                    await self._cleanup_document(session, existing_doc)

            document_id = await self._process_document(
                session=session,
                file_data=file_data,
                filename=filename,
                file_type=file_type,
                file_hash=file_hash,
                domain_id=domain_id,
                owner_id=owner_id,
                is_public=is_public,
                metadata=metadata,
            )
            return document_id, False

    async def _cleanup_document(self, session, document: Document) -> None:
        """Clean up a failed or incomplete document."""
        logger.info(f"Cleaning up {document.status} document: {document.id}")
        try:
            if document.minio_object_key:
                storage_service.delete_file(document.minio_object_key)
        except Exception as e:
            logger.warning(f"Could not delete from MinIO: {e}")
        await session.delete(document)
        await session.flush()

    async def _process_document(
        self,
        session,
        file_data: bytes,
        filename: str,
        file_type: str,
        file_hash: str,
        domain_id: UUID,
        owner_id: Optional[str],
        is_public: bool,
        metadata: Optional[Dict],
    ) -> UUID:
        """Process and store a document with its chunks."""
        # 1. Upload to MinIO
        logger.info("  1/7 Uploading to MinIO...")
        object_key = storage_service.upload_file(file_data, filename)

        # 2. Create document record
        logger.info("  2/7 Creating document record...")
        document = Document(
            domain_id=domain_id,
            filename=filename,
            file_type=file_type,
            file_size=len(file_data),
            file_hash=file_hash,
            minio_object_key=object_key,
            owner_id=owner_id,
            is_public=is_public,
            status="processing",
            processing_version="2.0",
            metadata_=metadata or {},
        )
        session.add(document)
        await session.flush()
        logger.info(f"      Document ID: {document.id}")

        try:
            # 3. Parse document
            logger.info("  3/7 Parsing document...")
            parsed_result = DocumentParser.parse(file_data, file_type)

            if not isinstance(parsed_result, dict):
                raise InvalidType("parsed_result", str({type(parsed_result)}), "dict")

            parsed_text = parsed_result["text"]
            parse_metadata = parsed_result.get("metadata", {})

            if len(parsed_text) < 10:
                raise InsufficientContentException(filename)

            if isinstance(parse_metadata, dict):
                document.metadata_ = {**(metadata or {}), **parse_metadata}
            logger.info(f"      Extracted {len(parsed_text)} characters")

            # 4. Chunk text
            logger.info(f"  4/7 Chunking text ({self.chunking_strategy})...")
            chunk_texts, semantic_chunks, use_semantic = self._chunk_text(
                parsed_text, file_type, parse_metadata
            )
            logger.info(f"      Created {len(chunk_texts)} chunks")

            # 5. Generate embeddings
            logger.info("  5/7 Generating embeddings...")
            embeddings = await embed_chunks(
                chunk_texts,
                self.embedding_model
            )
            
            logger.info(f"      Generated {len(embeddings)} embeddings")

            # 6. Store chunks
            logger.info("  6/7 Storing chunks...")
            quality_scores = self._store_chunks(
                session=session,
                document=document,
                domain_id=domain_id,
                chunk_texts=chunk_texts,
                embeddings=embeddings,
                semantic_chunks=semantic_chunks,
                use_semantic=use_semantic,
            )

            # 7. Finalize
            logger.info("  7/7 Finalizing...")
            document.status = "completed"
            document.chunk_count = len(chunk_texts)
            document.avg_chunk_quality = (
                float(np.mean(quality_scores)) if quality_scores else None
            )
            await session.flush()

            logger.info(f"Ingestion complete: {len(chunk_texts)} chunks")
            return document.id

        except Exception as e:
            document.status = "failed"
            document.error_message = str(e)
            await session.commit()
            raise

    def _chunk_text(
        self, text: str, file_type: str, metadata: dict
    ) -> tuple[List[str], Optional[List], bool]:
        """Chunk text using configured strategy."""
        if self.chunking_strategy in ("semantic_chunking", "hybrid_chunking"):
            semantic_chunks = self.chunker.chunk_document(
                text=text, file_type=file_type, metadata=metadata
            )
            return [c.text for c in semantic_chunks], semantic_chunks, True
        else:
            return self.chunker.split_text(text), None, False

    def _store_chunks(
        self,
        session,
        document: Document,
        domain_id: UUID,
        chunk_texts: List[str],
        embeddings: np.ndarray,
        semantic_chunks: Optional[List],
        use_semantic: bool,
    ) -> List[float]:
        """Store document chunks with embeddings."""
        quality_scores = []

        for idx, (chunk_text, embedding) in enumerate(zip(chunk_texts, embeddings)):
            if use_semantic and semantic_chunks:
                sc = semantic_chunks[idx]
                chunk = DocumentChunk(
                    document_id=document.id,
                    domain_id=domain_id,
                    chunk_index=sc.chunk_index,
                    text=sc.text,
                    embedding=embedding.tolist(),
                    chunk_type=sc.chunk_type,
                    semantic_density=sc.semantic_density,
                    keywords=sc.keywords,
                    section_title=sc.section_title,
                    page_number=sc.page_number,
                    quality_score=sc.quality_score,
                    token_count=len(sc.text.split()),
                )
                if sc.quality_score:
                    quality_scores.append(sc.quality_score)
            else:
                chunk = DocumentChunk(
                    document_id=document.id,
                    domain_id=domain_id,
                    chunk_index=idx,
                    text=chunk_text,
                    embedding=embedding.tolist(),
                    token_count=len(chunk_text.split()),
                )
            session.add(chunk)

        return quality_scores

    # =========================================================================
    # Document CRUD
    # =========================================================================
    async def get_document(self, document_id: UUID) -> Optional[Dict]:
        """Get document metadata by ID."""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Document, Domain).join(Domain).where(Document.id == document_id)
            )
            row = result.one_or_none()

            if not row:
                return None

            doc, domain = row
            return {
                "id": str(doc.id),
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "domain": domain.name,
                "status": doc.status,
                "chunk_count": doc.chunk_count,
                "avg_chunk_quality": doc.avg_chunk_quality,
                "metadata": dict(doc.metadata_) if doc.metadata_ else {},
                "owner_id": doc.owner_id,
                "is_public": doc.is_public,
                "created_at": doc.created_at.isoformat(),
            }

    async def list_documents(
        self, domain_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """List documents with optional domain filter."""
        async with db_manager.session() as session:
            stmt = (
                select(Document, Domain)
                .join(Domain)
                .order_by(Document.created_at.desc())
                .limit(limit)
            )

            if domain_name:
                stmt = stmt.where(Domain.name == domain_name)

            result = await session.execute(stmt)
            rows = result.all()

        return [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "domain": domain.name,
                "status": doc.status,
                "chunk_count": doc.chunk_count,
                "avg_chunk_quality": doc.avg_chunk_quality,
                "created_at": doc.created_at.isoformat(),
            }
            for doc, domain in rows
        ]

    async def delete_document(self, document_id: UUID) -> bool:
        """Delete a document and its chunks."""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return False

            # Delete from MinIO
            if doc.minio_object_key:
                try:
                    storage_service.delete_file(doc.minio_object_key)
                except Exception as e:
                    logger.error(f"Failed to delete from MinIO: {e}")

            # Delete from database (cascades to chunks)
            await session.delete(doc)
            await session.commit()
            logger.info(f"Deleted document: {document_id}")
            return True

    async def get_stats(self) -> Dict:
        """Get system statistics."""
        async with db_manager.session() as session:
            doc_result = await session.execute(select(func.count(Document.id)))
            total_docs = doc_result.scalar()

            chunk_result = await session.execute(select(func.count(DocumentChunk.id)))
            total_chunks = chunk_result.scalar()

            status_result = await session.execute(
                select(Document.status, func.count(Document.id)).group_by(
                    Document.status
                )
            )

            return {
                "total_documents": total_docs,
                "total_chunks": total_chunks,
                "status_breakdown": {
                    status: count for status, count in status_result.all()
                },
            }