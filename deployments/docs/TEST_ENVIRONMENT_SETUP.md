# Test Environment Setup Guide

## Overview
This document describes the automated setup process for the isA Platform test environment with full Supabase integration.

## Quick Start

```bash
# 1. Start Postgres
docker-compose -f compose/base.yml -f compose/data-stores.yml --env-file .env.test up -d postgres

# 2. Wait for Postgres to be healthy (10-15 seconds)
docker-compose -f compose/base.yml -f compose/data-stores.yml --env-file .env.test ps

# 3. Initialize database schemas
./scripts/init-test-schema.sh

# 4. Start Supabase services
docker-compose -f compose/base.yml -f compose/data-stores.yml --env-file .env.test up -d
```

## What Gets Automated

The `init-test-schema.sh` script now handles **ALL** the manual setup that was previously required:

### Step 1-2: Database Creation
- Creates `isa_platform`, `isa_mcp`, `isa_model`, `isa_agent`, `isa_user` databases
- Creates `supabase_admin` superuser role

### Step 3: PostgreSQL Extensions
- Enables `vector`, `pg_trgm`, `btree_gin` for all databases

### Step 4: Schema Migration from Dev
- Exports dev Supabase schema structure (no data)
- Renames `dev` schema to `test` schema (critical for test environment)
- Applies to `isa_platform` database
- Results: **129 tables** in test schema

### Step 5: Supabase Service Users
Creates all required Supabase users with proper permissions:
- `supabase_auth_admin` - Auth service
- `supabase_storage_admin` - Storage service
- `supabase_admin` - Main admin
- `authenticator` - API authentication
- `anon` - Anonymous access
- `service_role` - Service role access

### Step 6: **NEW** Supabase System Schemas
Creates all required system schemas with proper ownership:
- `auth` (owned by supabase_auth_admin)
- `storage` (owned by supabase_storage_admin)
- `_realtime` (owned by supabase_admin)
- `supabase_functions`, `_analytics`, `graphql`, `graphql_public`

Grants proper USAGE permissions to `anon`, `authenticated`, `service_role`.

### Step 7: **NEW** Enum Type Migration
Automatically moves enum types from `public` to `auth` schema:
- `factor_type` → `auth.factor_type`
- `factor_status` → `auth.factor_status`

This fixes the Auth service migration errors.

### Step 8: **NEW** Migration Cleanup
Drops stale `public.schema_migrations` table to allow fresh Supabase migrations.

### Step 9: Verification
Verifies all databases are accessible and counts tables.

## Docker Compose Fixes

All environment configuration is now in `compose/data-stores.yml`:

### Realtime Service
Added required environment variables:
```yaml
RLIMIT_NOFILE: "1048576"  # File descriptor limit
APP_NAME: realtime         # Application name
```

### Internal Port Configuration
All Supabase services use internal port `5432` for Postgres:
```yaml
# NOT ${POSTGRES_PORT} which would be 15432 (external)
DB_PORT: 5432  # Internal container network
```

### Studio Healthcheck
Added proper healthcheck for Studio service:
```yaml
healthcheck:
  test: ["CMD", "node", "-e", "require('http').get('http://localhost:3000/api/profile', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

## Port Configuration

### External Ports (Host → Container)
Test environment uses **1xxxx** range to avoid conflicts with dev:
```
15432 → postgres:5432
15321 → kong:8000 (HTTP API)
15322 → kong:8443 (HTTPS API)
13323 → studio:3000
```

### Internal Ports (Container → Container)
Services communicate via internal Docker network on standard ports:
```
postgres:5432
kong:8000
auth:9999
realtime:4000
storage:5000
rest:3000
meta:8080
```

## Environment Variables

Key variables in `.env.test`:

```bash
# Database
POSTGRES_DB=isa_platform  # NOT isa_db
POSTGRES_PORT=15432       # External port only

# Supabase
SUPABASE_API_EXTERNAL_URL=http://localhost:15321
SUPABASE_KONG_HTTP_PORT=15321
SUPABASE_KONG_HTTPS_PORT=15322

# JWT
JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long-test-env
```

## Service Startup Order

1. **Postgres** starts first (base layer)
2. **Init script** runs after Postgres is healthy
3. **Supabase Auth** starts and runs migrations
4. **Supabase Realtime** starts and runs migrations
5. **Supabase Storage** starts
6. **Supabase REST, Kong, Meta, Studio** start

## Verification

Check all services are healthy:
```bash
docker-compose -f compose/base.yml -f compose/data-stores.yml --env-file .env.test ps
```

Expected output:
- ✅ postgres: healthy
- ✅ supabase-auth: up
- ✅ supabase-realtime: up
- ✅ supabase-storage: up
- ✅ supabase-rest: up
- ✅ supabase-kong: healthy
- ✅ supabase-meta: healthy
- ✅ supabase-studio: healthy

## Testing Setup

Access services:
```bash
# Postgres
psql -h 127.0.0.1 -p 15432 -U postgres -d isa_platform

# Supabase API (via Kong)
curl http://localhost:15321/rest/v1/

# Studio UI
open http://localhost:13323
```

## Troubleshooting

### Auth Service Restarting
Check if `auth` schema exists and `factor_type` enum is in auth schema:
```sql
SELECT schemaname FROM pg_tables WHERE schemaname = 'auth';
SELECT n.nspname, t.typname
FROM pg_type t
JOIN pg_namespace n ON t.typnamespace = n.oid
WHERE t.typname IN ('factor_type', 'factor_status');
```

### Realtime Service Restarting
Check environment variables are set:
```bash
docker exec isa-supabase-realtime env | grep -E "(RLIMIT|APP_NAME)"
```

### Storage Service Restarting
Check `storage` schema exists and permissions are correct.

## Reset Environment

To start fresh:
```bash
# Stop all services
docker-compose -f compose/base.yml -f compose/data-stores.yml --env-file .env.test down -v

# Remove volumes (WARNING: deletes all data)
docker volume rm $(docker volume ls -q | grep isa)

# Start fresh
# Follow Quick Start steps
```

## What Changed From Manual Setup

Previously required manual commands (now automated):

1. ❌ Manual schema creation: `CREATE SCHEMA auth`
2. ❌ Manual enum migration: `ALTER TYPE public.factor_type SET SCHEMA auth`
3. ❌ Manual migration cleanup: `DROP TABLE public.schema_migrations`
4. ❌ Manual permission grants for each schema
5. ❌ Manual environment variable fixes in compose files

Now all handled by:
- ✅ `scripts/init-test-schema.sh` (steps 1-3)
- ✅ `compose/data-stores.yml` (steps 4-5)

## Summary

**Before:** ~15 manual SQL commands + 5 compose file edits required for each setup

**After:** 4 bash commands for complete automated setup

All fixes are persistent and reusable for future test environment deployments.
