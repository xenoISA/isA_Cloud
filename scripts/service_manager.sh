#!/usr/bin/env bash

# Service Manager for isA Cloud Platform
# Manages all microservices lifecycle

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CLOUD_DIR="$HOME/Documents/Fun/isA_Cloud"
USER_DIR="$HOME/Documents/Fun/isA_user"
MCP_DIR="$HOME/Documents/Fun/isA_MCP"
MODEL_DIR="$HOME/Documents/Fun/isA_Model"
AGENT_DIR="$HOME/Documents/Fun/isA_Agent"
CHAIN_DIR="$HOME/Documents/Fun/isA_Chain"
VENV_PATH="$USER_DIR/.venv"
PID_DIR="/tmp/isa_services"
LOG_DIR="/tmp/isa_services/logs"

# Service names
ALL_SERVICES="consul nats mcp user model agent blockchain gateway"

# Get service command
get_service_cmd() {
    case "$1" in
        consul)
            echo "consul agent -dev -ui -bind 127.0.0.1"
            ;;
        gateway)
            echo "cd $CLOUD_DIR && ./bin/gateway --config deployments/configs/gateway.yaml"
            ;;
        nats)
            echo "docker start isa-cloud-nats-1 isa-cloud-nats-2 isa-cloud-nats-3"
            ;;
        mcp)
            # Start MCP server directly without the wrapper script that has 'wait'
            echo "cd $MCP_DIR && source .venv/bin/activate && export \$(cat deployment/dev/.env | grep -v '^#' | xargs) && python smart_mcp_server.py --port 8081"
            ;;
        user)
            # User service needs to run within its virtual environment
            echo "cd $USER_DIR && source .venv/bin/activate && bash scripts/start_all_services.sh"
            ;;
        model)
            echo "cd $MODEL_DIR/deployment/scripts && bash start.sh local"
            ;;
        agent)
            echo "cd $AGENT_DIR/deployment/scripts && bash start.sh local"
            ;;
        blockchain)
            echo "cd $CHAIN_DIR && bash scripts/start-services.sh"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Get service port
get_service_port() {
    case "$1" in
        consul) echo "8500" ;;
        gateway) echo "8000" ;;
        nats) echo "4222" ;;
        mcp) echo "8081" ;;
        user) echo "8201" ;;
        model) echo "8082" ;;
        agent) echo "8080" ;;
        blockchain) echo "8545" ;;  # Hardhat node RPC port
        *) echo "" ;;
    esac
}

# Initialize directories
init_dirs() {
    mkdir -p "$PID_DIR"
    mkdir -p "$LOG_DIR"
}

# Register service with Consul
register_with_consul() {
    local service=$1
    local register_script=""
    local consul_pid_file="$PID_DIR/consul_${service}.pid"
    
    # Find the appropriate register_consul.py script
    case "$service" in
        mcp)
            register_script="$MCP_DIR/register_consul.py"
            ;;
        model)
            register_script="$MODEL_DIR/register_consul.py"
            ;;
        agent)
            register_script="$AGENT_DIR/register_consul.py"
            ;;
        *)
            return 0
            ;;
    esac
    
    # Check if register script exists
    if [ ! -f "$register_script" ]; then
        echo -e "${YELLOW}⚠ Consul registration script not found for $service${NC}"
        return 1
    fi
    
    # Check if already registered
    if [ -f "$consul_pid_file" ]; then
        local consul_pid=$(cat "$consul_pid_file")
        if ps -p "$consul_pid" > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠ $service already registered with Consul (PID: $consul_pid)${NC}"
            return 0
        fi
    fi
    
    # Register with Consul
    echo -e "${GREEN}Registering $service with Consul...${NC}"
    (cd $(dirname "$register_script") && nohup python3 "$register_script" > "$LOG_DIR/consul_${service}.log" 2>&1) &
    local consul_pid=$!
    
    # Save Consul registration PID
    echo $consul_pid > "$consul_pid_file"
    
    # Wait a moment for registration to complete
    sleep 2
    
    # Check if registration is running
    if ps -p "$consul_pid" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $service registered with Consul (Registration PID: $consul_pid)${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠ Consul registration may have failed for $service${NC}"
        rm -f "$consul_pid_file"
        return 1
    fi
}

# Start a service
start_service() {
    local service=$1
    local cmd=$(get_service_cmd "$service")
    local pid_file="$PID_DIR/$service.pid"
    local log_file="$LOG_DIR/$service.log"
    
    # Check if service is already running
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${YELLOW}Service $service is already running (PID: $pid)${NC}"
            return 0
        fi
    fi
    
    # Check if service port is already in use
    # For gateway, clean up any stale processes before starting
    if [[ "$service" == "gateway" ]]; then
        local existing_pids=$(pgrep -f "gateway --config" 2>/dev/null)
        if [ -n "$existing_pids" ]; then
            echo -e "${YELLOW}Found existing gateway processes, cleaning up...${NC}"
            pkill -f "gateway --config" 2>/dev/null || true
            sleep 2
        fi
    fi
    
    local port=$(get_service_port "$service")
    if [ -n "$port" ]; then
        if lsof -i:$port > /dev/null 2>&1; then
            # For gateway, if port is in use, kill the process and continue
            if [[ "$service" == "gateway" ]]; then
                echo -e "${YELLOW}Port $port is in use, cleaning up for gateway restart...${NC}"
                local blocking_pid=$(lsof -ti:$port)
                if [ -n "$blocking_pid" ]; then
                    kill -TERM $blocking_pid 2>/dev/null || true
                    sleep 2
                fi
            else
                echo -e "${YELLOW}Service $service is already running on port $port${NC}"
                # Try to find the PID and save it
                local service_pid=$(lsof -ti:$port | head -1)
                if [ -n "$service_pid" ]; then
                    echo "$service_pid" > "$pid_file"
                    echo -e "${GREEN}✓ Detected existing $service process (PID: $service_pid)${NC}"
                fi
                return 0
            fi
        fi
    fi
    
    echo -e "${GREEN}Starting $service...${NC}"
    
    # Special handling for services that need environment
    if [[ "$service" == "gateway" ]]; then
        # Build gateway first if needed
        (cd "$CLOUD_DIR" && go build -o bin/gateway ./cmd/gateway)
    fi
    
    # Special handling for NATS (Docker containers)
    if [[ "$service" == "nats" ]]; then
        # Start NATS containers
        docker start isa-cloud-nats-1 isa-cloud-nats-2 isa-cloud-nats-3
        sleep 2
        # Check if containers are running
        if docker ps | grep -q "isa-cloud-nats-1"; then
            echo -e "${GREEN}✓ NATS containers started successfully${NC}"
            # Save a fake PID for consistency
            echo "docker" > "$pid_file"
            return 0
        else
            echo -e "${RED}✗ Failed to start NATS containers${NC}"
            return 1
        fi
    fi
    
    
    # Start the service - need to handle working directory for some services
    if [[ "$service" == "model" ]]; then
        (cd "$MODEL_DIR" && nohup bash -c "./deployment/scripts/start.sh local" > "$log_file" 2>&1) &
        local pid=$!
    elif [[ "$service" == "agent" ]]; then
        (cd "$AGENT_DIR" && nohup bash -c "./deployment/scripts/start.sh local" > "$log_file" 2>&1) &
        local pid=$!
    elif [[ "$service" == "blockchain" ]]; then
        # Auto-select option 1 (Hardhat) for non-interactive startup
        (cd "$CHAIN_DIR" && nohup bash -c "echo '1' | ./scripts/start-services.sh" > "$log_file" 2>&1) &
        local pid=$!
    else
        nohup bash -c "$cmd" > "$log_file" 2>&1 &
        local pid=$!
    fi
    
    # Save PID
    echo $pid > "$pid_file"
    
    # Wait a moment for service to start
    sleep 2
    
    # Check if service started successfully
    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $service started successfully (PID: $pid)${NC}"
        
        # Register AI services with Consul
        if [[ "$service" == "mcp" ]] || [[ "$service" == "model" ]] || [[ "$service" == "agent" ]]; then
            register_with_consul "$service"
        fi
        
        return 0
    else
        echo -e "${RED}✗ Failed to start $service${NC}"
        rm -f "$pid_file"
        return 1
    fi
}

# Stop a service
stop_service() {
    local service=$1
    local pid_file="$PID_DIR/$service.pid"
    
    # Special handling for NATS (Docker containers)
    if [[ "$service" == "nats" ]]; then
        echo -e "${GREEN}Stopping NATS containers...${NC}"
        docker stop isa-cloud-nats-1 isa-cloud-nats-2 isa-cloud-nats-3
        rm -f "$pid_file"
        echo -e "${GREEN}✓ NATS containers stopped${NC}"
        return 0
    fi
    
    if [ ! -f "$pid_file" ]; then
        echo -e "${YELLOW}Service $service is not running${NC}"
        return 0
    fi
    
    local pid=$(cat "$pid_file")
    
    # Stop Consul registration for AI services
    if [[ "$service" == "mcp" ]] || [[ "$service" == "model" ]] || [[ "$service" == "agent" ]]; then
        local consul_pid_file="$PID_DIR/consul_${service}.pid"
        if [ -f "$consul_pid_file" ]; then
            local consul_pid=$(cat "$consul_pid_file")
            if ps -p "$consul_pid" > /dev/null 2>&1; then
                echo -e "${GREEN}Stopping Consul registration for $service...${NC}"
                kill "$consul_pid" 2>/dev/null || true
                rm -f "$consul_pid_file"
            fi
        fi
    fi
    
    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${GREEN}Stopping $service (PID: $pid)...${NC}"
        kill -TERM "$pid" 2>/dev/null || true
        
        # Wait for process to stop
        local count=0
        while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done
        
        # Force kill if still running
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        
        echo -e "${GREEN}✓ $service stopped${NC}"
    else
        echo -e "${YELLOW}Service $service was not running${NC}"
    fi
    
    # For gateway, also kill any other gateway processes that might be running
    if [[ "$service" == "gateway" ]]; then
        echo -e "${GREEN}Checking for other gateway processes...${NC}"
        local gateway_pids=$(pgrep -f "gateway --config" 2>/dev/null)
        if [ -n "$gateway_pids" ]; then
            echo -e "${GREEN}Found additional gateway processes, stopping them...${NC}"
            for gpid in $gateway_pids; do
                if [ "$gpid" != "$pid" ]; then
                    kill -TERM "$gpid" 2>/dev/null || true
                    echo -e "${GREEN}Stopped gateway process (PID: $gpid)${NC}"
                fi
            done
            sleep 1
            # Force kill any remaining
            pkill -9 -f "gateway --config" 2>/dev/null || true
        fi
    fi
    
    rm -f "$pid_file"
}

# Check service status
check_service() {
    local service=$1
    local pid_file="$PID_DIR/$service.pid"
    local port=$(get_service_port "$service")
    
    # Special handling for NATS (Docker containers)
    if [[ "$service" == "nats" ]]; then
        if docker ps | grep -q "isa-cloud-nats-1"; then
            echo -e "${GREEN}✓ $service: Running (Docker containers, Port: $port)${NC}"
            return 0
        else
            echo -e "${RED}✗ $service: Docker containers not running${NC}"
            return 1
        fi
    fi
    
    if [ ! -f "$pid_file" ]; then
        echo -e "${RED}✗ $service: Not running${NC}"
        return 1
    fi
    
    local pid=$(cat "$pid_file")
    
    if ! ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${RED}✗ $service: Process not found (PID: $pid)${NC}"
        rm -f "$pid_file"
        return 1
    fi
    
    # Check if port is listening
    if [ -n "$port" ]; then
        if lsof -i:$port > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $service: Running (PID: $pid, Port: $port)${NC}"
        else
            echo -e "${YELLOW}⚠ $service: Running but port $port not listening (PID: $pid)${NC}"
        fi
    else
        echo -e "${GREEN}✓ $service: Running (PID: $pid)${NC}"
    fi
    
    return 0
}

# Start all services
start_all() {
    echo -e "${GREEN}Starting all services...${NC}"
    
    # Start Consul first
    start_service "consul"
    sleep 3
    
    # Start NATS
    start_service "nats"
    sleep 2
    
    # Start blockchain
    start_service "blockchain"
    sleep 3
    
    # Start MCP service
    start_service "mcp"
    sleep 2
    
    # Start user services
    start_service "user"
    sleep 2
    
    # Start model service
    start_service "model"
    sleep 2
    
    # Start agent service
    start_service "agent"
    sleep 2
    
    # Start gateway last
    start_service "gateway"
    
    echo -e "${GREEN}All services started${NC}"
}

# Stop all services
stop_all() {
    echo -e "${GREEN}Stopping all services...${NC}"
    
    # Stop gateway first
    stop_service "gateway"
    
    # Stop agent
    stop_service "agent"
    
    # Stop model
    stop_service "model"
    
    # Stop user services
    stop_service "user"
    
    # Stop MCP
    stop_service "mcp"
    
    # Stop blockchain
    stop_service "blockchain"
    
    # Stop NATS
    stop_service "nats"
    
    # Stop Consul last
    stop_service "consul"
    
    echo -e "${GREEN}All services stopped${NC}"
}

# Check all services status
status_all() {
    echo -e "${GREEN}Service Status:${NC}"
    echo "------------------------"
    
    for service in $ALL_SERVICES; do
        check_service "$service"
    done
    
    echo "------------------------"
}

# Restart a service
restart_service() {
    local service=$1
    stop_service "$service"
    sleep 1
    start_service "$service"
}

# View logs
view_logs() {
    local service=$1
    local log_file="$LOG_DIR/$service.log"
    
    if [ ! -f "$log_file" ]; then
        echo -e "${RED}No logs found for $service${NC}"
        return 1
    fi
    
    tail -f "$log_file"
}

# Health check
health_check() {
    echo -e "${GREEN}Performing health check...${NC}"
    
    # Check Consul
    if curl -s http://localhost:8500/v1/status/leader > /dev/null; then
        echo -e "${GREEN}✓ Consul is healthy${NC}"
        
        # List registered services
        echo -e "\n${GREEN}Registered services in Consul:${NC}"
        curl -s http://localhost:8500/v1/catalog/services | jq -r 'keys[]' | grep -v consul
    else
        echo -e "${RED}✗ Consul is not responding${NC}"
    fi
    
    # Check Gateway
    if curl -s http://localhost:8000/health > /dev/null; then
        echo -e "${GREEN}✓ Gateway is healthy${NC}"
    else
        echo -e "${RED}✗ Gateway is not responding${NC}"
    fi
}

# Main menu
show_help() {
    echo "isA Cloud Service Manager"
    echo ""
    echo "Usage: $0 [command] [service]"
    echo ""
    echo "Commands:"
    echo "  start [service]    Start a specific service (or 'all' for all services)"
    echo "  stop [service]     Stop a specific service (or 'all' for all services)"
    echo "  restart [service]  Restart a specific service (or 'all' for all services)"
    echo "  status             Show status of all services"
    echo "  logs [service]     View logs for a specific service"
    echo "  health             Perform health check"
    echo "  help               Show this help message"
    echo ""
    echo "Available services:"
    echo "  consul, gateway, account, auth, authorization, audit, notification, payment, storage"
    echo ""
    echo "Examples:"
    echo "  $0 start all       # Start all services"
    echo "  $0 stop gateway    # Stop gateway service"
    echo "  $0 restart auth    # Restart auth service"
    echo "  $0 status          # Show status of all services"
    echo "  $0 logs account    # View account service logs"
}

# Main logic
main() {
    init_dirs
    
    case "$1" in
        start)
            if [ "$2" == "all" ]; then
                start_all
            elif [ -n "$2" ] && [ -n "$(get_service_cmd "$2")" ]; then
                start_service "$2"
            else
                echo -e "${RED}Invalid service: $2${NC}"
                show_help
            fi
            ;;
        stop)
            if [ "$2" == "all" ]; then
                stop_all
            elif [ -n "$2" ] && [ -n "$(get_service_cmd "$2")" ]; then
                stop_service "$2"
            else
                echo -e "${RED}Invalid service: $2${NC}"
                show_help
            fi
            ;;
        restart)
            if [ "$2" == "all" ]; then
                stop_all
                sleep 2
                start_all
            elif [ -n "$2" ] && [ -n "$(get_service_cmd "$2")" ]; then
                restart_service "$2"
            else
                echo -e "${RED}Invalid service: $2${NC}"
                show_help
            fi
            ;;
        status)
            status_all
            ;;
        logs)
            if [ -n "$2" ] && [ -n "${SERVICES[$2]}" ]; then
                view_logs "$2"
            else
                echo -e "${RED}Invalid service: $2${NC}"
                show_help
            fi
            ;;
        health)
            health_check
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}Invalid command: $1${NC}"
            show_help
            ;;
    esac
}

# Run main function
main "$@"