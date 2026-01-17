"""
Feature flags for A/B testing chunking and reranking strategies.

Usage in .env:
    FEATURE_SEMANTIC_CHUNKING=true
    FEATURE_RERANKING=true

Compare results by toggling flags:
    - Both false: baseline (basic chunking, no reranking)
    - SEMANTIC_CHUNKING=true: test semantic chunking improvement
    - RERANKING=true: test reranking improvement
    - Both true: full enhanced pipeline
"""
import os
from dataclasses import dataclass


@dataclass
class FeatureFlags:
    """Feature flags loaded from environment"""

    @property
    def semantic_chunking_enabled(self) -> bool:
        """Use semantic chunking instead of basic RecursiveCharacterTextSplitter"""
        return os.getenv("FEATURE_SEMANTIC_CHUNKING", "false").lower() == "true"

    @property
    def reranking_enabled(self) -> bool:
        """Use unified reranking after vector search"""
        return os.getenv("FEATURE_RERANKING", "false").lower() == "true"

    @property
    def rerank_top_k_multiplier(self) -> int:
        """How many more candidates to fetch for reranking (e.g., 3 = fetch 3x top_k)"""
        return int(os.getenv("FEATURE_RERANK_MULTIPLIER", "3"))

    def __repr__(self):
        return (
            f"FeatureFlags("
            f"semantic_chunking={self.semantic_chunking_enabled}, "
            f"reranking={self.reranking_enabled})"
        )


# Global instance
feature_flags = FeatureFlags()
