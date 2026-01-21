-- init.sql - Initialize database schema with pgvector

-- Enable pgvector extension (requires superuser)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Domain/Tenant table
CREATE TABLE IF NOT EXISTS domains (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    embedding_model VARCHAR(100) DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    chunk_size INTEGER DEFAULT 512,
    chunk_overlap INTEGER DEFAULT 50,
    metadata JSONB DEFAULT '{}',
    min_similarity_threshold FLOAT DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default domains
INSERT INTO domains (name, description, min_similarity_threshold) VALUES
('general', 'General knowledge base', 0.5),
('medical', 'Healthcare and medical documentation', 0.7),
('legal', 'Legal documents and contracts', 0.75),
('technical', 'Technical documentation and code', 0.65),
('finance', 'Financial reports and analysis', 0.75)
ON CONFLICT (name) DO NOTHING;

-- Documents table (metadata about uploaded files with domain support)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE RESTRICT,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(10) NOT NULL,
    file_size INTEGER NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    minio_object_key VARCHAR(500) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'processing',
    chunk_count INTEGER DEFAULT 0,
    error_message TEXT,
    avg_chunk_quality FLOAT,
    processing_version VARCHAR(20),
    metadata JSONB DEFAULT '{}',
    owner_id VARCHAR(255),
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_status CHECK (status IN ('processing', 'completed', 'failed')),
    CONSTRAINT valid_file_type CHECK (file_type IN ('pdf', 'docx', 'txt', 'md'))
);

-- Document chunks table (text chunks + vector embeddings + semantic metadata)
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE RESTRICT,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    chunk_type VARCHAR(50),
    semantic_density FLOAT,
    key_entities JSONB,
    keywords TEXT[],
    page_number INTEGER,
    section_title TEXT,
    token_count INTEGER,
    quality_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, chunk_index)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain_id);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id) WHERE owner_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);

CREATE INDEX IF NOT EXISTS idx_chunks_domain ON document_chunks(domain_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);
-- Standard index for the metadata filters
CREATE INDEX IF NOT EXISTS idx_chunks_metadata_filter 
ON document_chunks (domain_id, document_id);

-- Vector similarity index (HNSW for fast approximate nearest neighbor search)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Comments for documentation
COMMENT ON TABLE domains IS 'Domain/tenant isolation for multi-domain RAG';
COMMENT ON TABLE documents IS 'Stores metadata for uploaded documents';
COMMENT ON TABLE document_chunks IS 'Stores text chunks with vector embeddings for semantic search';
COMMENT ON COLUMN document_chunks.embedding IS 'Vector embedding (384-dim) using sentence-transformers/all-MiniLM-L6-v2';
COMMENT ON COLUMN document_chunks.page_number IS 'Page number in source document (for PDF citations, NULL for other formats)';
COMMENT ON INDEX idx_chunks_embedding IS 'HNSW index for fast vector similarity search using cosine distance';
