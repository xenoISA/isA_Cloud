-- Consolidated Schema Migration
-- Generated from current dev schema state
-- This migration can be applied to any schema (test, staging, production)
-- 
-- Usage: Replace SCHEMA_NAME with target schema before applying
-- e.g., sed 's/SCHEMA_NAME/test/g' this_file.sql | psql

-- Function to create complete schema structure
CREATE OR REPLACE FUNCTION create_complete_schema(schema_name TEXT) RETURNS VOID AS $$
BEGIN
    -- Ensure schema exists
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', schema_name);
    
    -- Grant permissions
    EXECUTE format('GRANT ALL ON SCHEMA %I TO postgres', schema_name);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO anon, authenticated', schema_name);
    
    -- Set search path for this function
    EXECUTE format('SET search_path TO %I, public', schema_name);
    
    -- Create sequences
    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I.carts_id_seq', schema_name);
    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I.events_id_seq', schema_name);
    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I.sessions_id_seq', schema_name);
    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I.users_id_seq', schema_name);
    -- Add other sequences as needed
    
    -- Create core tables
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.users (
            id INTEGER NOT NULL DEFAULT nextval(''%I.users_id_seq''::regclass) PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            is_active BOOLEAN DEFAULT TRUE,
            metadata JSONB DEFAULT ''{}''::jsonb
        )', schema_name, schema_name);
    
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.sessions (
            id INTEGER NOT NULL DEFAULT nextval(''%I.sessions_id_seq''::regclass) PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            user_id INTEGER REFERENCES %I.users(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE,
            metadata JSONB DEFAULT ''{}''::jsonb
        )', schema_name, schema_name, schema_name);
    
    -- Add indexes
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%I_users_email ON %I.users(email)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%I_sessions_user_id ON %I.sessions(user_id)', schema_name, schema_name);
    
    -- Reset search path
    RESET search_path;
END;
$$ LANGUAGE plpgsql;

-- This migration file is a template
-- To use it, call: SELECT create_complete_schema('target_schema_name');