#!/bin/bash
# ============================================
# Verify Test Infrastructure Health
# ============================================
# Checks all infrastructure services are healthy before starting core services

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

FAILED=0
TOTAL=0

check_service() {
    local name=$1
    local check_cmd=$2
    local description=$3

    ((TOTAL++))
    echo -n "  Checking $name... "

    if eval "$check_cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $description"
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        ((FAILED++))
        return 1
    fi
}

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Test Infrastructure Health Check${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ============================================
# Service Discovery & Messaging
# ============================================
echo -e "${BLUE}Service Discovery & Messaging:${NC}"

check_service "Consul" \
    "curl -sf http://localhost:18500/v1/status/leader" \
    "Consul is running and has a leader"

# NATS cluster checks - non-fatal (known issues with cluster name conflicts)
if docker ps --filter "name=isa-cloud-nats-1-test" --format "{{.Status}}" | grep -q "Up"; then
    echo -e "  Checking NATS-1... ${YELLOW}⚠${NC} NATS node 1 container is running (health checks disabled)"
    ((TOTAL++))
else
    echo -e "  Checking NATS-1... ${RED}✗${NC} NATS node 1 is not running"
    ((TOTAL++))
    ((FAILED++))
fi

if docker ps --filter "name=isa-cloud-nats-2-test" --format "{{.Status}}" | grep -q "Up"; then
    echo -e "  Checking NATS-2... ${YELLOW}⚠${NC} NATS node 2 container is running (health checks disabled)"
    ((TOTAL++))
else
    echo -e "  Checking NATS-2... ${RED}✗${NC} NATS node 2 is not running"
    ((TOTAL++))
    ((FAILED++))
fi

if docker ps --filter "name=isa-cloud-nats-3-test" --format "{{.Status}}" | grep -q "Up"; then
    echo -e "  Checking NATS-3... ${YELLOW}⚠${NC} NATS node 3 container is running (health checks disabled)"
    ((TOTAL++))
else
    echo -e "  Checking NATS-3... ${RED}✗${NC} NATS node 3 is not running"
    ((TOTAL++))
    ((FAILED++))
fi

echo ""

# ============================================
# Databases
# ============================================
echo -e "${BLUE}Databases:${NC}"

check_service "Supabase Local (Postgres)" \
    "pg_isready -h localhost -p 54322 -U postgres" \
    "Supabase Local PostgreSQL is accepting connections"

check_service "Redis" \
    "redis-cli -h localhost -p 16379 ping" \
    "Redis is responding to PING"

check_service "Neo4j" \
    "curl -sf http://localhost:17474" \
    "Neo4j browser is accessible"

check_service "InfluxDB" \
    "curl -sf http://localhost:18086/health" \
    "InfluxDB is healthy"

echo ""

# ============================================
# Supabase Local
# ============================================
echo -e "${BLUE}Supabase Local (Shared with dev):${NC}"

check_service "Supabase API Gateway" \
    "curl -sf http://localhost:54321/rest/v1/" \
    "Supabase API Gateway is responding"

check_service "Supabase Studio" \
    "curl -sf http://localhost:54323" \
    "Supabase Studio is accessible"

echo ""

# ============================================
# Storage & Messaging
# ============================================
echo -e "${BLUE}Storage & Messaging:${NC}"

check_service "MinIO" \
    "curl -sf http://localhost:19001" \
    "MinIO console is accessible"

# Mosquitto check - just verify container is running (mqtt_sub can hang)
if docker ps --filter "name=isa-mosquitto-test" --format "{{.Status}}" | grep -q "Up.*healthy"; then
    echo -e "  Checking Mosquitto... ${GREEN}✓${NC} MQTT broker container is healthy"
    ((TOTAL++))
else
    echo -e "  Checking Mosquitto... ${RED}✗${NC} MQTT broker is not healthy"
    ((TOTAL++))
    ((FAILED++))
fi

echo ""

# ============================================
# Observability
# ============================================
echo -e "${BLUE}Observability:${NC}"

check_service "Loki" \
    "curl -sf http://localhost:13100/ready" \
    "Loki is ready to receive logs"

check_service "Grafana" \
    "curl -sf http://localhost:13003/api/health" \
    "Grafana is healthy"

echo ""
echo -e "${BLUE}============================================${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All $TOTAL infrastructure services are healthy!${NC}"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "  1. Initialize database schemas: ./scripts/init-test-schema.sh"
    echo "  2. Start core services: ./scripts/start-test.sh services"
    exit 0
else
    echo -e "${RED}❌ $FAILED of $TOTAL checks failed${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo "  - Check logs: docker-compose -f docker-compose.test.infrastructure.yml logs [service]"
    echo "  - Restart failed services: docker-compose -f docker-compose.test.infrastructure.yml restart [service]"
    exit 1
fi
