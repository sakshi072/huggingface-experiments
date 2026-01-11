"""
SQLAlchemy models for PostgreSQL
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, Text, CheckConstraint, Index, ForeignKey, UniqueConstraint, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from database import Base

class Document(Base):
    """
    Document metadata table.
    Stores information about uploaded files.
    """
    __tablename__ = "documents"

    # Primary key
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # File information
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True) # SHA-256 hash
    minio_object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    # Processing status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="processing",
        server_default="processing"
    )
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata from parser (JSON)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp()
    )

    # Relationship to chunks
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan"
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="valid_status"
        ),
        CheckConstraint(
            "file_type IN ('pdf', 'docx', 'txt', 'md')",
            name="valid_file_type"
        ),
        Index("idx_documents_status", "status"),
        Index("idx_documents_created_at", "created_at"),
        Index("idx_documents_filename", "filename"),
        Index("idx_documents_file_type", "file_type"),
    )

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"

class DocumentChunk(Base):
    """
    Document chunks table with vector embeddings.
    Stores text chunks, embeddings, and citation information.
    """
    
    __tablename__ = "document_chunks"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign key to documents
    document_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Chunk content
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Vector embedding (384 dimensions for all-MiniLM-L6-v2)
    embedding: Mapped[list] = mapped_column(Vector(384), nullable=False)
    
    # Citation information
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    # Metadata
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp()
    )

    # Relationship to document
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks"
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="unique_chunk_per_document"),
        Index("idx_chunks_document_id", "document_id"),
        Index("idx_chunks_page_number", "page_number"),
        # HNSW index for vector similarity search (cosine distance)
        Index(
            "idx_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"}
        ),
    )
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"

if __name__ == "__main__":
    """Print model information"""
    print("=" * 60)
    print("SQLAlchemy Models")
    print("=" * 60)
    
    print("\nDocument Model:")
    print(f"  Table: {Document.__tablename__}")
    print(f"  Columns: {list(Document.__table__.columns.keys())}")
    
    print("\nDocumentChunk Model:")
    print(f"  Table: {DocumentChunk.__tablename__}")
    print(f"  Columns: {list(DocumentChunk.__table__.columns.keys())}")
    
    print("\nIndexes:")
    for idx in Document.__table__.indexes:
        print(f"  {idx.name}: {[c.name for c in idx.columns]}")
    for idx in DocumentChunk.__table__.indexes:
        print(f"  {idx.name}: {[c.name for c in idx.columns]}")
    
    print("\nRelationships:")
    print(f"  Document → chunks: {Document.chunks}")
    print(f"  DocumentChunk → document: {DocumentChunk.document}")