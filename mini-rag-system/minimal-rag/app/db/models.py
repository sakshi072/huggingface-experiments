"""
SQLAlchemy models for PostgreSQL
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import (
    String, Integer, Float, Boolean, ARRAY, DateTime,
    Text, CheckConstraint, Index, ForeignKey, UniqueConstraint, JSON, func
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.database import Base


class Domain(Base):
    """Domain/Tenant table for multi-domain Vector Storage and Retrieval System"""
    __tablename__ = "domains"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Domain-specific configuration
    embedding_model: Mapped[str] = mapped_column(String(100), default='sentence-transformers/all-MiniLM-L6-v2')
    chunk_size: Mapped[int] = mapped_column(Integer, default=512)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50)

    # Quality settings
    min_similarity_threshold: Mapped[float] = mapped_column(Float, default=0.5)

    # Additional settings
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    # Relationships
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="domain")
    chunks: Mapped[list["DocumentChunk"]] = relationship("DocumentChunk", back_populates="domain")

    def __repr__(self):
        return f"<Domain(name='{self.name}')>"


class Document(Base):
    """
    Document metadata table.
    Stores information about uploaded files.
    """
    __tablename__ = "documents"

    # Primary key
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    domain_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)

    # File information
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
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

    # Quality metrics
    avg_chunk_quality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    processing_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Metadata from parser (JSON)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON)

    # Access control
    owner_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp()
    )

    # Relationship to chunks
    domain: Mapped["Domain"] = relationship("Domain", back_populates="documents")
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
        Index("idx_documents_domain", "domain_id"),
        Index("idx_documents_owner", "owner_id"),
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
    domain_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)

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

    # Semantic metadata
    chunk_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    semantic_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    key_entities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    keywords: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)

    # Citation information
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    section_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

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
    domain: Mapped["Domain"] = relationship("Domain", back_populates="chunks")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="unique_chunk_per_document"),
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_type", "chunk_type"),
        Index("idx_chunks_domain", "domain_id"),
        Index("idx_chunks_quality", "quality_score"),
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

class SearchAnalytics(Base):
    """
    Search Analytics table 
    Stores Search history with metadata
    """
    __tablename__ = "search_analytics"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_chunk_ids: Mapped[list[UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    similarity_scores: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)

    # Performance metrics
    embedding_time_ms: Mapped[float] = mapped_column(Float, nullable=True)
    search_time_ms: Mapped[float] = mapped_column(Float, nullable=True)
    total_processing_time: Mapped[float] = mapped_column(Float, nullable=True)

    # Metadata
    is_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    def __repr__(self):
        return f"<SearchAnalytics(id={self.id}>"