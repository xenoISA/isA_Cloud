#!/bin/bash
# ============================================
# Initialize Test Environment Database Schemas
# ============================================
# Creates databases and applies schemas from dev Supabase

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Initialize Test Database Schemas${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Database connection details
PGHOST=127.0.0.1
PGPORT=15432
PGUSER=postgres
PGPASSWORD=postgres
export PGPASSWORD

# ============================================
# Step 1: Create Databases
# ============================================
echo -e "${BLUE}Step 1: Creating databases...${NC}"

create_database() {
    local dbname=$1
    echo -n "  Creating database: $dbname... "

    if psql -h $PGHOST -p $PGPORT -U $PGUSER -tc "SELECT 1 FROM pg_database WHERE datname = '$dbname'" | grep -q 1; then
        echo -e "${YELLOW}already exists${NC}"
    else
        psql -h $PGHOST -p $PGPORT -U $PGUSER -c "CREATE DATABASE $dbname;" > /dev/null 2>&1
        echo -e "${GREEN}✓ created${NC}"
    fi
}

create_database "isa_platform"
create_database "isa_mcp"
create_database "isa_model"
create_database "isa_agent"
create_database "isa_user"

echo ""

# ============================================
# Step 2: Create Supabase Admin Role
# ============================================
echo -e "${BLUE}Step 2: Creating supabase_admin role...${NC}"

psql -h $PGHOST -p $PGPORT -U $PGUSER -d postgres -c "
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'supabase_admin') THEN
            CREATE ROLE supabase_admin WITH LOGIN SUPERUSER PASSWORD '$PGPASSWORD';
        END IF;
    END
    \$\$;
" > /dev/null 2>&1

echo -e "  ${GREEN}✓ supabase_admin role created${NC}"
echo ""

# ============================================
# Step 3: Enable Extensions
# ============================================
echo -e "${BLUE}Step 3: Enabling PostgreSQL extensions...${NC}"

enable_extension() {
    local dbname=$1
    local extension=$2
    echo -n "  $dbname: $extension... "

    psql -h $PGHOST -p $PGPORT -U $PGUSER -d $dbname -c "CREATE EXTENSION IF NOT EXISTS $extension;" > /dev/null 2>&1
    echo -e "${GREEN}✓${NC}"
}

# Enable vector extension for all databases
for db in isa_platform isa_mcp isa_model isa_agent isa_user; do
    enable_extension $db "vector"
    enable_extension $db "pg_trgm"
    enable_extension $db "btree_gin"
done

echo ""

# ============================================
# Step 4: Export Dev Schema (if available)
# ============================================
echo -e "${BLUE}Step 4: Exporting schema from dev Supabase...${NC}"

# Direct connection to dev Supabase
DEV_DB_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres?options=-c%20search_path%3Ddev"

# Test connection
if psql "$DEV_DB_URL" -c "SELECT 1" > /dev/null 2>&1; then
    echo "  ✓ Connected to Supabase dev"

    # Count tables in dev schema
    TABLE_COUNT=$(psql "$DEV_DB_URL" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'dev';" 2>/dev/null | tr -d ' ')
    echo "  Found $TABLE_COUNT tables in dev schema"

    SCHEMA_FILE="$DEPLOY_DIR/configs/test/postgres/dev-schema.sql"
    mkdir -p "$(dirname "$SCHEMA_FILE")"

    echo "  Exporting dev schema (structure only, no data)..."
    echo "  Excluding Supabase system schemas (auth, storage, _realtime, etc.)"
    docker exec isa-postgres pg_dump "postgresql://postgres:postgres@host.docker.internal:54322/postgres" \
        --schema=dev \
        --exclude-schema=auth \
        --exclude-schema=storage \
        --exclude-schema=_realtime \
        --exclude-schema=_analytics \
        --exclude-schema=realtime \
        --exclude-schema=supabase_functions \
        --schema-only \
        --no-owner \
        --no-privileges \
        --clean \
        --if-exists \
        > "$SCHEMA_FILE" 2>/dev/null

    echo -e "  ${GREEN}✓ Schema exported to: $SCHEMA_FILE${NC}"

    # Apply schema to isa_platform database (renaming dev -> test)
    echo "  Applying schema to isa_platform (renaming dev -> test)..."

    # First create 'test' schema in test database
    psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "CREATE SCHEMA IF NOT EXISTS test;" > /dev/null 2>&1

    # Apply the schema with dev->test replacement
    sed 's/dev\./test./g' "$SCHEMA_FILE" | psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform > /dev/null 2>&1

    # Count tables in test
    TEST_TABLE_COUNT=$(psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'test';" 2>/dev/null | tr -d ' ')

    echo -e "  ${GREEN}✓ Schema applied ($TEST_TABLE_COUNT tables created)${NC}"
else
    echo -e "  ${YELLOW}⚠ Could not connect to Supabase dev${NC}"
    echo "  Make sure dev Supabase is running: supabase start"
fi

echo ""

# ============================================
# Step 5: Create Additional Supabase Users
# ============================================
echo -e "${BLUE}Step 5: Creating additional Supabase users...${NC}"

create_supabase_user() {
    local username=$1
    local dbname=$2
    echo -n "  Creating user: $username for $dbname... "

    # Create user if not exists
    psql -h $PGHOST -p $PGPORT -U $PGUSER -d postgres -c "
        DO \$\$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$username') THEN
                CREATE USER $username WITH PASSWORD '$PGPASSWORD';
            END IF;
        END
        \$\$;
    " > /dev/null 2>&1

    # Grant privileges
    psql -h $PGHOST -p $PGPORT -U $PGUSER -d $dbname -c "
        GRANT ALL PRIVILEGES ON DATABASE $dbname TO $username;
        GRANT ALL ON SCHEMA public TO $username;
        GRANT ALL ON SCHEMA test TO $username;
        GRANT ALL ON ALL TABLES IN SCHEMA public TO $username;
        GRANT ALL ON ALL TABLES IN SCHEMA test TO $username;
        GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO $username;
        GRANT ALL ON ALL SEQUENCES IN SCHEMA test TO $username;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $username;
        ALTER DEFAULT PRIVILEGES IN SCHEMA test GRANT ALL ON TABLES TO $username;
    " > /dev/null 2>&1

    echo -e "${GREEN}✓${NC}"
}

# Create Supabase service users
create_supabase_user "supabase_auth_admin" "isa_platform"
create_supabase_user "supabase_storage_admin" "isa_platform"
create_supabase_user "supabase_admin" "isa_platform"
create_supabase_user "authenticator" "isa_platform"
create_supabase_user "anon" "isa_platform"
create_supabase_user "service_role" "isa_platform"

echo ""

# ============================================
# Step 6: Create Supabase System Schemas (Fresh)
# ============================================
echo -e "${BLUE}Step 6: Creating Supabase system schemas...${NC}"
echo "  Note: Dropping existing Supabase schemas to ensure fresh state"

echo -n "  Creating auth schema... "
psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
    -- Drop and recreate to ensure fresh state (no stale migrations)
    DROP SCHEMA IF EXISTS auth CASCADE;
    CREATE SCHEMA auth AUTHORIZATION supabase_auth_admin;
    GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
    GRANT ALL ON SCHEMA auth TO supabase_auth_admin;
" > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo -n "  Creating storage schema... "
psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
    DROP SCHEMA IF EXISTS storage CASCADE;
    CREATE SCHEMA storage AUTHORIZATION supabase_storage_admin;
    GRANT USAGE ON SCHEMA storage TO anon, authenticated, service_role;
    GRANT ALL ON SCHEMA storage TO supabase_storage_admin;
" > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo -n "  Creating _realtime schema... "
psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
    DROP SCHEMA IF EXISTS _realtime CASCADE;
    CREATE SCHEMA _realtime AUTHORIZATION supabase_admin;
    GRANT ALL ON SCHEMA _realtime TO supabase_admin;
" > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo -n "  Creating additional Supabase schemas... "
psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
    DROP SCHEMA IF EXISTS supabase_functions CASCADE;
    DROP SCHEMA IF EXISTS _analytics CASCADE;
    DROP SCHEMA IF EXISTS graphql CASCADE;
    DROP SCHEMA IF EXISTS graphql_public CASCADE;
    CREATE SCHEMA supabase_functions;
    CREATE SCHEMA _analytics;
    CREATE SCHEMA graphql;
    CREATE SCHEMA graphql_public;
" > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo ""

# ============================================
# Step 6.5: Pre-mark Problematic Migrations
# ============================================
echo -e "${BLUE}Step 6.5: Pre-marking problematic Supabase Auth migrations...${NC}"

echo -n "  Creating auth.schema_migrations table... "
psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
    CREATE TABLE IF NOT EXISTS auth.schema_migrations (
        version character varying(255) NOT NULL PRIMARY KEY
    );
    GRANT ALL ON auth.schema_migrations TO supabase_auth_admin;
" > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo -n "  Marking migration 20221208132122 (uuid type fix) as complete... "
psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
    INSERT INTO auth.schema_migrations (version)
    VALUES ('20221208132122')
    ON CONFLICT (version) DO NOTHING;
" > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"
echo "  This migration has a type comparison bug (uuid = text) and is safely skipped for fresh installs"

echo ""

# ============================================
# Step 7: Fix Enum Types Location
# ============================================
echo -e "${BLUE}Step 7: Moving enum types to correct schemas...${NC}"

echo -n "  Checking for factor_type and factor_status enums... "
# Check if enums exist in public schema and move to auth
FACTOR_TYPE_EXISTS=$(psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -t -c "
    SELECT COUNT(*) FROM pg_type t
    JOIN pg_namespace n ON t.typnamespace = n.oid
    WHERE n.nspname = 'public' AND t.typname IN ('factor_type', 'factor_status');
" 2>/dev/null | tr -d ' ')

if [ "$FACTOR_TYPE_EXISTS" -gt 0 ]; then
    psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
        ALTER TYPE public.factor_type SET SCHEMA auth;
        ALTER TYPE public.factor_status SET SCHEMA auth;
    " > /dev/null 2>&1
    echo -e "${GREEN}✓ moved to auth schema${NC}"
else
    echo -e "${YELLOW}✓ not found (will be created by migrations)${NC}"
fi

echo ""

# ============================================
# Step 8: Clean Up Stale Migration Tables
# ============================================
echo -e "${BLUE}Step 8: Cleaning up stale migration tables...${NC}"

echo -n "  Dropping public.schema_migrations if exists... "
psql -h $PGHOST -p $PGPORT -U $PGUSER -d isa_platform -c "
    DROP TABLE IF EXISTS public.schema_migrations CASCADE;
" > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo ""

# ============================================
# Step 9: Verify Databases
# ============================================
echo -e "${BLUE}Step 9: Verifying databases...${NC}"

verify_database() {
    local dbname=$1
    echo -n "  $dbname: "

    if psql -h $PGHOST -p $PGPORT -U $PGUSER -d $dbname -c "SELECT 1;" > /dev/null 2>&1; then
        # Check for tables
        table_count=$(psql -h $PGHOST -p $PGPORT -U $PGUSER -d $dbname -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')

        if [ "$table_count" -gt 0 ]; then
            echo -e "${GREEN}✓ ($table_count tables)${NC}"
        else
            echo -e "${YELLOW}✓ (no tables yet)${NC}"
        fi
    else
        echo -e "${RED}✗ connection failed${NC}"
    fi
}

verify_database "isa_platform"
verify_database "isa_mcp"
verify_database "isa_model"
verify_database "isa_agent"
verify_database "isa_user"

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}✅ Database initialization complete!${NC}"
echo ""
echo -e "${BLUE}Database Connection Info:${NC}"
echo "  Host:     $PGHOST"
echo "  Port:     $PGPORT"
echo "  User:     $PGUSER"
echo "  Password: $PGPASSWORD"
echo ""
echo -e "${BLUE}Databases created:${NC}"
echo "  - isa_platform  (main platform schema)"
echo "  - isa_mcp       (MCP service)"
echo "  - isa_model     (Model service)"
echo "  - isa_agent     (Agent service)"
echo "  - isa_user      (User microservices)"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Start core services: ./scripts/start-test.sh services"
echo "  2. Check service health: docker-compose -f docker-compose.test.services.yml ps"
echo ""
