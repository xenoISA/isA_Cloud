# 3-Node Cluster Resource Profile

Override values for deploying the isA Cloud infrastructure on a 3-node Kubernetes cluster.

## Usage

```bash
./deploy.sh infrastructure --provider infotrend --nodes 3
```

Or manually with Helm:
```bash
helm upgrade --install postgresql bitnami/postgresql-ha \
  -n isa-cloud-production \
  -f values/postgresql-ha.yaml \
  -f profiles/3-node/postgresql-ha.yaml
```

## Resource Summary

| Component | Pods | CPU Request | Memory Request | Storage |
|-----------|------|-------------|----------------|---------|
| etcd | 3 | 500m x3 | 1Gi x3 | 20Gi x3 |
| PostgreSQL HA | 2+1 pgpool | 500m x2 + 100m | 1Gi x2 + 128Mi | 50Gi x2 |
| Redis Cluster | 3 | 250m x3 | 512Mi x3 | 10Gi x3 |
| Neo4j | 3 | 1000m x3 | 2Gi x3 | 20Gi x3 |
| MinIO | 4 | 500m x4 | 1Gi x4 | 100Gi x4 |
| NATS | 3 | 250m x3 | 512Mi x3 | 20Gi x3 |
| Qdrant | 3 | 500m x3 | 1Gi x3 | 50Gi x3 |
| EMQX | 3 | 250m x3 | 512Mi x3 | 5Gi x3 |
| Consul | 3+3 client | 250m x3 + 100m x3 | 256Mi x3 + 128Mi x3 | 10Gi x3 |
| Vault | 3 | 250m x3 | 256Mi x3 | — |
| APISIX | 2 | 250m x2 | 256Mi x2 | — |
| **Total** | **~34** | **~13.5 cores** | **~21 Gi** | **~925 Gi** |

## Minimum Node Requirements

Each node should have at minimum:
- **CPU**: 8 cores (24 total across 3 nodes)
- **RAM**: 16 GB (48 GB total)
- **Disk**: 500 GB SSD

## Key Changes from Default

- All hard pod anti-affinity changed to **soft** (preferred) — allows co-location when only 3 nodes available
- PostgreSQL reduced from 3 to **2 replicas** (1 primary + 1 standby)
- Redis Cluster reduced from 6 to **3 nodes** (3 masters, 0 replicas)
- MinIO keeps 4 replicas (minimum for erasure coding) — 2 nodes will run 2 pods
- All memory/CPU requests roughly halved from production defaults
- Storage sizes reduced where safe
- PDB thresholds adjusted for smaller replica counts
