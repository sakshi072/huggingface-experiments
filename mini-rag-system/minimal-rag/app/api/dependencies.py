"""
Shared API dependencies
"""
from typing import Optional

from app.services import KnowledgeBase

# Global RAG instance
_rag: Optional[KnowledgeBase] = None


def get_rag() -> Optional[KnowledgeBase]:
    """Get the global RAG instance"""
    return _rag


def set_rag(rag: KnowledgeBase) -> None:
    """Set the global RAG instance"""
    global _rag
    _rag = rag
