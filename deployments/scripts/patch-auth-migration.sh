#!/bin/bash
# ============================================
# Patch Supabase Auth Migration Bug
# ============================================
# Fixes the uuid = text comparison bug in migration 20221208132122

set -e

echo "🔧 Patching Supabase Auth migration file..."

# Stop the auth container if running
docker stop isa-supabase-auth-test 2>/dev/null || true
docker rm isa-supabase-auth-test 2>/dev/null || true

# Start a temporary container as root to patch the migration file
docker run --name auth-patcher -d --user root --entrypoint /bin/sh public.ecr.aws/supabase/gotrue:v2.176.1 -c "sleep 3600"

# Copy migration file out, patch it, and copy back
echo "Extracting migration file..."
docker cp auth-patcher:/usr/local/etc/auth/migrations/20221208132122_backfill_email_last_sign_in_at.up.sql /tmp/migration.sql

echo "Patching migration file..."
sed -i.bak 's/id = user_id::text/id = user_id/g' /tmp/migration.sql

echo "Verifying patch..."
grep "id = user_id" /tmp/migration.sql

echo "Copying patched file back..."
docker cp /tmp/migration.sql auth-patcher:/usr/local/etc/auth/migrations/20221208132122_backfill_email_last_sign_in_at.up.sql

# Commit the patched container as a new image
docker commit auth-patcher isa-supabase-gotrue:v2.176.1-patched

# Clean up
docker stop auth-patcher
docker rm auth-patcher

echo "✅ Patch complete! New image: isa-supabase-gotrue:v2.176.1-patched"
echo "Now update docker-compose to use this image"
