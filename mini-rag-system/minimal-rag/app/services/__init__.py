"""
Business logic services
"""

import logging
from typing import Dict, List, Optional
from uuid import UUID

from app.db import db_manager
from app.services.ingestion_service import IngestionService
from app.services.search_service import SearchService
from app.utils.reranking_strategy import RerankerConfig, RerankStrategy
from app.schemas import FileUploadResult, UploadStatus
from fastapi import UploadFile
logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    Facade combining ingestion and search services.

    Provides backward-compatible interface for existing API code.
    """

    def __init__(self, reranker_config: Optional[RerankerConfig] = None) -> None:
        """Initialize both services."""
        logger.info("Initializing KnowledgeBase...")

        self._ingestion = IngestionService()
        self._search = SearchService(reranker_config=reranker_config)

        # Initialize database
        db_manager.initialize()

        logger.info("KnowledgeBase ready\n")

    # =========================================================================
    # Ingestion (delegated)
    # =========================================================================

    async def process_single_file(
            self,
            file:UploadFile,
            domain_name:str,
            file_number:int,
            total_files:int
    ) -> FileUploadResult:
        """Process single file"""
        return await self._ingestion.process_single_file(
            file=file,
            domain=domain_name,
            file_number=file_number,
            total_files=total_files,
        )
    
    async def process_files_concurrently(
        self,
        files: List[UploadFile],
        domain:str
    ) -> List[FileUploadResult]:
        """Process batch upload"""
        return await self._ingestion.process_files_concurrently(
            files,
            domain
        )
    
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
        """Ingest document with chunking and embedding."""
        return await self._ingestion.ingest_file(
            file_data=file_data,
            filename=filename,
            file_type=file_type,
            domain_name=domain_name,
            owner_id=owner_id,
            is_public=is_public,
            metadata=metadata,
        )

    # =========================================================================
    # Search (delegated)
    # =========================================================================

    async def search(
        self,
        query_text: str,
        domain_name: Optional[str] = None,
        top_k: int = 5,
        rerank_strategy: RerankStrategy = RerankStrategy.COMBINED,
    ) -> Dict:
        """Search with vector similarity and optional reranking."""
        return await self._search.search(
            query_text=query_text,
            domain_name=domain_name,
            top_k=top_k,
            rerank_strategy=rerank_strategy,
        )
    
    async def search_history(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """List of query search result"""
        return await self._search.get_search_history(limit, offset)
    
    async def get_search_history_by_id(self, search_id:UUID) -> List[Dict]:
        """Query search result"""
        return await self._search.get_search_history_by_id(search_id)

    # =========================================================================
    # Document CRUD (delegated to ingestion service)
    # =========================================================================

    async def get_document(self, document_id: UUID) -> Optional[Dict]:
        """Get document metadata by ID."""
        return await self._ingestion.get_document(document_id)

    async def list_documents(
        self, domain_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """List documents with optional domain filter."""
        return await self._ingestion.list_documents(domain_name=domain_name, limit=limit)

    async def delete_document(self, document_id: UUID) -> bool:
        """Delete a document and its chunks."""
        return await self._ingestion.delete_document(document_id)

    async def get_stats(self) -> Dict:
        """Get system statistics."""
        return await self._ingestion.get_stats()


__all__ = [
    "KnowledgeBase",
    "IngestionService",
    "SearchService",
]
