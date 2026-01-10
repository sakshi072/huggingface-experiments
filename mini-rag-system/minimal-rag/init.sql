-- init.sql - Initialize database schema with pgvector

-- Enable pgvector extension (requires superuser)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Documents table (metadata about uploaded files)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- File information
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(10) NOT NULL,
    file_size INTEGER NOT NULL,
    minio_object_key VARCHAR(500) NOT NULL UNIQUE,
    
    -- Processing status
    status VARCHAR(20) NOT NULL DEFAULT 'processing',
    chunk_count INTEGER DEFAULT 0,
    error_message TEXT,
    
    -- Parsed metadata (JSON - pages, author, etc.)
    metadata JSONB,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('processing', 'completed', 'failed')),
    CONSTRAINT valid_file_type CHECK (file_type IN ('pdf', 'docx', 'txt', 'md'))
);

-- Document chunks table (text chunks + vector embeddings)
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Foreign key to documents
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Chunk content
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    
    -- Vector embedding (384 dimensions for sentence-transformers/all-MiniLM-L6-v2)
    embedding vector(384) NOT NULL,
    
    -- Citation information
    page_number INTEGER,  -- NULL for non-PDF documents
    
    -- Metadata
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique constraint
    UNIQUE(document_id, chunk_index)
);

-- Indexes for performance

-- Documents indexes
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents(file_type);

-- Chunks indexes
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page_number ON document_chunks(page_number) WHERE page_number IS NOT NULL;

-- Vector similarity index (HNSW for fast approximate nearest neighbor search)
-- This is the key index for semantic search!
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Comments for documentation
COMMENT ON TABLE documents IS 'Stores metadata for uploaded documents';
COMMENT ON TABLE document_chunks IS 'Stores text chunks with vector embeddings for semantic search';
COMMENT ON COLUMN document_chunks.embedding IS 'Vector embedding (384-dim) using sentence-transformers/all-MiniLM-L6-v2';
COMMENT ON COLUMN document_chunks.page_number IS 'Page number in source document (for PDF citations, NULL for other formats)';
COMMENT ON INDEX idx_chunks_embedding IS 'HNSW index for fast vector similarity search using cosine distance';