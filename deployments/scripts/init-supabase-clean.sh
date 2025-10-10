#!/bin/bash

# Initialize Supabase PostgreSQL with all required users and schemas
# This ensures a clean start without migration issues

set -e

echo "Initializing Supabase PostgreSQL..."

# Wait for PostgreSQL to be ready
until docker exec isa-postgres pg_isready -U postgres; do
  echo "Waiting for PostgreSQL..."
  sleep 2
done

echo "PostgreSQL is ready. Initializing schemas and users..."

# Create all required schemas and users
docker exec isa-postgres psql -U postgres <<EOF
-- Create schemas
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS storage;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE SCHEMA IF NOT EXISTS graphql_public;
CREATE SCHEMA IF NOT EXISTS _realtime;

-- Create required extensions in extensions schema
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pgjwt SCHEMA extensions;

-- Create users if they don't exist
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supabase_auth_admin') THEN
        CREATE USER supabase_auth_admin WITH PASSWORD 'postgres';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supabase_storage_admin') THEN
        CREATE USER supabase_storage_admin WITH PASSWORD 'postgres';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supabase_admin') THEN
        CREATE USER supabase_admin WITH PASSWORD 'postgres';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticator') THEN
        CREATE USER authenticator WITH PASSWORD 'postgres';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'anon') THEN
        CREATE USER anon WITH PASSWORD 'postgres';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticated') THEN
        CREATE USER authenticated WITH PASSWORD 'postgres';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'service_role') THEN
        CREATE USER service_role WITH PASSWORD 'postgres';
    END IF;
END
\$\$;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA auth TO supabase_auth_admin;
GRANT ALL PRIVILEGES ON SCHEMA storage TO supabase_storage_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO supabase_auth_admin, supabase_storage_admin;
GRANT CREATE ON SCHEMA public TO supabase_auth_admin, supabase_storage_admin;

GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA storage TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA extensions TO anon, authenticated, service_role;

-- Grant permissions on database
GRANT ALL PRIVILEGES ON DATABASE postgres TO supabase_admin;
GRANT CONNECT ON DATABASE postgres TO authenticator, anon, authenticated, service_role;

-- Create required types for auth migrations
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'factor_type' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'auth')) THEN
        CREATE TYPE auth.factor_type AS ENUM ('totp', 'webauthn');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'factor_status' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'auth')) THEN
        CREATE TYPE auth.factor_status AS ENUM ('verified', 'unverified');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'aal_level' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'auth')) THEN
        CREATE TYPE auth.aal_level AS ENUM ('aal1', 'aal2', 'aal3');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'code_challenge_method' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'auth')) THEN
        CREATE TYPE auth.code_challenge_method AS ENUM ('s256', 'plain');
    END IF;
END
\$\$;

-- Set search path for users
ALTER USER supabase_auth_admin SET search_path = auth, public, extensions;
ALTER USER supabase_storage_admin SET search_path = storage, public, extensions;
ALTER USER authenticator SET search_path = public, auth, storage, extensions;

EOF

echo "✅ Supabase PostgreSQL initialized successfully!"