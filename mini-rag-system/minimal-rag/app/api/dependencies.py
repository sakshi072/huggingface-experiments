"""
Shared API dependencies
"""
from typing import Optional

from app.services import KnowledgeBase

# Global Vector Storage and Retrieval instance
_vectore_storage_retrieval: Optional[KnowledgeBase] = None


def get_vectore_storage_retrieval() -> Optional[KnowledgeBase]:
    """Get the global Vector Storage and Retrieval instance"""
    return _vectore_storage_retrieval


def set_vectore_storage_retrieval(vectore_storage_retrieval: KnowledgeBase) -> None:
    """Set the global Vector Storage and Retrieval instance"""
    global _vectore_storage_retrieval
    _vectore_storage_retrieval = vectore_storage_retrieval
