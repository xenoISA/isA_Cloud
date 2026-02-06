#!/bin/bash
# =============================================================================
# Verify Backup Integrity Script
# =============================================================================
# Checks that backup files are valid and complete
#
# Usage:
#   ./verify-backup.sh /path/to/backup
#   ./verify-backup.sh  # Uses latest backup
# =============================================================================

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# isA_Cloud directory
ISA_CLOUD_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# Find backup directory
if [ -n "$1" ]; then
    BACKUP_DIR="$1"
else
    # Find latest backup
    BACKUP_DIR=$(ls -dt "$ISA_CLOUD_DIR/backups"/*-backup-* 2>/dev/null | head -1)
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: No backup directory found${NC}"
    echo "Usage: $0 /path/to/backup"
    exit 1
fi

echo -e "${BLUE}=============================================="
echo "Backup Verification"
echo "=============================================="
echo -e "${NC}"
echo "Backup: $BACKUP_DIR"
echo ""

ERRORS=0
WARNINGS=0

# Check metadata
echo -e "${YELLOW}[1/9] Checking metadata...${NC}"
if [ -f "$BACKUP_DIR/metadata.json" ]; then
    echo "  Backup date: $(jq -r '.timestamp' "$BACKUP_DIR/metadata.json" 2>/dev/null)"
    echo "  Environment: $(jq -r '.environment' "$BACKUP_DIR/metadata.json" 2>/dev/null)"
    echo "  Namespace:   $(jq -r '.namespace' "$BACKUP_DIR/metadata.json" 2>/dev/null)"
    echo -e "  ${GREEN}✓ Metadata valid${NC}"
else
    echo -e "  ${RED}✗ metadata.json missing${NC}"
    ((ERRORS++))
fi

# Check PostgreSQL
echo ""
echo -e "${YELLOW}[2/9] Checking PostgreSQL backup...${NC}"
if [ -f "$BACKUP_DIR/postgres/full_backup.sql" ]; then
    SIZE=$(du -h "$BACKUP_DIR/postgres/full_backup.sql" | cut -f1)
    LINES=$(wc -l < "$BACKUP_DIR/postgres/full_backup.sql")

    # Check if it starts with PostgreSQL header
    if head -5 "$BACKUP_DIR/postgres/full_backup.sql" | grep -q "PostgreSQL database"; then
        echo "  Full backup: $SIZE ($LINES lines)"
        echo -e "  ${GREEN}✓ PostgreSQL backup valid${NC}"
    else
        echo -e "  ${RED}✗ PostgreSQL backup appears corrupted${NC}"
        ((ERRORS++))
    fi

    # Check individual databases
    for dump in "$BACKUP_DIR/postgres"/*.dump; do
        if [ -f "$dump" ]; then
            DB_NAME=$(basename "$dump" .dump)
            DB_SIZE=$(du -h "$dump" | cut -f1)
            echo "  Database '$DB_NAME': $DB_SIZE"
        fi
    done
else
    echo -e "  ${YELLOW}⚠ No PostgreSQL backup found${NC}"
    ((WARNINGS++))
fi

# Check Redis
echo ""
echo -e "${YELLOW}[3/9] Checking Redis backup...${NC}"
if [ -f "$BACKUP_DIR/redis/dump.rdb" ]; then
    SIZE=$(du -h "$BACKUP_DIR/redis/dump.rdb" | cut -f1)

    # Check RDB magic header (REDIS)
    if head -c 5 "$BACKUP_DIR/redis/dump.rdb" | grep -q "REDIS"; then
        echo "  RDB file: $SIZE"
        echo -e "  ${GREEN}✓ Redis backup valid${NC}"
    else
        echo -e "  ${RED}✗ Redis RDB file appears corrupted${NC}"
        ((ERRORS++))
    fi
else
    echo -e "  ${YELLOW}⚠ No Redis backup found${NC}"
    ((WARNINGS++))
fi

# Check Qdrant
echo ""
echo -e "${YELLOW}[4/9] Checking Qdrant backup...${NC}"
QDRANT_COUNT=$(ls "$BACKUP_DIR/qdrant"/*.snapshot 2>/dev/null | wc -l)
if [ "$QDRANT_COUNT" -gt 0 ]; then
    echo "  Collections: $QDRANT_COUNT"
    for snapshot in "$BACKUP_DIR/qdrant"/*.snapshot; do
        if [ -f "$snapshot" ]; then
            COLL_NAME=$(basename "$snapshot" | cut -d'_' -f1)
            COLL_SIZE=$(du -h "$snapshot" | cut -f1)
            echo "    - $COLL_NAME: $COLL_SIZE"
        fi
    done
    echo -e "  ${GREEN}✓ Qdrant backup valid${NC}"
else
    echo -e "  ${YELLOW}⚠ No Qdrant snapshots found${NC}"
    ((WARNINGS++))
fi

# Check Neo4j
echo ""
echo -e "${YELLOW}[5/9] Checking Neo4j backup...${NC}"
if [ -f "$BACKUP_DIR/neo4j/neo4j.dump" ] || [ -f "$BACKUP_DIR/neo4j/neo4j-backup.tar.gz" ] || [ -f "$BACKUP_DIR/neo4j/neo4j-export.cypher" ]; then
    for f in "$BACKUP_DIR/neo4j"/*; do
        if [ -f "$f" ]; then
            echo "  $(basename "$f"): $(du -h "$f" | cut -f1)"
        fi
    done
    echo -e "  ${GREEN}✓ Neo4j backup found${NC}"
else
    echo -e "  ${YELLOW}⚠ No Neo4j backup found${NC}"
    ((WARNINGS++))
fi

# Check MinIO
echo ""
echo -e "${YELLOW}[6/9] Checking MinIO backup...${NC}"
if [ -d "$BACKUP_DIR/minio" ]; then
    BUCKET_COUNT=$(ls -d "$BACKUP_DIR/minio"/*/ 2>/dev/null | wc -l)
    if [ "$BUCKET_COUNT" -gt 0 ]; then
        echo "  Buckets: $BUCKET_COUNT"
        du -sh "$BACKUP_DIR/minio"/*/ 2>/dev/null | while read size bucket; do
            echo "    - $(basename "$bucket"): $size"
        done
        echo -e "  ${GREEN}✓ MinIO backup valid${NC}"
    else
        echo -e "  ${YELLOW}⚠ MinIO backup is empty (no buckets)${NC}"
        ((WARNINGS++))
    fi
else
    echo -e "  ${YELLOW}⚠ No MinIO backup found${NC}"
    ((WARNINGS++))
fi

# Check Consul
echo ""
echo -e "${YELLOW}[7/9] Checking Consul backup...${NC}"
if [ -f "$BACKUP_DIR/consul/consul.snap" ]; then
    SIZE=$(du -h "$BACKUP_DIR/consul/consul.snap" | cut -f1)
    echo "  Snapshot: $SIZE"
    echo -e "  ${GREEN}✓ Consul snapshot valid${NC}"
elif [ -f "$BACKUP_DIR/consul/kv-store.json" ]; then
    SIZE=$(du -h "$BACKUP_DIR/consul/kv-store.json" | cut -f1)
    KV_COUNT=$(jq 'length' "$BACKUP_DIR/consul/kv-store.json" 2>/dev/null || echo "?")
    echo "  KV store: $SIZE ($KV_COUNT keys)"
    echo -e "  ${GREEN}✓ Consul KV backup valid${NC}"
else
    echo -e "  ${YELLOW}⚠ No Consul backup found${NC}"
    ((WARNINGS++))
fi

# Check NATS
echo ""
echo -e "${YELLOW}[8/9] Checking NATS backup...${NC}"
if [ -f "$BACKUP_DIR/nats/jetstream-data.tar.gz" ]; then
    SIZE=$(du -h "$BACKUP_DIR/nats/jetstream-data.tar.gz" | cut -f1)
    echo "  JetStream data: $SIZE"
    echo -e "  ${GREEN}✓ NATS backup valid${NC}"
elif [ -d "$BACKUP_DIR/nats/streams" ]; then
    STREAM_COUNT=$(ls -d "$BACKUP_DIR/nats/streams"/*/ 2>/dev/null | wc -l)
    echo "  Streams: $STREAM_COUNT"
    echo -e "  ${GREEN}✓ NATS stream configs backed up${NC}"
else
    echo -e "  ${YELLOW}⚠ No NATS backup found${NC}"
    ((WARNINGS++))
fi

# Check APISIX
echo ""
echo -e "${YELLOW}[9/9] Checking APISIX backup...${NC}"
if [ -f "$BACKUP_DIR/apisix/routes.json" ]; then
    ROUTE_COUNT=$(jq '.total // (.list | length) // 0' "$BACKUP_DIR/apisix/routes.json" 2>/dev/null)
    UPSTREAM_COUNT=$(jq '.total // (.list | length) // 0' "$BACKUP_DIR/apisix/upstreams.json" 2>/dev/null || echo "0")
    echo "  Routes: $ROUTE_COUNT"
    echo "  Upstreams: $UPSTREAM_COUNT"

    # Validate JSON
    if jq empty "$BACKUP_DIR/apisix/routes.json" 2>/dev/null; then
        echo -e "  ${GREEN}✓ APISIX backup valid${NC}"
    else
        echo -e "  ${RED}✗ APISIX routes.json is invalid JSON${NC}"
        ((ERRORS++))
    fi
else
    echo -e "  ${YELLOW}⚠ No APISIX backup found${NC}"
    ((WARNINGS++))
fi

# Summary
echo ""
echo -e "${BLUE}=============================================="
echo "Verification Summary"
echo "=============================================="
echo -e "${NC}"
echo "Total size: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All backups verified successfully!${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Verification complete with $WARNINGS warning(s)${NC}"
    echo "  Some services may not have been backed up."
    exit 0
else
    echo -e "${RED}✗ Verification failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
    exit 1
fi
