"""
Production Vector Storage and Retrieval - Knowledge Base Service

Features:
1. Domain-aware document ingestion
2. Semantic chunking with quality scoring
3. Unified reranking strategies
4. Vector similarity search with pgvector
5. Analytics and monitoring

Version: 2.0
"""

import hashlib
from typing import List, Dict, Optional
from uuid import UUID

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select, func, and_, or_

from app.db import db_manager, Document, DocumentChunk, Domain
from app.services.storage_service import storage_service
from app.services.parser_service import DocumentParser
from app.core.feature_flags import feature_flags
from .reranking_strategy import UnifiedReranker, RerankCandidate, RerankerConfig, RerankStrategy
from .semantic_chunker import SemanticChunker, SemanticChunk
import numpy as np
import time
import logging

load_dotenv()
logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class KnowledgeBase:
    """Vector Storage and Retrieval system for semantic search and document retrieval."""

    def __init__(self, reranker_config: RerankerConfig = None):
        """Initialize components."""
        logger.info("Initializing Vector Storage and Retrieval System...")
        logger.info(f"Feature Flags: {feature_flags}")

        # Embedding model (runs locally, no API needed)
        logger.info(f" Loading embedding model: {EMBEDDING_MODEL}")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)

        # Basic text splitter (always available as fallback)
        self.basic_text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        # Semantic chunker (initialized only if enabled)
        self.semantic_chunker = None
        if feature_flags.semantic_chunking_enabled:
            logger.info("Initializing semantic chunker (ENABLED)...")
            self.semantic_chunker = SemanticChunker(
                embedder=self.embedder,
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP
            )
        else:
            logger.info("Semantic chunking: DISABLED (using basic chunking)")
        # Unified reranker (initialized only if enabled)
        self.reranker = None
        if feature_flags.reranking_enabled:
            logger.info("Initializing unified reranker (ENABLED)...")
            self.reranker = UnifiedReranker(
                config=reranker_config or RerankerConfig(
                    strategy=RerankStrategy.COMBINED,
                    quality_weight=0.2,
                    alpha=0.7,
                    max_chunks_per_doc=2
                )
            )
        else:
            logger.info("Reranking: DISABLED (using vector similarity only)")

        # Initialize database
        db_manager.initialize()

        logger.info("Initialization complete!\n")
    
    # ========================================================================
    # Domain Management
    # ========================================================================

    async def ensure_domain(self, domain_name:str) -> UUID:
        """Ensure domain exists, create if not"""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Domain).where(Domain.name == domain_name)
            )
            domain = result.scalar_one_or_none()

            if not domain:
                logger.info(f" Creating new domain: {domain_name}")
                domain = Domain(
                    name=domain_name,
                    min_similarity_threshold=0.5
                )
                session.add(domain)
                await session.flush()
            
            return domain.id
        
    async def get_domain_config(self, domain_name:str) -> Optional[Domain]:
        """Get domain configuration."""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Domain).where(Domain.name == domain_name)
            )
            return result.scalar_one_or_none()

    def calculate_file_hash(self, file_data: bytes) -> str:
        return hashlib.sha256(file_data).hexdigest()
    
    # ========================================================================
    # Document Ingestion
    # ========================================================================

    async def ingest_file(
        self,
        file_data: bytes,
        filename: str,
        file_type: str,
        domain_name:str = 'general',
        owner_id: Optional[str] = None,
        is_public:bool = False,
        metadata: Optional[Dict] = None
    ) -> tuple[UUID, bool]:
        """
        Ingest document with semantic chunking and quality scoring.

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
        logger.info(f"\n📄 Ingesting: {filename} → Domain: {domain_name}")

        async with db_manager.session() as session:

            # Ensure domain exists
            domain_id = await self.ensure_domain(domain_name)

            # Get domain settings
            domain = await self.get_domain_config(domain_name)

            # Calculate hash
            file_hash = self.calculate_file_hash(file_data)

            # Check for duplicates
            existing = await session.execute(
                select(Document).where(
                    and_(
                        Document.file_hash == file_hash,
                        Document.domain_id == domain_id
                    )
                )
            )
            if existing_doc := existing.scalar_one_or_none():
                if existing_doc.status == "completed":
                    # Successfully ingested before - return as duplicate
                    logger.info(f"Duplicate! Using existing doc {existing_doc.id}")
                    return existing_doc.id, True
                else:
                    # Failed or processing - clean up and re-ingest
                    logger.info(f"Found {existing_doc.status} document {existing_doc.id}, cleaning up for re-ingestion...")
                    try:
                        # Delete from MinIO if exists
                        if existing_doc.minio_object_key:
                            storage_service.delete_file(existing_doc.minio_object_key)
                    except Exception as e:
                        logger.warning(f"   Warning: Could not delete from MinIO: {e}")
                    # Delete document (cascades to chunks)
                    await session.delete(existing_doc)
                    await session.flush()
                    logger.info(f"   Cleaned up failed document, proceeding with fresh ingestion")

            try:
                # 1. Upload File to MinIO
                logger.info("   1/7 Uploading original file to MinIO...")
                object_key = storage_service.upload_file(file_data, filename)
                logger.info(f"       Stored as: {object_key}")

                # 2. Create document record
                logger.info("   2/7 Creating document record...")
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
                    metadata_=metadata or {}
                )

                session.add(document)
                await session.flush()
                logger.info(f"       Document ID: {document.id}")

                # 3. Parse the ORIGINAL file (not pre-parsed text)
                logger.info("   3/7 Parsing document...")
                parsed_result = DocumentParser.parse(file_data, file_type)

                # Validate parser result
                if not isinstance(parsed_result, dict):
                    raise ValueError(f"Parser returned {type(parsed_result)} instead of dict")

                parsed_text = parsed_result["text"]
                parse_metadata = parsed_result.get("metadata", {})

                # Check if extraction was successful
                if len(parsed_text) < 10:
                    raise ValueError(
                        f"Extracted text is too short ({len(parsed_text)} chars). "
                        "PDF may be scanned/image-based (OCR not supported) or corrupted."
                    )

                # Update metadata
                if isinstance(parse_metadata, dict):
                    document.metadata_ = {**(metadata or {}), **parse_metadata}
                logger.info(f"       ✓ Extracted {len(parsed_text)} characters")

                # 4. Chunk text (feature flag: semantic vs basic)
                if feature_flags.semantic_chunking_enabled and self.semantic_chunker:
                    logger.info("   4/7 Chunking text (SEMANTIC)...")
                    semantic_chunks = self.semantic_chunker.chunk_document(
                        text=parsed_text,
                        file_type=file_type,
                        metadata=parse_metadata
                    )
                    chunk_texts = [chunk.text for chunk in semantic_chunks]
                    use_semantic = True
                else:
                    logger.info("   4/7 Chunking text (BASIC)...")
                    chunk_texts = self.basic_text_splitter.split_text(parsed_text)
                    semantic_chunks = None
                    use_semantic = False
                logger.info(f"       Created {len(chunk_texts)} chunks")

                # 5. Generate embeddings
                logger.info("   5/7 Generating embeddings...")
                embeddings = self.embedder.encode(
                    chunk_texts,
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
                logger.info(f"       Generated {len(embeddings)} embeddings")

                # 6. Store chunks with embeddings
                logger.info("   6/7 Storing chunks in PostgreSQL...")
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
                            token_count=len(sc.text.split())
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
                            token_count=len(chunk_text.split())
                        )
                    session.add(chunk)

                # Step 7: Finalize document
                logger.info("   7/7 Finalizing...")
                document.status = "completed"
                document.chunk_count = len(chunk_texts)
                document.avg_chunk_quality = (
                    np.mean(quality_scores) if quality_scores else None
                )
                await session.flush()

                logger.info(f"Ingestion complete!")
                logger.info(f"   Document ID: {document.id}")
                logger.info(f"   Domain: {domain_name}")
                logger.info(f"   Chunks: {len(chunk_texts)}")
                if document.avg_chunk_quality:
                    logger.info(f"   Avg Quality: {document.avg_chunk_quality:.2f}")

                return document.id, False
            
            except Exception as e:
                # Mark document as failed
                if 'document' in locals():
                    document.status = "failed"
                    document.error_message = str(e)
                    await session.commit()

                logger.error(f"Ingestion failed: {e}")
                raise
    
    # ========================================================================
    # Search & Retrieval
    # ========================================================================

    async def search(
        self,
        query_text: str,
        domain_name: Optional[str] = None,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
        rerank_strategy: RerankStrategy = RerankStrategy.COMBINED,
        filter_by_quality: bool = True,
        user_id: Optional[str] = None
    ) -> Dict:
        """
        Search with unified reranking.

        Args:
            query_text: User's query
            domain_name: Filter by domain (None = all domains)
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            rerank_strategy: Reranking strategy to use
            filter_by_quality: Filter low-quality chunks
            user_id: User ID for logging

        Returns:
            Dictionary with sources and metadata
        """
        start_time = time.time()
        logger.info(f"\n🔍 Search: {query_text}")

        if domain_name:
            logger.info(f"Domain: {domain_name}")

        async with db_manager.session() as session:
            # Get domain config
            domain_id = None
            domain_threshold = 0.5

            if domain_name:
                domain_result = await session.execute(
                    select(Domain).where(Domain.name == domain_name)
                )
                domain = domain_result.scalar_one_or_none()
                if domain:
                    domain_id = domain.id
                    domain_threshold = domain.min_similarity_threshold
            
            # Use domain threshold if not specified
            if min_similarity is None:
                min_similarity = domain_threshold

            # 1. Generate query embedding
            logger.info("   1/3 Generating query embedding...")
            query_embedding = self.embedder.encode(
                query_text,
                show_progress_bar=False,
                convert_to_numpy=True
            )

            # Step 2: Vector search
            use_reranking = feature_flags.reranking_enabled and self.reranker
            fetch_limit = top_k * feature_flags.rerank_top_k_multiplier if use_reranking else top_k

            logger.info(f"   2/3 Searching vector database...")
            candidates = await self._vector_search(
                session=session,
                query_embedding=query_embedding,
                domain_id=domain_id,
                min_similarity=min_similarity,
                filter_by_quality=filter_by_quality,
                limit=fetch_limit
            )

            if not candidates:
                return {
                    "sources": [],
                    "query_time": round(time.time() - start_time, 2),
                    "domain": domain_name,
                    "message": f"No results above threshold {min_similarity}"
                }

            logger.info(f"       Found {len(candidates)} candidates")

            # Step 3: Rerank or return directly (feature flag)
            if use_reranking:
                logger.info(f"   3/3 Reranking (ENABLED - {rerank_strategy.value})...")
                self.reranker.config.strategy = rerank_strategy
                final_results = self.reranker.rerank(
                    candidates=candidates,
                    query_text=query_text,
                    query_embedding=query_embedding,
                    top_k=top_k
                )
                strategy_used = rerank_strategy.value
            else:
                logger.info(f"   3/3 Reranking: DISABLED (returning top {top_k} by similarity)")
                # Convert candidates to result format without reranking
                final_results = [
                    {
                        "chunk_id": c.chunk_id,
                        "document_id": c.document_id,
                        "filename": c.filename,
                        "domain": c.domain,
                        "text": c.text,
                        "similarity": c.vector_similarity,
                        "file_url": c.file_url,
                        "chunk_index": c.chunk_index,
                        "page_number": c.page_number,
                    }
                    for c in candidates[:top_k]
                ]
                strategy_used = "none"

            query_time = time.time() - start_time
            logger.info(f"Search complete in {query_time:.2f}s")
            logger.info(f"   Returned {len(final_results)} results")

            return {
                "sources": final_results,
                "query_time": round(query_time, 2),
                "domain": domain_name,
                "strategy": strategy_used,
                "num_candidates": len(candidates),
                "features": {
                    "semantic_chunking": feature_flags.semantic_chunking_enabled,
                    "reranking": feature_flags.reranking_enabled
                }
            }

    async def _vector_search(
        self,
        session,
        query_embedding:np.ndarray,
        domain_id: Optional[UUID],
        min_similarity:float,
        filter_by_quality:bool,
        limit:int,
    ) -> List[RerankCandidate]:
        """
        Pure vector similarity search (no reranking).

        Returns candidates for reranking.
        """

        # Compute similarity
        similarity_col = (
            1 - DocumentChunk.embedding.cosine_distance(query_embedding.tolist())
        ).label('similarity')

        # Build query
        stmt = (
            select(DocumentChunk, Document, Domain, similarity_col)
            .select_from(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .join(Domain, DocumentChunk.domain_id == Domain.id)
            .where(Document.status == "completed")
            .where(similarity_col >= min_similarity)
        )

        # Domain filter
        if domain_id:
            stmt = stmt.where(DocumentChunk.domain_id == domain_id)
        
        # Quality filter
        if filter_by_quality:
            stmt = stmt.where(
                or_(
                    DocumentChunk.quality_score >= 0.5,
                    DocumentChunk.quality_score.is_(None)
                )
            )
        
        # Order and limit
        stmt = stmt.order_by(similarity_col.desc()).limit(limit)

        # Execute
        result = await session.execute(stmt)
        rows = result.all()

        # Convert to RerankCandidate format
        candidates = []
        for chunk, doc, domain, similarity in rows:
            # Get presigned URL
            try:
                file_url = storage_service.get_presigned_url(
                    doc.minio_object_key,
                    expiry_seconds=3600
                )
            except:
                file_url = None
            
            # Create candidate
            candidate = RerankCandidate(
                chunk_id=str(chunk.id),
                document_id=str(doc.id),
                filename=doc.filename,
                domain=domain.name,
                text=chunk.text,
                vector_similarity=float(similarity),
                quality_score=chunk.quality_score,
                chunk_type=chunk.chunk_type,
                chunk_index=chunk.chunk_index,
                keywords=chunk.keywords,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
                file_url=file_url,
                embedding=np.array(chunk.embedding) if chunk.embedding is not None else None
            )
            candidates.append(candidate)

        return candidates


    async def get_document(self, document_id: UUID) -> Optional[Dict]:
        """Get document metadata"""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Document, Domain)
                .join(Domain)
                .where(Document.id == document_id)
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
                "created_at": doc.created_at.isoformat()
            }

    async def list_documents(self, domain_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """List all documents"""
        async with db_manager.session() as session:
            stmt = (
                select(Document, Domain)
                .join(Domain)
                .order_by(Document.created_at.desc())
            )
            # Domain filter
            if domain_name:
                stmt = stmt.where(Domain.name == domain_name)
            
            # Pagination
            stmt = stmt.limit(limit)

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
                "created_at": doc.created_at.isoformat()
            }
            for doc, domain in rows
        ]

    async def delete_document(self, document_id: UUID) -> bool:
        """Delete document and all its chunks"""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return False

            # Delete from MinIO
            try:
                storage_service.delete_file(doc.minio_object_key)
            except Exception as e:
                logger.error(f"Failed to delete from MinIO: {e}")

            # Delete from database (cascades to chunks)
            await session.delete(doc)
            await session.commit()

            return True

    async def get_stats(self) -> Dict:
        """Get Vector Storage and Retrieval system statistics"""
        async with db_manager.session() as session:
            # Count documents
            doc_result = await session.execute(
                select(func.count(Document.id))
            )
            total_docs = doc_result.scalar()

            # Count chunks
            chunk_result = await session.execute(
                select(func.count(DocumentChunk.id))
            )
            total_chunks = chunk_result.scalar()

            # Count by status
            status_result = await session.execute(
                select(Document.status, func.count(Document.id))
                .group_by(Document.status)
            )

            status_counts = {status: count for status, count in status_result.all()}

            return {
                "total_documents": total_docs,
                "total_chunks": total_chunks,
                "status_breakdown": status_counts
            }
