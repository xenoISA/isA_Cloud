# isA Cloud

Cloud-native infrastructure platform for the isA ecosystem.

## Overview

isA Cloud provides unified microservices infrastructure with:

- **9 gRPC services** wrapping backend infrastructure
- **API gateway** via Apache APISIX
- **Service discovery** via Consul
- **GitOps deployment** via ArgoCD
- **Multi-environment** support (dev, staging, production)
- **42+ microservices** orchestration

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL TRAFFIC                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                      APISIX GATEWAY (Port 9080)                             │
│        Rate limiting • Authentication • Dynamic routing • SSL               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CONSUL SERVICE DISCOVERY (Port 8500)                   │
│        Service registration • Health checks • DNS • KV store                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                      gRPC INFRASTRUCTURE SERVICES                           │
│        postgres-grpc • redis-grpc • neo4j-grpc • nats-grpc • mqtt-grpc      │
│        minio-grpc • qdrant-grpc • duckdb-grpc • loki-grpc                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                      BACKEND INFRASTRUCTURE                                 │
│   PostgreSQL • Redis • Neo4j • NATS • MQTT • MinIO • Qdrant • DuckDB • Loki │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Purpose |
|-----------|---------|
| **gRPC Services** | Unified interface to 9 backend systems |
| **APISIX** | API gateway with dynamic routing |
| **Consul** | Service discovery and health checks |
| **ArgoCD** | GitOps continuous deployment |
| **isA_common** | Shared Python client library |
| **Helm Charts** | Kubernetes package management |

## gRPC Services

| Service | Port | Backend |
|---------|------|---------|
| postgres-grpc | 50061 | PostgreSQL |
| redis-grpc | 50055 | Redis |
| neo4j-grpc | 50063 | Neo4j |
| nats-grpc | 50056 | NATS |
| mqtt-grpc | 50053 | MQTT |
| minio-grpc | 50051 | MinIO |
| qdrant-grpc | 50062 | Qdrant |
| duckdb-grpc | 50052 | DuckDB |
| loki-grpc | 50054 | Loki |

## Technology Stack

| Category | Technologies |
|----------|--------------|
| **Languages** | Go 1.23, Python 3.8+ |
| **Orchestration** | Kubernetes 1.34, Helm |
| **IaC** | Terraform, Kustomize |
| **CI/CD** | GitHub Actions, ArgoCD |
| **Gateway** | Apache APISIX |
| **Discovery** | Consul |
| **Messaging** | NATS JetStream, MQTT |
| **Databases** | PostgreSQL, Redis, Neo4j, DuckDB |
| **Storage** | MinIO (S3-compatible) |
| **Vectors** | Qdrant |
| **Observability** | Loki, Grafana, Prometheus |

## Environments

| Environment | Cluster | Namespace |
|-------------|---------|-----------|
| **Local** | KIND | isa-cloud-local |
| **Staging** | EKS | isa-cloud-staging |
| **Production** | EKS/GKE | isa-cloud-production |

## Quick Start

```bash
# Local deployment with KIND
cd deployments/kubernetes/local/scripts
./kind-setup.sh
./kind-build-load.sh
./kind-deploy.sh

# Access services
# APISIX: http://localhost:9080
# Consul: http://localhost:8500
```

## Next Steps

- [Quick Start](./quickstart) - Local development setup
- [gRPC Services](./grpc-services) - Infrastructure wrappers
- [Gateway](./gateway) - APISIX configuration
- [Discovery](./discovery) - Consul integration
- [SDK](./sdk) - Python client library
- [Deployment](./deployment) - ArgoCD & Helm
- [CI/CD](./cicd) - GitHub Actions
- [Testing](./testing) - Contract-driven development
- [Operations](./operations) - Scripts & monitoring
