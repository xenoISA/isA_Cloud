#!/bin/bash

# Port-forward all services to localhost
# This script sets up port forwarding for all services in the isa-cloud-staging namespace

NAMESPACE="isa-cloud-staging"

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Kill existing port-forwards for isa-cloud-staging namespace
echo -e "${YELLOW}Cleaning up existing port-forwards...${NC}"
EXISTING=$(pgrep -f "kubectl port-forward -n $NAMESPACE" 2>/dev/null)
if [ -n "$EXISTING" ]; then
    echo -e "${RED}Found existing port-forwards, killing them...${NC}"
    pkill -f "kubectl port-forward -n $NAMESPACE" 2>/dev/null
    sleep 1
    echo -e "${GREEN}Existing port-forwards killed${NC}"
else
    echo -e "${GREEN}No existing port-forwards found${NC}"
fi

echo -e "\n${GREEN}Starting port-forward for all services...${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all port-forwards${NC}\n"

# Array to store background process IDs
PIDS=()

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping all port-forwards...${NC}"
    for pid in "${PIDS[@]}"; do
        kill $pid 2>/dev/null
    done
    echo -e "${GREEN}All port-forwards stopped${NC}"
    exit 0
}

# Trap Ctrl+C and call cleanup
trap cleanup INT TERM

# Counter for services
COUNT=0

# ==========================================
# gRPC Services (50051-50063)
# ==========================================
echo -e "${BLUE}=== gRPC Services ===${NC}"

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

echo -e "${GREEN}[Monitor] APISIX Gateway (localhost:80)${NC}"
kubectl port-forward -n $NAMESPACE svc/apisix-gateway 80:80 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[Monitor] APISIX Dashboard (localhost:9090)${NC}"
kubectl port-forward -n $NAMESPACE svc/apisix-dashboard 9090:9000 &
PIDS+=($!)
((COUNT++))

# ==========================================
# Application Services (8080-8230)
# ==========================================
echo -e "\n${BLUE}=== Application Services ===${NC}"

echo -e "${GREEN}[App] Agent (localhost:8080)${NC}"
kubectl port-forward -n $NAMESPACE svc/agent 8080:8080 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] MCP (localhost:8081)${NC}"
kubectl port-forward -n $NAMESPACE svc/mcp 8081:8081 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Model (localhost:8082)${NC}"
kubectl port-forward -n $NAMESPACE svc/model 8082:8082 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Web (localhost:8083)${NC}"
kubectl port-forward -n $NAMESPACE svc/web 8083:8083 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Data (localhost:8084)${NC}"
kubectl port-forward -n $NAMESPACE svc/data 8084:8084 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Python REPL (localhost:8086)${NC}"
kubectl port-forward -n $NAMESPACE svc/python-repl 8086:8086 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Auth (localhost:8201)${NC}"
kubectl port-forward -n $NAMESPACE svc/auth 8201:8201 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Account (localhost:8202)${NC}"
kubectl port-forward -n $NAMESPACE svc/account 8202:8202 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Session (localhost:8203)${NC}"
kubectl port-forward -n $NAMESPACE svc/session 8203:8203 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Authorization (localhost:8204)${NC}"
kubectl port-forward -n $NAMESPACE svc/authorization 8204:8204 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Audit (localhost:8205)${NC}"
kubectl port-forward -n $NAMESPACE svc/audit 8205:8205 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Notification (localhost:8206)${NC}"
kubectl port-forward -n $NAMESPACE svc/notification 8206:8206 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Payment (localhost:8207)${NC}"
kubectl port-forward -n $NAMESPACE svc/payment 8207:8207 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Wallet (localhost:8208)${NC}"
kubectl port-forward -n $NAMESPACE svc/wallet 8208:8208 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Storage (localhost:8209)${NC}"
kubectl port-forward -n $NAMESPACE svc/storage 8209:8209 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Order (localhost:8210)${NC}"
kubectl port-forward -n $NAMESPACE svc/order 8210:8210 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Task (localhost:8211)${NC}"
kubectl port-forward -n $NAMESPACE svc/task 8211:8211 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Organization (localhost:8212)${NC}"
kubectl port-forward -n $NAMESPACE svc/organization 8212:8212 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Invitation (localhost:8213)${NC}"
kubectl port-forward -n $NAMESPACE svc/invitation 8213:8213 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Vault (localhost:8214)${NC}"
kubectl port-forward -n $NAMESPACE svc/vault 8214:8214 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Product (localhost:8215)${NC}"
kubectl port-forward -n $NAMESPACE svc/product 8215:8215 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Billing (localhost:8216)${NC}"
kubectl port-forward -n $NAMESPACE svc/billing 8216:8216 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Calendar (localhost:8217)${NC}"
kubectl port-forward -n $NAMESPACE svc/calendar 8217:8217 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Weather (localhost:8218)${NC}"
kubectl port-forward -n $NAMESPACE svc/weather 8218:8218 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Album (localhost:8219)${NC}"
kubectl port-forward -n $NAMESPACE svc/album 8219:8219 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Device (localhost:8220)${NC}"
kubectl port-forward -n $NAMESPACE svc/device 8220:8220 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] OTA (localhost:8221)${NC}"
kubectl port-forward -n $NAMESPACE svc/ota 8221:8221 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Media (localhost:8222)${NC}"
kubectl port-forward -n $NAMESPACE svc/media 8222:8222 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Memory (localhost:8223)${NC}"
kubectl port-forward -n $NAMESPACE svc/memory 8223:8223 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Location (localhost:8224)${NC}"
kubectl port-forward -n $NAMESPACE svc/location 8224:8224 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Telemetry (localhost:8225)${NC}"
kubectl port-forward -n $NAMESPACE svc/telemetry 8225:8225 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Compliance (localhost:8226)${NC}"
kubectl port-forward -n $NAMESPACE svc/compliance 8226:8226 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Document (localhost:8227)${NC}"
kubectl port-forward -n $NAMESPACE svc/document 8227:8227 &
PIDS+=($!)
((COUNT++))

echo -e "${GREEN}[App] Event (localhost:8230)${NC}"
kubectl port-forward -n $NAMESPACE svc/event 8230:8230 &
PIDS+=($!)
((COUNT++))

# Wait a bit for port-forwards to establish
sleep 2

echo -e "\n${GREEN}✓ All $COUNT services are now accessible on localhost${NC}"
echo ""
echo -e "${BLUE}=== gRPC Services ===${NC}"
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
echo "  APISIX Gateway:  localhost:80"
echo "  APISIX Dashboard:localhost:9090"
echo ""
echo -e "${BLUE}=== Application Services ===${NC}"
echo "  Agent:           localhost:8080"
echo "  MCP:             localhost:8081"
echo "  Model:           localhost:8082"
echo "  Web:             localhost:8083"
echo "  Data:            localhost:8084"
echo "  Python REPL:     localhost:8086"
echo "  Auth:            localhost:8201"
echo "  Account:         localhost:8202"
echo "  Session:         localhost:8203"
echo "  Authorization:   localhost:8204"
echo "  Audit:           localhost:8205"
echo "  Notification:    localhost:8206"
echo "  Payment:         localhost:8207"
echo "  Wallet:          localhost:8208"
echo "  Storage:         localhost:8209"
echo "  Order:           localhost:8210"
echo "  Task:            localhost:8211"
echo "  Organization:    localhost:8212"
echo "  Invitation:      localhost:8213"
echo "  Vault:           localhost:8214"
echo "  Product:         localhost:8215"
echo "  Billing:         localhost:8216"
echo "  Calendar:        localhost:8217"
echo "  Weather:         localhost:8218"
echo "  Album:           localhost:8219"
echo "  Device:          localhost:8220"
echo "  OTA:             localhost:8221"
echo "  Media:           localhost:8222"
echo "  Memory:          localhost:8223"
echo "  Location:        localhost:8224"
echo "  Telemetry:       localhost:8225"
echo "  Compliance:      localhost:8226"
echo "  Document:        localhost:8227"
echo "  Event:           localhost:8230"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all port-forwards${NC}\n"

# Wait for all background jobs
wait
