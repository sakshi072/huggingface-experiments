"""
Unified reranking module - single source of truth for result reranking

Architecture:
1. Database returns candidates (vector similarity only)
2. Reranker applies multiple strategies (quality, diversity, hybrid)
3. Return final ranked results

This eliminates duplicate reranking logic across modules.
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np
from enum import Enum
from app.core.settings import settings

class RerankStrategy(Enum):
    """Available reranking strategies"""
    SIMILARITY_ONLY = "similarity"  # Just use vector similarity
    QUALITY_BOOST = "quality"       # Boost by quality score
    HYBRID_SCORE = "hybrid"         # Dense + sparse scoring
    MMR_DIVERSITY = "mmr"           # Maximal Marginal Relevance
    COMBINED = "combined"           # All strategies together


@dataclass
class RerankCandidate:
    """
    Unified candidate structure from database

    This is what comes OUT of the database query
    """
    chunk_id: str
    document_id: str
    domain: str
    text: str

    # Scores
    vector_similarity: float  # From pgvector cosine similarity
    quality_score: Optional[float] = None

    # Metadata
    chunk_type: Optional[str] = None
    chunk_index: int = 0
    keywords: Optional[List[str]] = None
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    filename: Optional[str] = None

    # Additional
    file_url: Optional[str] = None
    metadata: Optional[Dict] = None
    embedding: Optional[np.ndarray] = None  # Only if needed for MMR


@dataclass
class RerankerConfig:
    """Configuration for reranking - reads defaults from environment variables"""
    strategy: RerankStrategy = None

    # Quality boost params
    quality_weight: float = None  # Max boost from quality

    # Hybrid params
    alpha: float = None  # Weight for dense (1-alpha for sparse)

    # MMR params
    lambda_param: float = None  # Balance relevance vs diversity

    # Type preferences
    type_weights: Dict[str, float] = None

    # Diversity
    max_chunks_per_doc: int = None  # Promote diversity across documents

    def __post_init__(self):
        # Load defaults from env if not explicitly set
        if self.strategy is None:
            strategy_str = settings.rerank.strategy
            self.strategy = RerankStrategy(strategy_str)

        if self.quality_weight is None:
            self.quality_weight = settings.rerank.quality_weight

        if self.alpha is None:
            self.alpha = settings.rerank.alpha

        if self.lambda_param is None:
            self.lambda_param = settings.rerank.lambda_param

        if self.max_chunks_per_doc is None:
            self.max_chunks_per_doc = settings.rerank.max_chunks_per_doc

        if self.type_weights is None:
            self.type_weights = {
                'paragraph': 1.1,
                'section': 1.05,
                'list': 1.0,
                'code': 0.95,
                'table': 0.95,
                'heading': 0.9
            }


class UnifiedReranker:
    """
    Single reranking service used throughout the application
    
    Usage:
        reranker = UnifiedReranker(config)
        results = reranker.rerank(candidates, query, top_k=5)
    """
    
    def __init__(self, config: RerankerConfig = None):
        self.config = config or RerankerConfig()
    
    def rerank(
        self,
        candidates: List[RerankCandidate],
        query_text: str,
        query_embedding: Optional[np.ndarray] = None,
        top_k: int = 10
    ) -> List[Dict]:
        """
        Main reranking function - routes to appropriate strategy
        
        Args:
            candidates: Results from database query
            query_text: Original query string
            query_embedding: Query embedding (needed for MMR/hybrid)
            top_k: Number of results to return
            
        Returns:
            Reranked and formatted results
        """
        if not candidates:
            return []
        
        # Route to strategy
        if self.config.strategy == RerankStrategy.SIMILARITY_ONLY:
            scored = self._rerank_similarity_only(candidates)
        
        elif self.config.strategy == RerankStrategy.QUALITY_BOOST:
            scored = self._rerank_with_quality(candidates)
        
        elif self.config.strategy == RerankStrategy.HYBRID_SCORE:
            if query_embedding is None:
                # Fallback to quality boost
                scored = self._rerank_with_quality(candidates)
            else:
                scored = self._rerank_hybrid(candidates, query_text, query_embedding)
        
        elif self.config.strategy == RerankStrategy.MMR_DIVERSITY:
            if query_embedding is None or not all(c.embedding is not None for c in candidates):
                # Fallback to quality boost
                scored = self._rerank_with_quality(candidates)
            else:
                scored = self._rerank_mmr(candidates, query_embedding)
        
        else:  # COMBINED
            scored = self._rerank_combined(candidates, query_text, query_embedding)
        
        # Apply diversity filter (max chunks per document)
        diverse = self._apply_diversity_filter(scored, self.config.max_chunks_per_doc)
        
        # Take top-k
        final = diverse[:top_k]
        
        # Format for API response
        return self._format_results(final)
    
    def _rerank_similarity_only(
        self,
        candidates: List[RerankCandidate]
    ) -> List[Tuple[RerankCandidate, float]]:
        """
        Strategy 1: Use only vector similarity (fastest)
        
        Just sort by database similarity score
        """
        scored = [(c, c.vector_similarity) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def _rerank_with_quality(
        self,
        candidates: List[RerankCandidate]
    ) -> List[Tuple[RerankCandidate, float]]:
        """
        Strategy 2: Boost results by quality score
        
        Formula: final_score = similarity * (1 + quality * weight)
        """
        scored = []
        
        for candidate in candidates:
            base_score = candidate.vector_similarity
            
            # Quality boost (0-20% by default)
            quality_boost = 1.0
            if candidate.quality_score is not None:
                quality_boost = 1 + (candidate.quality_score * self.config.quality_weight)
            
            # Type boost
            type_boost = self.config.type_weights.get(
                candidate.chunk_type or 'paragraph',
                1.0
            )
            
            final_score = base_score * quality_boost * type_boost
            scored.append((candidate, final_score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def _rerank_hybrid(
        self,
        candidates: List[RerankCandidate],
        query_text: str,
        query_embedding: np.ndarray
    ) -> List[Tuple[RerankCandidate, float]]:
        """
        Strategy 3: Hybrid dense + sparse scoring
        
        Combines:
        - Dense: Vector similarity (already have)
        - Sparse: BM25-like keyword matching
        """
        scored = []
        
        for candidate in candidates:
            # Dense score (already computed)
            dense_score = candidate.vector_similarity
            
            # Sparse score (BM25 approximation)
            sparse_score = self._compute_bm25_score(query_text, candidate.text)
            
            # Hybrid combination
            hybrid_score = (
                self.config.alpha * dense_score +
                (1 - self.config.alpha) * sparse_score
            )
            
            # Quality boost
            quality_boost = 1.0
            if candidate.quality_score is not None:
                quality_boost = 1 + (candidate.quality_score * self.config.quality_weight)
            
            final_score = hybrid_score * quality_boost
            scored.append((candidate, final_score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def _rerank_mmr(
        self,
        candidates: List[RerankCandidate],
        query_embedding: np.ndarray
    ) -> List[Tuple[RerankCandidate, float]]:
        """
        Strategy 4: Maximal Marginal Relevance (diversity)
        
        Selects diverse results to avoid redundancy
        """
        if not candidates or not all(c.embedding is not None for c in candidates):
            return self._rerank_with_quality(candidates)
        
        selected = []
        remaining = candidates.copy()
        
        # First: select most similar
        similarities = [c.vector_similarity for c in remaining]
        first_idx = np.argmax(similarities)
        selected.append((remaining.pop(first_idx), similarities[first_idx]))
        
        # Iteratively select remaining with MMR
        while remaining and len(selected) < len(candidates):
            mmr_scores = []
            
            for candidate in remaining:
                # Relevance to query
                relevance = candidate.vector_similarity
                
                # Max similarity to already selected
                max_similarity = max([
                    self._cosine_similarity(candidate.embedding, sel[0].embedding)
                    for sel in selected
                ])
                
                # MMR score
                mmr = (
                    self.config.lambda_param * relevance -
                    (1 - self.config.lambda_param) * max_similarity
                )
                mmr_scores.append((candidate, mmr))
            
            # Select best MMR
            best = max(mmr_scores, key=lambda x: x[1])
            selected.append(best)
            remaining.remove(best[0])
        
        return selected
    
    def _rerank_combined(
        self,
        candidates: List[RerankCandidate],
        query_text: str,
        query_embedding: Optional[np.ndarray]
    ) -> List[Tuple[RerankCandidate, float]]:
        """
        Strategy 5: Combined approach (production default)
        
        1. Start with quality-boosted scores
        2. Add hybrid scoring if possible
        3. Apply diversity at the end
        """
        scored = []
        
        for candidate in candidates:
            # Base: vector similarity
            score = candidate.vector_similarity
            
            # Layer 1: Quality boost
            if candidate.quality_score is not None:
                quality_boost = 1 + (candidate.quality_score * self.config.quality_weight)
                score *= quality_boost
            
            # Layer 2: Type preference
            type_boost = self.config.type_weights.get(
                candidate.chunk_type or 'paragraph',
                1.0
            )
            score *= type_boost
            
            # Layer 3: Hybrid scoring (if query available)
            if query_text and self.config.alpha < 1.0:
                sparse_score = self._compute_bm25_score(query_text, candidate.text)
                # Blend in sparse component
                score = (
                    self.config.alpha * score +
                    (1 - self.config.alpha) * sparse_score
                )
            
            scored.append((candidate, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Apply MMR-like diversity if embeddings available
        if query_embedding is not None and all(c.embedding is not None for c in candidates):
            # Use MMR on top-20 to select diverse top-10
            top_candidates = [c for c, s in scored[:20]]
            if len(top_candidates) > 10:
                scored = self._rerank_mmr(top_candidates, query_embedding)
        
        return scored
    
    def _apply_diversity_filter(
        self,
        scored: List[Tuple[RerankCandidate, float]],
        max_per_doc: int
    ) -> List[Tuple[RerankCandidate, float]]:
        """
        Ensure diversity across documents
        
        Limits chunks from same document to avoid redundancy
        """
        if max_per_doc <= 0:
            return scored
        
        doc_counts = {}
        filtered = []
        
        for candidate, score in scored:
            doc_id = candidate.document_id
            count = doc_counts.get(doc_id, 0)
            
            if count < max_per_doc:
                filtered.append((candidate, score))
                doc_counts[doc_id] = count + 1
        
        return filtered
    
    def _compute_bm25_score(
        self,
        query: str,
        document: str,
        k1: float = 1.5,
        b: float = 0.75
    ) -> float:
        """BM25 scoring for sparse retrieval"""
        query_terms = set(query.lower().split())
        doc_terms = document.lower().split()
        doc_length = len(doc_terms)
        avg_doc_length = 100
        
        score = 0.0
        for term in query_terms:
            tf = doc_terms.count(term)
            if tf == 0:
                continue
            
            idf = 1.0
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_length / avg_doc_length))
            score += idf * (numerator / denominator)
        
        return min(score / 10, 1.0)
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between vectors"""
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    
    def _format_results(
        self,
        scored: List[Tuple[RerankCandidate, float]]
    ) -> List[Dict]:
        """Format reranked results for API response"""
        results = []
        
        for candidate, final_score in scored:
            results.append({
                'document_id': candidate.document_id,
                'chunk_id': candidate.chunk_id,
                'filename': candidate.filename,
                'domain': candidate.domain,
                'chunk_index': candidate.chunk_index,
                'similarity': round(candidate.vector_similarity, 3),
                'final_score': round(final_score, 3),
                'quality_score': round(candidate.quality_score, 2) if candidate.quality_score else None,
                'text': candidate.text,
                'chunk_type': candidate.chunk_type,
                'keywords': candidate.keywords,
                'section_title': candidate.section_title,
                'page_number': candidate.page_number,
                'file_url': candidate.file_url
            })
        
        return results