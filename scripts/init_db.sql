-- scripts/init_db.sql
--
-- WHY THIS FILE:
-- This runs automatically when PostgreSQL container first starts.
-- It sets up extensions and initial configuration that SQLAlchemy
-- migrations cannot handle (because extensions require superuser privileges).
--
-- pgvector: adds vector similarity search to PostgreSQL.
-- We use it for storing and searching medication embeddings.

-- Enable the pgvector extension
-- CREATE EXTENSION IF NOT EXISTS: safe to run multiple times
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation (used for primary keys)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for fuzzy text search (drug name matching with typos)
-- This powers the "did you mean ibuprofen?" feature when users misspell drug names
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Log that setup completed
DO $$
BEGIN
    RAISE NOTICE 'Pillara database extensions initialized successfully';
END $$;