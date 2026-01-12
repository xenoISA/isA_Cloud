#!/bin/bash

# Port-forward infrastructure services only (gRPC gateways + databases + monitoring)
# Lighter-weight alternative to port-forward.sh for development

NAMESPACE="isa-cloud-staging"

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Infrastructure ports only
PORTS=(
    50051 50052 50053 50054 50055 50056 50061 50062 50063  # gRPC gateways
    5432 6379 9000 9001 4222 1883 7474 7687 6333 8500 2379  # Infrastructure
    3000 3100 9090  # Monitoring (Grafana, Loki, APISIX Dashboard)
)

# Kill existing port-forwards for this namespace
echo -e "${YELLOW}Cleaning up existing port-forwards...${NC}"
EXISTING=$(pgrep -f "kubectl port-forward -n $NAMESPACE" 2>/dev/null)
if [ -n "$EXISTING" ]; then
    echo -e "${RED}Found existing kubectl port-forwards, killing them...${NC}"
    pkill -f "kubectl port-forward -n $NAMESPACE" 2>/dev/null
    sleep 1
    echo -e "${GREEN}Existing kubectl port-forwards killed${NC}"
else
    echo -e "${GREEN}No existing kubectl port-forwards found${NC}"
fi

# Kill any process occupying our target ports
echo -e "${YELLOW}Checking for processes using target ports...${NC}"
KILLED_PORTS=()
SKIPPED_PORTS=()
for port in "${PORTS[@]}"; do
    PIDS=$(lsof -ti tcp:$port 2>/dev/null)
    if [ -n "$PIDS" ]; then
        for PID in $PIDS; do
            PROC_CMD=$(ps -p $PID -o comm= 2>/dev/null)
            PROC_ARGS=$(ps -p $PID -o args= 2>/dev/null)

            # Skip critical processes
            if [[ "$PROC_CMD" == "kubectl" && "$PROC_ARGS" == *"proxy"* ]]; then
                SKIPPED_PORTS+=($port)
                continue
            fi
            if [[ "$PROC_ARGS" == *"kube"* && "$PROC_ARGS" == *"proxy"* ]]; then
                SKIPPED_PORTS+=($port)
                continue
            fi
            if [[ "$PROC_ARGS" == *"Docker"* ]] || [[ "$PROC_ARGS" == *"docker"* ]] || [[ "$PROC_CMD" == *"docker"* ]] || [[ "$PROC_CMD" == "com.docker"* ]]; then
                SKIPPED_PORTS+=($port)
                continue
            fi

            echo -e "${RED}Port $port is in use by PID $PID ($PROC_CMD), killing...${NC}"
            kill -9 $PID 2>/dev/null
            KILLED_PORTS+=($port)
        done
    fi
done

if [ ${#KILLED_PORTS[@]} -gt 0 ]; then
    echo -e "${GREEN}Killed processes on ports: ${KILLED_PORTS[*]}${NC}"
    sleep 1
fi

echo -e "\n${GREEN}Starting port-forward for infrastructure services...${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all port-forwards${NC}\n"

# Array to store background process IDs
PIDS=()

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Stopping all port-forwards...${NC}"
    for pid in "${PIDS[@]}"; do
        kill $pid 2>/dev/null
    done
    echo -e "${GREEN}All port-forwards stopped${NC}"
    exit 0
}

trap cleanup INT TERM

COUNT=0

# ==========================================
# gRPC Gateway Services (50051-50063)
# ==========================================
echo -e "${BLUE}=== gRPC Gateway Services ===${NC}"

echo -e "${GREEN}[gRPC] MinIO gRPC (localhost:50051)${NC}"
kubectl port-forward -n $NAMESPACE svc/minio-grpc 50051:50051 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] DuckDB gRPC (localhost:50052)${NC}"
kubectl port-forward -n $NAMESPACE svc/duckdb-grpc 50052:50052 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] MQTT gRPC (localhost:50053)${NC}"
kubectl port-forward -n $NAMESPACE svc/mqtt-grpc 50053:50053 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] Loki gRPC (localhost:50054)${NC}"
kubectl port-forward -n $NAMESPACE svc/loki-grpc 50054:50054 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] Redis gRPC (localhost:50055)${NC}"
kubectl port-forward -n $NAMESPACE svc/redis-grpc 50055:50055 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] NATS gRPC (localhost:50056)${NC}"
kubectl port-forward -n $NAMESPACE svc/nats-grpc 50056:50056 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] PostgreSQL gRPC (localhost:50061)${NC}"
kubectl port-forward -n $NAMESPACE svc/postgres-grpc 50061:50061 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] Qdrant gRPC (localhost:50062)${NC}"
kubectl port-forward -n $NAMESPACE svc/qdrant-grpc 50062:50062 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[gRPC] Neo4j gRPC (localhost:50063)${NC}"
kubectl port-forward -n $NAMESPACE svc/neo4j-grpc 50063:50063 &
PIDS+=($!)
((COUNT++))

# ==========================================
# Infrastructure Services
# ==========================================
echo -e "\n${BLUE}=== Infrastructure Services ===${NC}"

echo -e "${GREEN}[Infra] PostgreSQL (localhost:5432)${NC}"
kubectl port-forward -n $NAMESPACE svc/postgres 5432:5432 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] Redis (localhost:6379)${NC}"
kubectl port-forward -n $NAMESPACE svc/redis 6379:6379 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] MinIO API (localhost:9000)${NC}"
kubectl port-forward -n $NAMESPACE svc/minio 9000:9000 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] MinIO Console (localhost:9001)${NC}"
kubectl port-forward -n $NAMESPACE svc/minio 9001:9001 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] NATS (localhost:4222)${NC}"
kubectl port-forward -n $NAMESPACE svc/nats 4222:4222 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] Mosquitto MQTT (localhost:1883)${NC}"
kubectl port-forward -n $NAMESPACE svc/mosquitto 1883:1883 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] Neo4j Browser (localhost:7474)${NC}"
kubectl port-forward -n $NAMESPACE svc/neo4j 7474:7474 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] Neo4j Bolt (localhost:7687)${NC}"
kubectl port-forward -n $NAMESPACE svc/neo4j 7687:7687 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] Qdrant (localhost:6333)${NC}"
kubectl port-forward -n $NAMESPACE svc/qdrant 6333:6333 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] Consul (localhost:8500)${NC}"
kubectl port-forward -n $NAMESPACE svc/consul 8500:8500 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Infra] etcd (localhost:2379)${NC}"
kubectl port-forward -n $NAMESPACE svc/etcd 2379:2379 &
PIDS+=($!)
((COUNT++))

# ==========================================
# Monitoring Services
# ==========================================
echo -e "\n${BLUE}=== Monitoring Services ===${NC}"

echo -e "${GREEN}[Monitor] Grafana (localhost:3000)${NC}"
kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Monitor] Loki (localhost:3100)${NC}"
kubectl port-forward -n $NAMESPACE svc/loki 3100:3100 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Monitor] APISIX Dashboard (localhost:9090)${NC}"
kubectl port-forward -n $NAMESPACE svc/apisix-dashboard 9090:9000 &
PIDS+=($!)
((COUNT++))

# Wait for port-forwards to establish
sleep 2

echo -e "\n${GREEN}✓ $COUNT infrastructure services are now accessible on localhost${NC}"
echo ""
echo -e "${BLUE}=== gRPC Gateway Services ===${NC}"
echo "  MinIO gRPC:      localhost:50051"
echo "  DuckDB gRPC:     localhost:50052"
echo "  MQTT gRPC:       localhost:50053"
echo "  Loki gRPC:       localhost:50054"
echo "  Redis gRPC:      localhost:50055"
echo "  NATS gRPC:       localhost:50056"
echo "  PostgreSQL gRPC: localhost:50061"
echo "  Qdrant gRPC:     localhost:50062"
echo "  Neo4j gRPC:      localhost:50063"
echo ""
echo -e "${BLUE}=== Infrastructure ===${NC}"
echo "  PostgreSQL:      localhost:5432"
echo "  Redis:           localhost:6379"
echo "  MinIO API:       localhost:9000"
echo "  MinIO Console:   localhost:9001"
echo "  NATS:            localhost:4222"
echo "  Mosquitto:       localhost:1883"
echo "  Neo4j Browser:   localhost:7474"
echo "  Neo4j Bolt:      localhost:7687"
echo "  Qdrant:          localhost:6333"
echo "  Consul:          localhost:8500"
echo "  etcd:            localhost:2379"
echo ""
echo -e "${BLUE}=== Monitoring ===${NC}"
echo "  Grafana:         localhost:3000"
echo "  Loki:            localhost:3100"
echo "  APISIX Dashboard:localhost:9090"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all port-forwards${NC}\n"

# Wait for all background jobs
wait
