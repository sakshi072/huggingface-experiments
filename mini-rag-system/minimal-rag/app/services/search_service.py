"""
Search Service

Handles:
- Semantic search with vector similarity
- Optional reranking
"""

import logging
import os
import time
from typing import Dict, List, Optional
from uuid import UUID

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import select

from app.core.feature_flags import feature_flags
from app.db import DocumentChunk, Domain, db_manager
from app.utils.embeddings import get_shared_embedder, embed_chunks
from app.utils.reranking_strategy import (
    RerankCandidate,
    RerankerConfig,
    RerankStrategy,
    UnifiedReranker,
)
from app.utils.timer import SearchTimer

load_dotenv()
logger = logging.getLogger(__name__)


class SearchService:
    """Service for search and document retrieval operations."""

    def __init__(self, reranker_config: Optional[RerankerConfig] = None) -> None:
        """Initialize the search service."""
        logger.info("Initializing SearchService...")

        # Load config
        self.embedding_model = os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )

        # Load embedder (shared with ingestion service)
        logger.info(f"  Embedding model: {self.embedding_model}")
        self.embedder = get_shared_embedder(self.embedding_model)

        # Initialize reranker if enabled
        self.reranker: Optional[UnifiedReranker] = None
        if feature_flags.reranking_enabled:
            logger.info("  Reranking: ENABLED")
            self.reranker = UnifiedReranker(config=reranker_config or RerankerConfig())
            logger.info(f"    Strategy: {self.reranker.config.strategy.value}")
            logger.info(f"    Quality weight: {self.reranker.config.quality_weight}")
            logger.info(f"    Alpha: {self.reranker.config.alpha}")
        else:
            logger.info("  Reranking: DISABLED")

        logger.info("SearchService ready")

    # =========================================================================
    # Search
    # =========================================================================

    async def search(
        self,
        query_text: str,
        domain_name: Optional[str] = None,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
        rerank_strategy: RerankStrategy = RerankStrategy.COMBINED,
    ) -> Dict:
        """
        Search with vector similarity and optional reranking.

        Args:
            query_text: User's query
            domain_name: Filter by domain (None = all domains)
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            rerank_strategy: Reranking strategy to use

        Returns:
            Dictionary with sources and metadata
        """
        timer = SearchTimer()
        start_time = time.time()
        logger.info(f"Search: {query_text[:50]}...")

        if domain_name:
            logger.info(f"  Domain: {domain_name}")

        async with db_manager.session() as session:
            # Get domain config
            domain_id, domain_threshold = await self._resolve_domain(
                session, domain_name
            )
            timer.mark("domain_lookup")

            if min_similarity is None:
                min_similarity = domain_threshold

            # Generate query embedding
            logger.info("  1/3 Generating query embedding...")
            query_embedding = (await embed_chunks(
                [query_text],
                self.embedding_model
            ))[0]
            # query_embedding = self.embedder.encode(
            #     query_text, show_progress_bar=False, convert_to_numpy=True
            # )
            timer.mark("embedding_generation")

            # Vector search
            use_reranking = feature_flags.reranking_enabled and self.reranker
            fetch_limit = (
                top_k * feature_flags.rerank_top_k_multiplier
                if use_reranking
                else top_k
            )

            logger.info("  2/3 Searching vector database...")
            candidates = await self._vector_search(
                session=session,
                query_embedding=query_embedding,
                domain_id=domain_id,
                domain_name=domain_name,
                limit=fetch_limit,
            )
            timer.mark("vector_db_search")

            if not candidates:
                return {
                    "sources": [],
                    "query_time": round(time.time() - start_time, 2),
                    "domain": domain_name,
                    "message": f"No results above threshold {min_similarity}",
                }

            logger.info(f"      Found {len(candidates)} candidates")

            # Rerank or return directly
            if use_reranking and self.reranker:
                logger.info(f"  3/3 Reranking ({rerank_strategy.value})...")
                self.reranker.config.strategy = rerank_strategy
                final_results = self.reranker.rerank(
                    candidates=candidates,
                    query_text=query_text,
                    query_embedding=query_embedding,
                    top_k=top_k,
                )
                strategy_used = rerank_strategy.value
                timer.mark("reranking")
            else:
                logger.info(f"  3/3 Returning top {top_k} by similarity")
                final_results = [
                    {
                        "chunk_id": c.chunk_id,
                        "document_id": c.document_id,
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
                timer.mark("no_rerank_fallback")

            query_time = time.time() - start_time
            logger.info(f"Search complete: {query_time:.2f}s, {len(final_results)} results")
            logger.info(f"Performance (ms): {timer.logs}")

            return {
                "sources": final_results,
                "query_time": round(query_time, 2),
                "domain": domain_name,
                "strategy": strategy_used,
                "num_candidates": len(candidates),
                "features": {
                    "semantic_chunking": feature_flags.semantic_chunking_enabled,
                    "reranking": feature_flags.reranking_enabled,
                },
            }

    async def _resolve_domain(
        self, session, domain_name: Optional[str]
    ) -> tuple[Optional[UUID], float]:
        """Resolve domain name to ID and get threshold."""
        if not domain_name:
            return None, 0.5

        result = await session.execute(
            select(Domain).where(Domain.name == domain_name)
        )
        domain = result.scalar_one_or_none()

        if domain:
            return domain.id, domain.min_similarity_threshold
        return None, 0.5

    async def _vector_search(
        self,
        session,
        query_embedding: np.ndarray,
        domain_id: Optional[UUID],
        domain_name: Optional[str],
        limit: int,
    ) -> List[RerankCandidate]:
        """Execute vector similarity search."""
        distance_func = DocumentChunk.embedding.cosine_distance(
            query_embedding.tolist()
        )

        stmt = select(
            DocumentChunk, (1 - distance_func).label("similarity")
        ).order_by(distance_func.asc())

        if domain_id:
            stmt = stmt.where(DocumentChunk.domain_id == domain_id)

        stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        return [
            RerankCandidate(
                chunk_id=str(chunk.id),
                document_id=str(chunk.document_id),
                domain=domain_name,
                text=chunk.text,
                vector_similarity=float(similarity),
                quality_score=chunk.quality_score,
                chunk_type=chunk.chunk_type,
                chunk_index=chunk.chunk_index,
                keywords=chunk.keywords,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
                file_url=None,
                embedding=(
                    np.array(chunk.embedding) if chunk.embedding is not None else None
                ),
            )
            for chunk, similarity in rows
        ]

