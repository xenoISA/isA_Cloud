# Service Discovery

Consul integration for service registration, health checks, and DNS.

## Overview

Consul provides:

- **Service Registry** - 42+ services registered
- **Health Checks** - TCP/HTTP health monitoring
- **DNS Interface** - Service discovery via DNS
- **KV Store** - Configuration management
- **UI Dashboard** - Visual service monitoring

## Ports

| Port | Purpose |
|------|---------|
| 8500 | HTTP API / UI |
| 8600 | DNS |
| 8301 | Serf LAN |
| 8302 | Serf WAN |
| 8300 | RPC |

## Service Registration

### Manual Registration

```bash
curl -X PUT http://localhost:8500/v1/agent/service/register \
  -H "Content-Type: application/json" \
  -d '{
    "Name": "auth_service",
    "ID": "auth_service-1",
    "Port": 8201,
    "Tags": ["api", "v1", "http"],
    "Check": {
      "HTTP": "http://localhost:8201/health",
      "Interval": "10s",
      "Timeout": "5s"
    }
  }'
```

### Python Registration

```python
from isa_common import ConsulClient

consul = ConsulClient(host="localhost", port=8500)

# Register service
await consul.register_service(
    name="auth_service",
    port=8201,
    tags=["api", "v1"],
    health_check={
        "http": "http://localhost:8201/health",
        "interval": "10s"
    }
)

# Deregister on shutdown
await consul.deregister_service("auth_service-1")
```

### Automatic Registration

Services auto-register on startup:

```python
# core/consul_registry.py
async def register_service(
    service_name: str,
    port: int,
    health_check_path: str = "/health"
):
    await consul.agent.service.register(
        name=service_name,
        service_id=f"{service_name}-{instance_id}",
        port=port,
        check={
            "http": f"http://localhost:{port}{health_check_path}",
            "interval": "10s"
        }
    )
```

## Health Checks

### Check Types

| Type | Description |
|------|-------------|
| **HTTP** | GET request, 2xx = healthy |
| **TCP** | Connection test |
| **gRPC** | gRPC health protocol |
| **Script** | Custom script execution |
| **TTL** | Heartbeat-based |

### HTTP Check

```json
{
  "Check": {
    "HTTP": "http://localhost:8201/health",
    "Interval": "10s",
    "Timeout": "5s",
    "DeregisterCriticalServiceAfter": "30m"
  }
}
```

### gRPC Check

```json
{
  "Check": {
    "GRPC": "localhost:50061",
    "GRPCUseTLS": false,
    "Interval": "10s"
  }
}
```

## Service Discovery

### HTTP API

```bash
# List all services
curl http://localhost:8500/v1/catalog/services

# Get service instances
curl http://localhost:8500/v1/catalog/service/auth_service

# Get healthy instances only
curl http://localhost:8500/v1/health/service/auth_service?passing=true
```

### DNS

```bash
# Resolve service
dig @localhost -p 8600 auth_service.service.consul

# SRV record (includes port)
dig @localhost -p 8600 auth_service.service.consul SRV
```

### Python Client

```python
from isa_common import ConsulClient

consul = ConsulClient(host="localhost", port=8500)

# Discover service
services = await consul.get_service("auth_service")
for svc in services:
    print(f"{svc.address}:{svc.port}")

# Get healthy instances
healthy = await consul.get_healthy_service("auth_service")
```

## Registered Services

### Infrastructure Services (9)

| Service | Port | Type |
|---------|------|------|
| postgres-grpc | 50061 | gRPC |
| redis-grpc | 50055 | gRPC |
| neo4j-grpc | 50063 | gRPC |
| nats-grpc | 50056 | gRPC |
| mqtt-grpc | 50053 | gRPC |
| minio-grpc | 50051 | gRPC |
| qdrant-grpc | 50062 | gRPC |
| duckdb-grpc | 50052 | gRPC |
| loki-grpc | 50054 | gRPC |

### Business Services (33)

From isA_user and other repositories, dynamically registered.

## KV Store

### Store Configuration

```bash
# Set value
curl -X PUT http://localhost:8500/v1/kv/config/database/host \
  -d "localhost"

# Get value
curl http://localhost:8500/v1/kv/config/database/host?raw
```

### Python KV Access

```python
# Store config
await consul.kv_put("config/database/host", "localhost")

# Get config
host = await consul.kv_get("config/database/host")

# Watch for changes
async for value in consul.kv_watch("config/database"):
    print(f"Config changed: {value}")
```

## Service Tags

Tags enable filtering and routing:

```json
{
  "Tags": ["api", "v1", "http", "public"]
}
```

### Query by Tag

```bash
curl "http://localhost:8500/v1/catalog/service/auth_service?tag=api"
```

## Consul UI

Access at `http://localhost:8500`:

- **Services** - View all registered services
- **Nodes** - Cluster node status
- **Key/Value** - Configuration browser
- **Intentions** - Service mesh policies

## Health Status

| Status | Description |
|--------|-------------|
| `passing` | All checks pass |
| `warning` | Some warnings |
| `critical` | Service unhealthy |

### Check Service Health

```bash
curl http://localhost:8500/v1/health/service/auth_service | jq '.[].Checks'
```

## Kubernetes Integration

### Service Sync

Consul syncs with Kubernetes services:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: auth-service
  annotations:
    consul.hashicorp.com/service-sync: "true"
spec:
  ports:
    - port: 8201
```

### Consul Connect (Service Mesh)

```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    consul.hashicorp.com/connect-inject: "true"
```

## Monitoring

### Service Count

```bash
curl http://localhost:8500/v1/catalog/services | jq 'keys | length'
```

### Health Summary

```bash
curl http://localhost:8500/v1/health/state/critical
curl http://localhost:8500/v1/health/state/warning
curl http://localhost:8500/v1/health/state/passing
```

## Troubleshooting

### Service Not Registered

```bash
# Check agent services
curl http://localhost:8500/v1/agent/services

# Check agent health
curl http://localhost:8500/v1/agent/self
```

### Health Check Failing

```bash
# View check details
curl http://localhost:8500/v1/health/checks/auth_service

# Test health endpoint directly
curl http://localhost:8201/health
```

## Next Steps

- [Gateway](./gateway) - APISIX routing
- [SDK](./sdk) - Python client library
- [Deployment](./deployment) - Production setup
