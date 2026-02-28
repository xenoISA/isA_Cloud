# isA Cloud - Cloud-Native Infrastructure Platform

<div align="center">

**Kubernetes Infrastructure + Service Mesh + API Gateway**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.34-326CE5?logo=kubernetes)](https://kubernetes.io/)
[![Apache APISIX](https://img.shields.io/badge/APISIX-3.x-F04C23?logo=apache)](https://apisix.apache.org/)
[![Consul](https://img.shields.io/badge/Consul-1.21-F24C53?logo=consul)](https://www.consul.io/)
[![ArgoCD](https://img.shields.io/badge/ArgoCD-GitOps-EF7B4D?logo=argo)](https://argoproj.github.io/cd/)

</div>

---

## Overview

**isA Cloud** is the isA platform's cloud-native infrastructure center, providing:

### This Repository Provides

**isa_common Python Library** (native async clients)
  - Direct async connections to 8 infrastructure backends
  - No intermediate gRPC layer — clients connect to native ports
  - Source in `isA_common/isa_common/`

**Infrastructure Deployment** (Kubernetes)
  - PostgreSQL, Redis, Neo4j, MinIO, NATS, Mosquitto, Loki, Grafana, Qdrant
  - Consul (service discovery), APISIX (API gateway)

**GitOps Configuration**
  - Kubernetes deployment configs (Kustomize)
  - ArgoCD application definitions
  - Multi-environment management (dev/staging/production)

**CI/CD Pipeline**
  - GitHub Actions automated builds
  - Image push to ECR
  - Automated deployment config updates

### External Business Services (other repositories)

These services have **source code in their own repos**; isA_Cloud contains only their **Kubernetes deployment configs**:

- **isA_user** — 27 user microservices (account, auth, session, organization...)
- **isA_Agent** — AI agent service
- **isA_MCP** — Model Control Protocol service
- **isA_Model** — AI model service
- **isa-data** — Data service
- **web-service** — Web service

---

## Architecture

### Overall Architecture

```
                         External Traffic
                              │
                              ▼
                      ┌───────────────┐
                      │ Apache APISIX │  API Gateway (Port: 9080)
                      │   (Gateway)   │  - Dynamic routing (auto-sync Consul)
                      └───────┬───────┘  - Auth/rate-limit/CORS
                              │
                              ▼
                      ┌───────────────┐
                      │    Consul     │  Service Discovery
                      │ (42 services) │  - Health checks
                      └───────┬───────┘  - KV storage
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
       ▼                      ▼                      ▼
┌──────────────┐     ┌───────────────┐      ┌──────────────┐
│ Infrastructure│     │  isa_common   │      │ Business     │
│ (this repo   │     │  Python SDK   │      │ Services     │
│  deploys)    │     │ (this repo)   │      │ (other repos)│
├──────────────┤     ├───────────────┤      ├──────────────┤
│ PostgreSQL   │◄────│ AsyncPostgres │      │ isA_user     │
│ Redis        │◄────│ AsyncRedis    │      │  ├─ auth     │
│ Neo4j        │◄────│ AsyncNeo4j    │      │  ├─ account  │
│ MinIO        │◄────│ AsyncMinIO    │      │  └─ ... (27) │
│ NATS         │◄────│ AsyncNATS     │      │              │
│ Mosquitto    │◄────│ AsyncMQTT     │      │ isA_Agent    │
│ Loki         │     │ AsyncDuckDB   │      │ isA_MCP      │
│ Grafana      │     │ AsyncQdrant   │      │ isA_Model    │
│ Qdrant       │     │ ConsulRegistry│      │ isa-data     │
└──────────────┘     └───────────────┘      └──────────────┘
      Native Ports         Direct
   (5432,6379,7687,        Connection
    4222,9000,1883,        (no gRPC
    6333,3100)              layer)
```

### GitOps Workflow

```
1. Developer commits code
   ├─ isA_Cloud: modify isa_common library or deployment configs
   └─ External repo: modify business service code
                     │
                     ▼
2. CI Pipeline (GitHub Actions)
   ├─ Lint & Test (pytest for Python, security scans)
   ├─ Build Docker images
   ├─ Push to ECR
   └─ External repos trigger repository_dispatch → isA_Cloud
                     │
                     ▼
3. Update GitOps config (automatic)
   ├─ CD workflow updates deployment.yaml with new image tag
   └─ Git commit & push
                     │
                     ▼
4. ArgoCD auto-sync (within 30 seconds)
   ├─ Detects Git changes
   └─ Applies to Kubernetes
                     │
                     ▼
5. Kubernetes rolling update
   ├─ Creates new Pods → health check → Consul registration
   └─ APISIX route sync (CronJob every 5 minutes)
```

---

## Repository Structure

```
isA_Cloud/
├── isA_common/                   # Python infrastructure library
│   ├── isa_common/
│   │   ├── __init__.py           # Exports (v0.3.1)
│   │   ├── async_base_client.py  # Abstract base for all clients
│   │   ├── async_client_config.py
│   │   ├── async_redis_client.py
│   │   ├── async_postgres_client.py
│   │   ├── async_nats_client.py
│   │   ├── async_neo4j_client.py
│   │   ├── async_minio_client.py
│   │   ├── async_qdrant_client.py
│   │   ├── async_duckdb_client.py
│   │   ├── async_mqtt_client.py
│   │   ├── consul_client.py      # Service discovery
│   │   └── events/               # Event-driven billing architecture
│   ├── tests/                    # pytest test suite
│   └── pyproject.toml
│
├── deployments/
│   ├── kubernetes/               # Kustomize configs
│   │   ├── local/                # KIND cluster
│   │   ├── staging/              # Staging K8s
│   │   └── production/           # Production K8s (HA)
│   ├── argocd/                   # ArgoCD app-of-apps
│   ├── terraform/                # AWS IaC (staging)
│   └── charts/isa-service/       # Generic Helm chart
│
├── .github/workflows/            # CI/CD pipelines
├── tests/                        # Integration test scripts
│   ├── contracts/                # Logic contracts (8 services)
│   ├── test_auth_via_apisix.sh
│   └── ...
│
└── docs/                         # Documentation
```

---

## Core Components

### 1. isa_common — Python Infrastructure SDK

Native async clients connecting directly to backend services on their native ports:

| Client | Backend | Port | Methods | Status |
|--------|---------|------|---------|--------|
| **AsyncRedisClient** | Redis | 6379 | 53 | Complete |
| **AsyncPostgresClient** | PostgreSQL | 5432 | 19 | Complete |
| **AsyncNATSClient** | NATS | 4222 | 33 | Complete |
| **AsyncNeo4jClient** | Neo4j | 7687 | 37 | Partial |
| **AsyncMinIOClient** | MinIO | 9000 | 35 | Complete |
| **AsyncQdrantClient** | Qdrant | 6333 | 25 | Complete |
| **AsyncDuckDBClient** | DuckDB | embedded | 27 | Complete |
| **AsyncMQTTClient** | Mosquitto | 1883 | 29 | Complete |

Additional local-mode clients: `AsyncSQLiteClient`, `AsyncLocalStorageClient`, `AsyncChromaClient`, `AsyncMemoryClient`

**Usage:**

```python
from isa_common import AsyncRedisClient, AsyncPostgresClient, AsyncNATSClient

# Direct connection to Redis on native port
async with AsyncRedisClient(host="localhost", port=6379) as redis:
    await redis.set("session:user_123", session_data, ttl=3600)
    session = await redis.get("session:user_123")

# Direct connection to PostgreSQL
async with AsyncPostgresClient(host="localhost", port=5432, database="mydb") as pg:
    rows = await pg.query("SELECT * FROM users WHERE org_id = $1", "org_123")

# Direct connection to NATS with JetStream
async with AsyncNATSClient(host="localhost", port=4222) as nats:
    await nats.publish("orders.created", {"order_id": "123"})
    messages = await nats.pull_messages("USAGE_EVENTS", "billing-consumer")
```

### 2. Apache APISIX (API Gateway)

- Unified traffic entry (Port: 9080)
- Dynamic routing (auto-sync from Consul)
- Auth (JWT/Key Auth), rate limiting, CORS
- Admin API: `http://localhost:9180`

### 3. Consul (Service Discovery)

- Service registration/discovery, health checks, KV config
- 42 registered services (33 business + 9 infrastructure)
- UI: `http://localhost:8500`

### 4. ArgoCD (GitOps)

- Git → Kubernetes auto-sync, declarative deployments
- Multi-environment: dev (auto-sync), staging (auto-sync), production (manual sync)

---

## Quick Start

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| **Docker** | 20.10+ | [Docker Desktop](https://www.docker.com/products/docker-desktop) |
| **kubectl** | 1.28+ | `brew install kubectl` |
| **kind** | 0.20+ | `brew install kind` |
| **Python** | 3.12+ | `brew install python` |

### Install isa_common

```bash
cd isA_common
pip install -e ".[dev]"
```

### Run Tests

```bash
cd isA_common/tests
python -m pytest -v                          # All tests
python -m pytest redis/ -v                   # Redis client tests
python -m pytest smoke/ -m smoke -v          # Billing pipeline smoke tests
```

### Local Kubernetes Deployment (KIND)

```bash
cd deployments/kubernetes/scripts
./kind-setup.sh          # Create KIND cluster
./kind-deploy.sh         # Deploy all services
./check-services.sh      # Check status

# Access services
open http://localhost:9080    # APISIX Gateway
open http://localhost:8500    # Consul UI
open http://localhost:3000    # Grafana
```

---

## Infrastructure Services

| Service | Port | Purpose |
|---------|------|---------|
| **APISIX** | 9080, 9180 | API Gateway |
| **Consul** | 8500, 8600 | Service Discovery |
| **PostgreSQL** | 5432 | Relational Database |
| **Redis** | 6379 | Cache/Sessions |
| **Neo4j** | 7474, 7687 | Graph Database |
| **MinIO** | 9000, 9001 | Object Storage |
| **NATS** | 4222, 8222 | Message Queue |
| **Mosquitto** | 1883 | MQTT Broker |
| **Loki** | 3100 | Log Aggregation |
| **Grafana** | 3000 | Visualization |
| **Qdrant** | 6333 | Vector Database |

---

## Deployment

### Environments

| Environment | Cluster | Namespace | Branch |
|-------------|---------|-----------|--------|
| **dev** | KIND local | isa-cloud-dev | develop |
| **staging** | KIND/EKS | isa-cloud-staging | main |
| **production** | EKS/GKE | isa-cloud-production | production |

See [Production Deployment Guide](./docs/production_deployment_guide.md) for EKS/GKE setup.

---

## Documentation

### Core Docs
- **[CI/CD Pipeline](./docs/cicd.md)** — GitHub Actions + ArgoCD workflow
- **[Consul Guide](./docs/how_to_consul.md)** — Service discovery operations
- **[APISIX Route Sync](./docs/apisix_route_consul_sync.md)** — Auto route sync
- **[Production Deploy](./docs/production_deployment_guide.md)** — EKS/GKE + HPA

### Runbooks
- **[NATS Consumer Lag](./docs/runbooks/nats-consumer-lag.md)** — Billing event delays

### Test Scripts
- [test_auth_via_apisix.sh](./tests/test_auth_via_apisix.sh)
- [test_mcp_via_apisix.sh](./tests/test_mcp_via_apisix.sh)
- [test_agent_via_apisix.sh](./tests/test_agent_via_apisix.sh)
- [test_storage_via_apisix.sh](./tests/test_storage_via_apisix.sh)

---

## Contributing

### Commit Conventions

```
feat: New feature
fix: Bug fix
docs: Documentation
refactor: Refactoring
test: Tests
chore: Build/tooling
```

---

## License

MIT License

---

<div align="center">

**Made with care by the isA Team**

</div>
