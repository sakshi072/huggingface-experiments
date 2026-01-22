"""
Database layer - PostgreSQL with pgvector
"""
from app.db.database import db_manager, get_session, startup_database, shutdown_database, Base
from app.db.models import Domain, Document, DocumentChunk, SearchAnalytics

__all__ = [
    "db_manager",
    "get_session",
    "startup_database",
    "shutdown_database",
    "Base",
    "Domain",
    "Document",
    "DocumentChunk",
    "SearchAnalytics"
]
