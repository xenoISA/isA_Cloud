#!/bin/bash
# ============================================
# isA Platform - Test Environment (Phased Startup)
# ============================================
# Phased startup approach matching dev environment workflow

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DEPLOY_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Load environment variables
if [ -f .env.test ]; then
    set -a
    source .env.test
    set +a
fi

# Compose file paths
COMPOSE_FILES="-f compose/base.yml \
-f compose/infrastructure.yml \
-f compose/data-stores.yml \
-f compose/data-stores-test.yml \
-f compose/observability.yml \
-f compose/services.yml \
-f docker-compose.test.infrastructure-overrides.yml \
-f docker-compose.test.services-overrides.yml"

show_help() {
    echo -e "${BLUE}isA Platform - Test Environment${NC}"
    echo ""
    echo "Usage: $0 {command}"
    echo ""
    echo "Commands:"
    echo "  ${GREEN}infrastructure${NC}  - Start only infrastructure (Phase 1)"
    echo "  ${GREEN}verify${NC}          - Verify infrastructure health (Phase 2)"
    echo "  ${GREEN}schema${NC}          - Initialize database schemas (Phase 3)"
    echo "  ${GREEN}services${NC}        - Start core services (Phase 4)"
    echo "  ${GREEN}up${NC}              - Complete phased startup (all phases)"
    echo ""
    echo "  ${YELLOW}all${NC}             - Start everything at once (not recommended)"
    echo ""
    echo "  ${RED}down${NC}            - Stop all services"
    echo "  ${RED}clean${NC}           - Stop and remove volumes"
    echo "  restart         - Restart services"
    echo "  logs [service]  - Show logs"
    echo "  ps              - Show running containers"
    echo "  status          - Show detailed status"
    echo ""
}

show_urls() {
    echo ""
    echo -e "${BLUE}📊 Service URLs (Test Ports):${NC}"
    echo ""
    echo -e "${BLUE}Infrastructure:${NC}"
    echo "  - Consul:   http://localhost:18500"
    echo "  - Grafana:  http://localhost:13003 (admin/admin)"
    echo "  - Loki:     http://localhost:13100"
    echo ""
    echo -e "${BLUE}Databases:${NC}"
    echo "  - Postgres: localhost:15432 (postgres/postgres)"
    echo "  - Redis:    localhost:16379"
    echo "  - MinIO:    http://localhost:19001 (minioadmin/minioadmin)"
    echo "  - Neo4j:    http://localhost:17474"
    echo "  - MQTT:     localhost:11883"
    echo ""
    echo -e "${BLUE}Supabase (Local - test schema):${NC}"
    echo "  - API Gateway:    http://localhost:54321"
    echo "  - Studio:         http://localhost:54323"
    echo "  - DB:             postgresql://postgres:postgres@localhost:54322/postgres?options=-c%20search_path=test"
    echo ""
    echo -e "${BLUE}Core Services:${NC}"
    echo "  - Gateway:  http://localhost:18000"
    echo "  - MCP:      http://localhost:18081"
    echo "  - Model:    http://localhost:18082"
    echo "  - Agent:    http://localhost:18083"
    echo ""
}

start_infrastructure() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}Phase 1: Starting Infrastructure${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    # Start Supabase Local (shared with dev, using test schema)
    echo "📦 Starting Supabase Local (test schema)..."
    CONFIGS_DIR="$DEPLOY_DIR/configs/dev"

    if ! supabase status --workdir "$CONFIGS_DIR" 2>/dev/null | grep -q "supabase local development setup is running"; then
        echo "   Starting Supabase..."
        cd "$CONFIGS_DIR" && supabase start
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}   ✅ Supabase Local started (shared with dev, test schema available)${NC}"
        else
            echo -e "${RED}   ✗ Failed to start Supabase Local${NC}"
        fi
        cd "$DEPLOY_DIR"
    else
        echo -e "${GREEN}   ✅ Supabase Local is already running${NC}"
    fi
    echo ""

    echo "📦 Building and starting Docker infrastructure services..."
    echo "   - Service Discovery: Consul, NATS cluster"
    echo "   - Databases: Redis, MinIO, Neo4j, InfluxDB, Mosquitto"
    echo "   - Observability: Loki, Grafana, Promtail"
    echo ""

    docker-compose \
        -f compose/base.yml \
        -f compose/infrastructure.yml \
        -f compose/data-stores.yml \
        -f compose/data-stores-test.yml \
        -f compose/observability.yml \
        -f docker-compose.test.infrastructure-overrides.yml \
        up -d --build

    echo ""
    echo -e "${GREEN}✅ Infrastructure started!${NC}"
    show_urls
    echo -e "${BLUE}Next steps:${NC}"
    echo "  1. Verify health: ${GREEN}./scripts/start-test.sh verify${NC}"
    echo "  2. Initialize schemas: ${GREEN}./scripts/start-test.sh schema${NC}"
    echo "  3. Start services: ${GREEN}./scripts/start-test.sh services${NC}"
    echo ""
}

verify_infrastructure() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}Phase 2: Verifying Infrastructure${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    "$SCRIPT_DIR/verify-test-infra.sh"
}

init_schema() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}Phase 3: Initializing Database Schemas${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    "$SCRIPT_DIR/init-test-schema.sh"
}

start_services() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}Phase 4: Starting Core Services${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    echo "📦 Building and starting core services..."
    echo "   - Gateway"
    echo "   - AI Services: MCP, Model, Agent"
    echo "   - User Microservices"
    echo ""

    docker-compose \
        -f compose/base.yml \
        -f compose/infrastructure.yml \
        -f compose/data-stores.yml \
        -f compose/data-stores-test.yml \
        -f compose/observability.yml \
        -f compose/services.yml \
        -f docker-compose.test.infrastructure-overrides.yml \
        -f docker-compose.test.services-overrides.yml \
        up -d --build

    echo ""
    echo -e "${GREEN}✅ Core services started!${NC}"
    show_urls
    echo ""
    echo -e "${BLUE}💡 Useful commands:${NC}"
    echo "  - Check logs: ${GREEN}./scripts/start-test.sh logs [service]${NC}"
    echo "  - Check status: ${GREEN}./scripts/start-test.sh ps${NC}"
    echo ""
}

phased_startup() {
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  isA Platform - Phased Test Startup   ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""

    # Phase 1: Infrastructure
    start_infrastructure

    # Wait for infrastructure to stabilize
    echo -e "${YELLOW}⏳ Waiting 10 seconds for infrastructure to stabilize...${NC}"
    sleep 10

    # Phase 2: Verify
    verify_infrastructure

    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}⚠️  Infrastructure verification had warnings, but continuing startup...${NC}"
        echo ""
    fi

    # Phase 3: Schema
    init_schema

    # Phase 4: Services
    start_services

    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   ✅ Test Environment Ready!           ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
}

start_all() {
    echo "🧪 Starting isA Platform - Test Environment (All at once)"
    echo "⚠️  Note: Phased startup is recommended for better reliability"
    echo ""
    docker-compose -f docker-compose.test.yml up -d --build
    echo ""
    echo -e "${GREEN}✅ Test environment started!${NC}"
    show_urls
}

stop_services() {
    echo "🛑 Stopping services..."
    docker-compose $COMPOSE_FILES down
    echo -e "${GREEN}✅ Stopped!${NC}"
}

clean_all() {
    echo "🧹 Cleaning up (removing volumes)..."
    docker-compose $COMPOSE_FILES down -v
    echo -e "${GREEN}✅ Cleaned!${NC}"
}

restart_services() {
    echo "🔄 Restarting services..."
    docker-compose $COMPOSE_FILES restart
    echo -e "${GREEN}✅ Restarted!${NC}"
}

show_logs() {
    docker-compose $COMPOSE_FILES logs -f ${1:-}
}

show_ps() {
    docker-compose $COMPOSE_FILES ps
}

show_status() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}Test Environment Status${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    echo -e "${BLUE}All Services:${NC}"
    docker-compose $COMPOSE_FILES ps

    show_urls
}

# Main command router
case "${1:-help}" in
    infrastructure|infra)
        start_infrastructure
        ;;
    verify|check)
        verify_infrastructure
        ;;
    schema|init)
        init_schema
        ;;
    services|apps)
        start_services
        ;;
    up|start)
        phased_startup
        ;;
    all|full)
        start_all
        ;;
    down|stop)
        stop_services
        ;;
    clean|cleanup)
        clean_all
        ;;
    restart)
        restart_services
        ;;
    logs)
        show_logs $2
        ;;
    ps|containers)
        show_ps
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
