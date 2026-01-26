-- create_user.sql - Create rag_user and grant permissions

-- Create rag_user
CREATE USER rag_user WITH PASSWORD 'rag_password';

-- Grant all privileges on database
GRANT ALL PRIVILEGES ON DATABASE retrieval_db TO rag_user;

-- Grant schema permissions
GRANT ALL PRIVILEGES ON SCHEMA public TO rag_user;

-- Grant permissions on all existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO rag_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO rag_user;

-- Grant permissions on future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO rag_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO rag_user;