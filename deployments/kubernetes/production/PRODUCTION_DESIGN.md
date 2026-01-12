# Production Infrastructure Design

## Overview

Production-grade Kubernetes infrastructure using Helm charts with Infotrend hybrid storage backend.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Production Kubernetes Cluster                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Namespace: isa-cloud-production                   │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │                                                                      │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │                    Data Layer (StatefulSets)                  │   │    │
│  │  ├──────────────────────────────────────────────────────────────┤   │    │
│  │  │                                                               │   │    │
│  │  │  PostgreSQL HA          Redis Cluster       Qdrant Cluster   │   │    │
│  │  │  ┌─────┬─────┬─────┐   ┌─────┬─────┬─────┐  ┌─────┬─────┬─────┐   │    │
│  │  │  │Pri  │Stby1│Stby2│   │M1/R1│M2/R2│M3/R3│  │Node1│Node2│Node3│   │    │
│  │  │  │100Gi│100Gi│100Gi│   │20Gi │20Gi │20Gi │  │100Gi│100Gi│100Gi│   │    │
│  │  │  └──┬──┴──┬──┴──┬──┘   └──┬──┴──┬──┴──┬──┘  └──┬──┴──┬──┴──┬──┘   │    │
│  │  │     │     │     │         │     │     │        │     │     │      │   │    │
│  │  │  Neo4j Cluster          NATS JetStream       MinIO Distributed   │   │    │
│  │  │  ┌─────┬─────┬─────┐   ┌─────┬─────┬─────┐  ┌─────┬─────┬─────┬─────┐   │
│  │  │  │Core1│Core2│Core3│   │JS1  │JS2  │JS3  │  │Node1│Node2│Node3│Node4│   │
│  │  │  │50Gi │50Gi │50Gi │   │50Gi │50Gi │50Gi │  │200Gi│200Gi│200Gi│200Gi│   │
│  │  │  └─────┴─────┴─────┘   └─────┴─────┴─────┘  └─────┴─────┴─────┴─────┘   │
│  │  │                                                               │   │    │
│  │  │  EMQX MQTT Cluster                                           │   │    │
│  │  │  ┌─────┬─────┬─────┐                                         │   │    │
│  │  │  │Node1│Node2│Node3│                                         │   │    │
│  │  │  │10Gi │10Gi │10Gi │                                         │   │    │
│  │  │  └─────┴─────┴─────┘                                         │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  │                              │                                       │    │
│  │                              ▼                                       │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │                 Infotrend Hybrid Storage Backend              │   │    │
│  │  ├──────────────────────────────────────────────────────────────┤   │    │
│  │  │  Block Storage (iSCSI)   │  NFS Storage    │  Object Storage  │   │    │
│  │  │  - PostgreSQL            │  - Shared logs  │  - MinIO backend │   │    │
│  │  │  - Redis                 │  - Config maps  │  - Backups       │   │    │
│  │  │  - Neo4j                 │  - ReadWriteMany│  - Archives      │   │    │
│  │  │  - Qdrant                │                 │                  │   │    │
│  │  │  - NATS                  │                 │                  │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Storage Classes

### Block Storage (for databases)
- **Name**: `infotrend-block`
- **Provisioner**: Infotrend CSI or iSCSI
- **Use case**: PostgreSQL, Redis, Neo4j, Qdrant, NATS
- **Features**: High IOPS, low latency

### NFS Storage (for shared access)
- **Name**: `infotrend-nfs`
- **Provisioner**: NFS CSI
- **Use case**: Shared configurations, logs, ReadWriteMany volumes
- **Features**: Multi-pod access

### Object Storage (for backups/archives)
- **Name**: `infotrend-object`
- **Provisioner**: S3-compatible API
- **Use case**: MinIO backend, database backups, long-term storage
- **Features**: Cost-effective, scalable

## Component Specifications

### 1. PostgreSQL HA (Bitnami Chart)
| Setting | Value |
|---------|-------|
| Chart | `bitnami/postgresql-ha` |
| Replicas | 3 (1 primary + 2 standby) |
| Storage | 100Gi block per node |
| Resources | 2 CPU / 4Gi RAM |
| HA Mode | Streaming replication + Pgpool |

### 2. Redis Cluster (Bitnami Chart)
| Setting | Value |
|---------|-------|
| Chart | `bitnami/redis-cluster` |
| Nodes | 6 (3 masters + 3 replicas) |
| Storage | 20Gi block per node |
| Resources | 1 CPU / 2Gi RAM |
| Mode | Redis Cluster (sharding) |

### 3. Qdrant Distributed (Official Chart)
| Setting | Value |
|---------|-------|
| Chart | `qdrant/qdrant` |
| Replicas | 3 |
| Storage | 100Gi block per node |
| Resources | 2 CPU / 4Gi RAM |
| Shards | 3 |
| Replication | 2 |

### 4. NATS JetStream (Official Chart)
| Setting | Value |
|---------|-------|
| Chart | `nats/nats` |
| Replicas | 3 |
| Storage | 50Gi block per node |
| Resources | 1 CPU / 2Gi RAM |
| Mode | JetStream cluster |

### 5. MinIO Distributed (Official Chart)
| Setting | Value |
|---------|-------|
| Chart | `minio/minio` |
| Nodes | 4 |
| Drives per node | 1 |
| Storage | 200Gi per node (800Gi total) |
| Resources | 2 CPU / 4Gi RAM |
| Mode | Distributed |

### 6. Neo4j Cluster (Official Chart)
| Setting | Value |
|---------|-------|
| Chart | `neo4j/neo4j` |
| Cores | 3 |
| Storage | 50Gi block per node |
| Resources | 2 CPU / 4Gi RAM |
| Mode | Cluster (requires Enterprise) |

### 7. EMQX MQTT (Official Chart)
| Setting | Value |
|---------|-------|
| Chart | `emqx/emqx` |
| Replicas | 3 |
| Storage | 10Gi block per node |
| Resources | 1 CPU / 2Gi RAM |
| Mode | Cluster |

## Resource Summary

| Component | Nodes | CPU Total | Memory Total | Storage Total |
|-----------|-------|-----------|--------------|---------------|
| PostgreSQL | 3 | 6 CPU | 12Gi | 300Gi |
| Redis | 6 | 6 CPU | 12Gi | 120Gi |
| Qdrant | 3 | 6 CPU | 12Gi | 300Gi |
| NATS | 3 | 3 CPU | 6Gi | 150Gi |
| MinIO | 4 | 8 CPU | 16Gi | 800Gi |
| Neo4j | 3 | 6 CPU | 12Gi | 150Gi |
| EMQX | 3 | 3 CPU | 6Gi | 30Gi |
| **TOTAL** | **25** | **38 CPU** | **76Gi** | **1.85Ti** |

## Directory Structure

```
deployments/kubernetes/production/
├── PRODUCTION_DESIGN.md          # This document
├── namespace.yaml                # Namespace + RBAC
├── storage/
│   └── storage-classes.yaml      # Infotrend storage classes
├── helm/
│   ├── helmfile.yaml             # Declarative Helm releases
│   └── values/
│       ├── postgresql-ha.yaml
│       ├── redis-cluster.yaml
│       ├── qdrant-distributed.yaml
│       ├── nats-jetstream.yaml
│       ├── minio-distributed.yaml
│       ├── neo4j-cluster.yaml
│       └── emqx-cluster.yaml
└── scripts/
    ├── deploy.sh                 # Full deployment script
    └── backup.sh                 # Backup script
```

## Deployment Order

1. Storage Classes
2. Namespace + RBAC
3. PostgreSQL HA
4. Redis Cluster
5. NATS JetStream
6. MinIO Distributed
7. Qdrant Distributed
8. Neo4j Cluster
9. EMQX MQTT

## High Availability Features

- **Pod Anti-Affinity**: Spread pods across nodes/zones
- **Pod Disruption Budgets**: Ensure minimum availability during updates
- **Horizontal Pod Autoscaling**: For stateless gRPC services
- **Automatic Failover**: Built into each HA component
- **Data Replication**: Multi-replica storage for all databases
