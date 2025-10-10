-- Enable pgvector extension for vector embeddings
-- This is required for all embedding tables in the MCP system

-- Enable the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- Enable RLS (Row Level Security) by default
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;

-- Add comment for tracking
COMMENT ON EXTENSION vector IS 'pgvector extension for MCP embedding tables - enabled 2025-07-02';