# Quick Start

Local development setup with KIND (Kubernetes in Docker).

## Prerequisites

- Docker 20.10+
- kubectl
- Helm 3.x
- KIND (Kubernetes in Docker)
- Go 1.23+ (for building services)
- Python 3.8+ (for isA_common)

## Local Cluster Setup

### 1. Create KIND Cluster

```bash
cd deployments/kubernetes/local/scripts
./kind-setup.sh
```

This creates a KIND cluster with:
- 1 control plane node
- 2 worker nodes
- Ingress support
- Port mappings for services

### 2. Build and Load Images

```bash
./kind-build-load.sh
```

Builds Docker images for all gRPC services and loads them into KIND.

### 3. Deploy Infrastructure

```bash
./kind-deploy.sh
```

Deploys all infrastructure components:
- PostgreSQL, Redis, Neo4j
- NATS, MQTT (Mosquitto)
- MinIO, Qdrant, DuckDB
- Loki, Grafana
- Consul, APISIX

### 4. Verify Services

```bash
./check-services.sh
```

## Manual Setup

### Create Cluster

```bash
kind create cluster --name isa-cloud --config kind-config.yaml
```

### Deploy with Helm

```bash
# Add Helm repos
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo add apisix https://charts.apiseven.com

# Deploy infrastructure (local namespace)
helm install postgresql bitnami/postgresql -n isa-cloud-local
helm install redis bitnami/redis -n isa-cloud-local
helm install consul hashicorp/consul -n isa-cloud-local
helm install apisix apisix/apisix -n isa-cloud-local
```

## Port Forwarding

Access services locally:

```bash
# All services
./scripts/port-forward.sh

# Infrastructure only
./scripts/port-forward-infra.sh
```

### Service Ports

| Service | Local Port |
|---------|------------|
| APISIX Gateway | 9080 |
| APISIX Admin | 9180 |
| Consul UI | 8500 |
| Consul DNS | 8600 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| Neo4j HTTP | 7474 |
| Neo4j Bolt | 7687 |
| NATS | 4222 |
| MQTT | 1883 |
| MinIO API | 9000 |
| MinIO Console | 9001 |
| Qdrant | 6333 |
| Grafana | 3000 |
| Loki | 3100 |

## Build Commands

```bash
# Build all services
make build

# Build specific service
make build-postgres
make build-redis

# Run tests
make test

# Lint code
make lint

# Generate protobuf
make proto
```

## Configuration

### Development Config

```yaml
# configs/examples/development.yaml
postgres:
  host: localhost
  port: 5432
  database: isa_dev

redis:
  host: localhost
  port: 6379

consul:
  host: localhost
  port: 8500
```

### Environment Variables

```bash
export ISA_ENV=development
export ISA_LOG_LEVEL=debug
export POSTGRES_HOST=localhost
export REDIS_HOST=localhost
export CONSUL_HTTP_ADDR=localhost:8500
```

## Verify Installation

### Check Pods

```bash
kubectl get pods -n isa-cloud-local
```

### Check Services in Consul

```bash
curl http://localhost:8500/v1/catalog/services | jq
```

### Test gRPC Service

```bash
grpcurl -plaintext localhost:50061 list
```

## Troubleshooting

### Pods Not Starting

```bash
kubectl describe pod <pod-name> -n isa-cloud-local
kubectl logs <pod-name> -n isa-cloud-local
```

### Service Not Registered

Check Consul health:
```bash
curl http://localhost:8500/v1/health/service/<service-name>
```

### Connection Refused

Verify port forwarding:
```bash
kubectl port-forward svc/postgres 5432:5432 -n isa-cloud-local
```

## Next Steps

- [gRPC Services](./grpc-services) - Infrastructure wrappers
- [Gateway](./gateway) - APISIX configuration
- [Discovery](./discovery) - Consul integration
