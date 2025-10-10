-- Create separate schemas for different environments
-- This allows us to use the same Supabase instance for dev/test/staging

-- Create schemas
CREATE SCHEMA IF NOT EXISTS dev;
CREATE SCHEMA IF NOT EXISTS test;
CREATE SCHEMA IF NOT EXISTS staging;

-- Grant permissions to postgres user
GRANT ALL ON SCHEMA dev TO postgres;
GRANT ALL ON SCHEMA test TO postgres;
GRANT ALL ON SCHEMA staging TO postgres;

-- Grant permissions to anon and authenticated roles
GRANT USAGE ON SCHEMA dev TO anon, authenticated;
GRANT USAGE ON SCHEMA test TO anon, authenticated;
GRANT USAGE ON SCHEMA staging TO anon, authenticated;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA dev GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA test GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL ON TABLES TO postgres;

ALTER DEFAULT PRIVILEGES IN SCHEMA dev GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA test GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;