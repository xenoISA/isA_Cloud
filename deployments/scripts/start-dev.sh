#!/bin/bash
# ============================================
# isA Platform - Development Environment (Brew)
# ============================================
# Manages all infrastructure services via Homebrew
# No Docker required for dev environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
CONFIGS_DIR="$DEPLOY_DIR/configs/dev"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Required brew services (Database uses Supabase Local via CLI)
REQUIRED_SERVICES=(
    "redis"
    "minio"
    "consul"
    "nats-server"
    "neo4j"
    "influxdb"
    "mosquitto"
    "loki"
    "grafana"
    "promtail"
)

print_header() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}  isA Platform - Development Environment (Brew)${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo ""
}

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Homebrew is installed
check_brew() {
    if ! command -v brew &> /dev/null; then
        print_error "Homebrew is not installed!"
        echo "Install from: https://brew.sh"
        exit 1
    fi
    print_info "✅ Homebrew installed"
}

# Check if required services are installed
check_services() {
    print_info "Checking required services..."
    local missing=()

    for service in "${REQUIRED_SERVICES[@]}"; do
        if ! brew list --formula | grep -q "^${service}$"; then
            missing+=("$service")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        print_warn "Missing services:"
        for service in "${missing[@]}"; do
            echo "  - $service"
        done
        echo ""
        read -p "Install missing services? (yes/no): " confirm
        if [ "$confirm" == "yes" ]; then
            for service in "${missing[@]}"; do
                print_info "Installing $service..."
                brew install "$service"
            done
        else
            print_error "Cannot start without required services"
            exit 1
        fi
    else
        print_info "✅ All services installed"
    fi
}

# Start all services
start_services() {
    print_info "Starting infrastructure services..."
    echo ""

    # Supabase (via CLI - separate process)
    print_info "Starting Supabase Local..."
    SUPABASE_DIR="$CONFIGS_DIR/supabase"

    if ! supabase status --workdir "$CONFIGS_DIR" 2>/dev/null | grep -q "supabase local development setup is running"; then
        print_info "  Starting Supabase..."
        cd "$CONFIGS_DIR" && supabase start
        if [ $? -eq 0 ]; then
            print_info "✅ Supabase Local started successfully (dev schema)"
        else
            print_error "Failed to start Supabase Local"
        fi
        cd "$DEPLOY_DIR"
    else
        print_info "✅ Supabase Local is already running"
    fi

    # Redis
    print_info "Starting Redis..."
    brew services start redis

    # MinIO (requires manual start with config)
    print_info "Starting MinIO..."
    if ! pgrep -f "minio server" > /dev/null; then
        mkdir -p ~/minio-data
        export MINIO_ROOT_USER=minioadmin
        export MINIO_ROOT_PASSWORD=minioadmin
        nohup minio server ~/minio-data --console-address ":9001" > /tmp/minio.log 2>&1 &
        sleep 2
    fi

    # Consul
    print_info "Starting Consul..."
    if ! pgrep -f "consul agent" > /dev/null; then
        nohup consul agent -dev -ui -client=0.0.0.0 > /tmp/consul.log 2>&1 &
        sleep 2
    fi

    # NATS
    print_info "Starting NATS..."
    if ! pgrep -f "nats-server" > /dev/null; then
        nohup nats-server -p 4222 > /tmp/nats.log 2>&1 &
        sleep 2
    fi

    # Neo4j
    print_info "Starting Neo4j..."
    brew services start neo4j

    # InfluxDB
    print_info "Starting InfluxDB..."
    brew services start influxdb

    # Mosquitto
    print_info "Starting Mosquitto..."
    brew services start mosquitto

    # Loki (with brew config)
    print_info "Starting Loki..."
    LOKI_CONFIG="$CONFIGS_DIR/loki-local.yml"
    if [ -f "$LOKI_CONFIG" ]; then
        # Stop brew service if running
        brew services stop loki 2>/dev/null || true
        # Start with custom config
        nohup loki -config.file="$LOKI_CONFIG" > /tmp/loki.log 2>&1 &
        sleep 2
        print_info "  Loki started with custom config"
    else
        brew services start loki
    fi

    # Promtail
    print_info "Starting Promtail..."
    if [ -f "$CONFIGS_DIR/promtail.yml" ]; then
        nohup promtail -config.file="$CONFIGS_DIR/promtail.yml" > /tmp/promtail.log 2>&1 &
        sleep 2
    else
        brew services start promtail
    fi

    # Grafana (with Loki datasource provisioning)
    print_info "Starting Grafana..."

    # Ensure Loki datasource is configured
    GRAFANA_PROVISIONING_DIR="/opt/homebrew/opt/grafana/share/grafana/conf/provisioning/datasources"
    LOKI_DATASOURCE_CONFIG="$CONFIGS_DIR/grafana-datasource-loki.yml"

    if [ -f "$LOKI_DATASOURCE_CONFIG" ]; then
        mkdir -p "$GRAFANA_PROVISIONING_DIR"
        cp "$LOKI_DATASOURCE_CONFIG" "$GRAFANA_PROVISIONING_DIR/loki.yml"
        print_info "  Loki datasource configured"
    fi

    brew services start grafana

    echo ""
    print_info "✅ All services started!"
}

# Stop all services
stop_services() {
    print_info "Stopping infrastructure services..."
    echo ""

    # Stop Supabase Local
    print_info "Stopping Supabase Local..."
    if supabase status --workdir "$CONFIGS_DIR" 2>/dev/null | grep -q "supabase local development setup is running"; then
        cd "$CONFIGS_DIR" && supabase stop
        print_info "  Supabase stopped"
        cd "$DEPLOY_DIR"
    fi

    # Stop brew services
    brew services stop redis
    brew services stop neo4j
    brew services stop influxdb
    brew services stop mosquitto
    brew services stop grafana
    brew services stop loki
    brew services stop promtail

    # Stop manually started services
    pkill -f "minio server" 2>/dev/null || true
    pkill -f "consul agent" 2>/dev/null || true
    pkill -f "nats-server" 2>/dev/null || true

    print_info "✅ All services stopped!"
}

# Show service status
show_status() {
    print_header

    echo -e "${BLUE}Brew Services Status:${NC}"
    brew services list | grep -E "(redis|neo4j|mosquitto|grafana|loki|promtail)" || true

    # Check InfluxDB separately (may not be in brew services if not installed)
    if brew list influxdb &>/dev/null; then
        brew services list | grep "influxdb" || true
    fi
    echo ""

    echo -e "${BLUE}Supabase Status:${NC}"
    CURRENT_DIR="$(pwd)"

    cd "$CONFIGS_DIR" > /dev/null 2>&1
    if supabase status 2>&1 | grep -q "is running"; then
        echo -e "  Supabase:   ${GREEN}Running${NC} (dev schema)"
    else
        echo -e "  Supabase:   ${RED}Stopped${NC} (Start with: cd $CONFIGS_DIR && supabase start)"
    fi
    cd "$CURRENT_DIR" > /dev/null 2>&1
    echo ""

    echo -e "${BLUE}Manual Services Status:${NC}"
    echo -n "MinIO:    "
    pgrep -f "minio server" > /dev/null && echo -e "${GREEN}Running${NC}" || echo -e "${RED}Stopped${NC}"
    echo -n "Consul:   "
    pgrep -f "consul agent" > /dev/null && echo -e "${GREEN}Running${NC}" || echo -e "${RED}Stopped${NC}"
    echo -n "NATS:     "
    pgrep -f "nats-server" > /dev/null && echo -e "${GREEN}Running${NC}" || echo -e "${RED}Stopped${NC}"
    echo -n "InfluxDB: "
    pgrep -f influxd > /dev/null && echo -e "${GREEN}Running${NC}" || echo -e "${RED}Stopped${NC}"
    echo ""

    echo -e "${BLUE}Service URLs:${NC}"
    echo "  - Supabase Studio:  http://127.0.0.1:54321"
    echo "  - PostgreSQL:       127.0.0.1:54322 (postgres/postgres)"
    echo "  - Consul:           http://localhost:8500"
    echo "  - Grafana:          http://localhost:3000 (admin/admin)"
    echo "  - Loki:             http://localhost:3100"
    echo "  - Redis:            localhost:6379"
    echo "  - MinIO Console:    http://localhost:9001 (minioadmin/minioadmin)"
    echo "  - MinIO API:        http://localhost:9000"
    echo "  - Neo4j Browser:    http://localhost:7474 (neo4j/neo4j)"
    echo "  - Neo4j Bolt:       bolt://localhost:7687"
    echo "  - InfluxDB:         http://localhost:8086"
    echo "  - MQTT:             mqtt://localhost:1883"
    echo "  - NATS:             nats://localhost:4222"
    echo ""
}

# Main
print_header
check_brew

case "${1:-status}" in
    start|up)
        check_services
        start_services
        show_status
        echo ""
        echo -e "${BLUE}================================================${NC}"
        print_info "💡 Next Steps - Start Application Services:"
        echo ""
        echo "  1. MCP Service (Port 8081):"
        echo "     cd ~/Documents/Fun/isA_MCP && ./deployment/scripts/start.sh"
        echo ""
        echo "  2. Model Service (Port 8082):"
        echo "     cd ~/Documents/Fun/isA_Model && ./deployment/scripts/start.sh"
        echo ""
        echo "  3. Agent Service (Port 8083):"
        echo "     cd ~/Documents/Fun/isA_Agent && ./deployment/scripts/start.sh"
        echo ""
        echo "  4. User Services (Ports 8200+):"
        echo "     cd ~/Documents/Fun/isA_user && ./deployment/scripts/start_user_service.sh"
        echo ""
        echo "  Or start Gateway to access all services:"
        echo "     cd ~/Documents/Fun/isA_Cloud && go run cmd/gateway/main.go"
        echo ""
        echo -e "${BLUE}================================================${NC}"
        ;;
    stop|down)
        stop_services
        ;;
    restart)
        stop_services
        sleep 2
        start_services
        show_status
        ;;
    status|ps)
        show_status
        ;;
    install)
        check_services
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|install}"
        echo ""
        echo "Commands:"
        echo "  start    - Start all brew services"
        echo "  stop     - Stop all brew services"
        echo "  restart  - Restart all brew services"
        echo "  status   - Show service status"
        echo "  install  - Install missing services"
        exit 1
        ;;
esac
