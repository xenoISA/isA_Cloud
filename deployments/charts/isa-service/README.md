# isa-service Helm Chart

Generic Helm chart for deploying all isA platform Python services.

## Architecture

All isA services follow the same deployment pattern:
- Use this shared chart with service-specific values
- Native infrastructure access (PostgreSQL 5432, Redis 6379, etc.)
- Consul service discovery
- Harbor container registry

## Quick Start

```bash
# Deploy a service
helm upgrade --install <service>-service \
  ~/Documents/Fun/isA/isA_Cloud/deployments/charts/isa-service \
  -f ~/Documents/Fun/isA/isA_<Service>/deployment/helm/values.yaml \
  -n isa-cloud-staging

# Examples
helm upgrade --install mcp-service ./isa-service \
  -f ~/Documents/Fun/isA/isA_MCP/deployment/helm/values.yaml \
  -n isa-cloud-staging

helm upgrade --install model-service ./isa-service \
  -f ~/Documents/Fun/isA/isA_Model/deployment/helm/values.yaml \
  -n isa-cloud-staging
```

## Service Deployment Structure

Each isA service should have this structure in their repo:

```
deployment/
├── environments/
│   ├── dev.env           # Local development (native localhost)
│   └── staging.env       # Staging K8s cluster
├── helm/
│   ├── values.yaml       # Helm values for this service
│   └── secrets.yaml.template  # Secret template (not committed)
├── k8s/
│   ├── Dockerfile.<svc>  # Container build file
│   └── _legacy/          # Old Kustomize configs (archived)
├── requirements/
│   ├── base.txt          # Prod dependencies
│   ├── base_dev.txt      # Dev dependencies (incl. isa-common)
│   └── project.txt       # Project-specific deps
└── local-dev.sh          # Local development script
```

## Services

| Service | Port | Values File |
|---------|------|-------------|
| MCP | 8081 | `isA_MCP/deployment/helm/values.yaml` |
| Model | 8082 | `isA_Model/deployment/helm/values.yaml` |
| Agent | 8083 | `isA_Agent/deployment/helm/values.yaml` |
| Data | 8084 | `isA_Data/deployment/helm/values.yaml` |

## Chart Features

### values.yaml Required Fields

```yaml
name: my-service
namespace: isa-cloud-staging

image:
  registry: harbor.local:30443
  repository: isa/my-service
  tag: latest
  pullPolicy: Always

port: 8080
replicas: 1

resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "1000m"

health:
  path: /health
  initialDelaySeconds: 30
  periodSeconds: 10

consul:
  enabled: true

env:
  - name: MY_VAR
    value: "my-value"
```

### Secrets (from K8s Secret)

```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: my-service-secrets
        key: db-password
```

### Volumes (Optional)

```yaml
volumes:
  - name: data
    emptyDir: {}

volumeMounts:
  - name: data
    mountPath: /app/data
```

### Autoscaling

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilization: 70
  targetMemoryUtilization: 80
```

## Infrastructure Endpoints (Staging K8s)

All services connect to infrastructure using native protocols:

| Service | Host | Port |
|---------|------|------|
| PostgreSQL | postgresql.isa-cloud-staging.svc.cluster.local | 5432 |
| Redis | redis-master.isa-cloud-staging.svc.cluster.local | 6379 |
| Qdrant | qdrant.isa-cloud-staging.svc.cluster.local | 6333 |
| Neo4j | neo4j.isa-cloud-staging.svc.cluster.local | 7687 |
| NATS | nats.isa-cloud-staging.svc.cluster.local | 4222 |
| MinIO | minio.isa-cloud-staging.svc.cluster.local | 9000 |
| Consul | consul-server.isa-cloud-staging.svc.cluster.local | 8500 |
| MQTT | emqx.isa-cloud-staging.svc.cluster.local | 1883 |

## Deployment Commands

```bash
# Create namespace
kubectl create namespace isa-cloud-staging

# Apply secrets first
kubectl apply -f deployment/helm/secrets.yaml -n isa-cloud-staging

# Deploy service
helm upgrade --install <name>-service \
  ~/Documents/Fun/isA/isA_Cloud/deployments/charts/isa-service \
  -f deployment/helm/values.yaml \
  -n isa-cloud-staging

# Check status
kubectl get pods -n isa-cloud-staging -l app=<name>-service
kubectl logs -f deployment/<name>-service -n isa-cloud-staging
```
