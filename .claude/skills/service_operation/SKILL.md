---
name: api-service-operations
description: API service operations for isA platform. Check Consul registration, clear stale records, trigger APISIX sync, and test service endpoints. Use when debugging service registration, fixing routing issues, or verifying service health via gateway.
disable-model-invocation: true
---

# API Service Operations for isA Platform

Operations for managing API services in Consul and APISIX gateway.

## Available Operations

1. **Check service status** - Verify Consul registration and APISIX routes
2. **Clear stale records** - Remove old/dead service registrations from Consul
3. **Trigger APISIX sync** - Sync Consul services to APISIX routes
4. **Test service endpoint** - Verify service is accessible via APISIX gateway
5. **Full service check** - Run all operations for a service

## Configuration

### Environment Details

- **Consul**: `localhost:8500` (via Kind NodePort 30500)
- **APISIX Admin**: `localhost:9180` (via Kind NodePort 30180)
- **APISIX Gateway**: `localhost:9080` (via Kind NodePort 30080)
- **APISIX Admin Key**: `edd1c9f034335f136f87ad84b625c8f1`
- **Namespace**: `isa-cloud-local`

### Service Host for Local Dev

Services running on Mac need to register with `SERVICE_HOST=192.168.65.254` (Docker gateway IP) to be reachable from Kind cluster.

## Operation 1: Check Service Status

### Check Consul Registration

```bash
# List all registered services
curl -s http://localhost:8500/v1/catalog/services | jq 'keys[]' | grep -v consul

# Check specific service registration
SERVICE_NAME="model_service"  # or mcp_service, data, etc.
curl -s http://localhost:8500/v1/catalog/service/${SERVICE_NAME} | jq '.[0] | {
  ServiceID: .ServiceID,
  ServiceAddress: .ServiceAddress,
  ServicePort: .ServicePort
}'

# Check service metadata (base_path for APISIX routing)
curl -s http://localhost:8500/v1/catalog/service/${SERVICE_NAME} | jq '.[0].ServiceMeta | {
  api_path,
  base_path,
  version,
  route_count
}'

# Check service health status
curl -s http://localhost:8500/v1/health/service/${SERVICE_NAME} | jq '.[0] | {
  ServiceID: .Service.ID,
  Status: .Checks[].Status
}'
```

### Check APISIX Routes

```bash
SERVICE_NAME="model_service"
ADMIN_KEY="edd1c9f034335f136f87ad84b625c8f1"

# List all routes
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq '.list[] | {name: .value.name, uris: .value.uris}'

# Check specific service routes
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq ".list[] | select(.value.name | test(\"${SERVICE_NAME}\")) | {name: .value.name, uris: .value.uris}"

# Count total routes
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: ${ADMIN_KEY}" | jq '.total'
```

## Operation 2: Clear Stale Records

### Identify Stale Registrations

Stale registrations occur when:
- Service crashed without deregistering
- Service restarted with different hostname
- Old container IDs in service ID

```bash
SERVICE_NAME="model_service"

# List all instances of a service
curl -s http://localhost:8500/v1/catalog/service/${SERVICE_NAME} | jq '.[] | {
  ServiceID: .ServiceID,
  ServiceAddress: .ServiceAddress,
  ServicePort: .ServicePort
}'

# Check health - critical/warning services are likely stale
curl -s http://localhost:8500/v1/health/service/${SERVICE_NAME}?passing=false | jq '.[] | {
  ServiceID: .Service.ID,
  Status: .Checks[].Status
}'
```

### Remove Stale Registration

```bash
# Deregister specific service by ID
SERVICE_ID="model_service-localhost-8082"  # Example stale registration
curl -s -X PUT "http://localhost:8500/v1/agent/service/deregister/${SERVICE_ID}"

# Verify removal
curl -s http://localhost:8500/v1/catalog/service/${SERVICE_NAME} | jq length
```

### Bulk Cleanup - Remove All Instances of a Service

```bash
SERVICE_NAME="model_service"

# Get all service IDs and deregister each
for SERVICE_ID in $(curl -s http://localhost:8500/v1/catalog/service/${SERVICE_NAME} | jq -r '.[].ServiceID'); do
  echo "Deregistering: ${SERVICE_ID}"
  curl -s -X PUT "http://localhost:8500/v1/agent/service/deregister/${SERVICE_ID}"
done
```

## Operation 3: Trigger APISIX Sync

The consul-apisix-sync CronJob runs every 5 minutes. To trigger immediately:

### Manual Sync via Kubernetes Job

```bash
# Trigger sync job
kubectl create job consul-apisix-sync-manual-$(date +%s) \
  --from=cronjob/consul-apisix-sync \
  -n isa-cloud-local

# Wait for completion
sleep 10

# Check sync logs
kubectl logs -n isa-cloud-local -l app=consul-apisix-sync --tail=50
```

### Verify Sync Results

```bash
# Check total routes after sync
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.total'

# Check if specific service has routes
SERVICE_NAME="model_service"
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | \
  jq ".list[] | select(.value.name | test(\"${SERVICE_NAME}\"))"
```

### Sync Script Details

The sync job reads service metadata from Consul and creates APISIX routes:
- Uses `api_path` or `base_path` from service metadata
- Creates main route: `/{api_path}` and `/{api_path}/*`
- Creates health route: `/{api_path}/health`
- Configures CORS, rate limiting, and request-id plugins

Services without `api_path` or `base_path` metadata are skipped.

## Operation 4: Test Service Endpoint

### Test via APISIX Gateway

```bash
# Test health endpoint
API_PATH="/api/v1/models"  # Adjust based on service
curl -s http://localhost:9080${API_PATH}/health | jq .

# Test main endpoint
curl -s http://localhost:9080${API_PATH} | head -c 500

# Test with verbose output (see headers)
curl -v http://localhost:9080${API_PATH}/health 2>&1 | head -30
```

### Common API Paths by Service

| Service | API Path | Health Endpoint |
|---------|----------|-----------------|
| model_service | /api/v1/models | /api/v1/models/health |
| mcp_service | /api/v1/mcp | /api/v1/mcp/health |
| data_service | /api/v1/digital | /api/v1/digital/health |
| account_service | /api/v1/accounts | /api/v1/accounts/health |
| auth_service | /api/v1/auth | /api/v1/auth/health |

### Test Direct (Bypass APISIX)

If APISIX test fails, verify service is running directly:

```bash
# Direct health check (adjust port)
curl -s http://localhost:8082/health | jq .  # model_service
curl -s http://localhost:8081/health | jq .  # mcp_service
curl -s http://localhost:8084/health | jq .  # data_service
```

## Operation 5: Full Service Check

Run all operations for a service in sequence:

### Full Check Script

```bash
#!/bin/bash
SERVICE_NAME="${1:-model_service}"
API_PATH="${2:-/api/v1/models}"
ADMIN_KEY="edd1c9f034335f136f87ad84b625c8f1"

echo "=== Checking ${SERVICE_NAME} ==="

# 1. Check Consul registration
echo -e "\n[1/4] Consul Registration:"
CONSUL_DATA=$(curl -s http://localhost:8500/v1/catalog/service/${SERVICE_NAME})
if [ "$(echo $CONSUL_DATA | jq length)" -gt 0 ]; then
  echo $CONSUL_DATA | jq '.[0] | {ServiceID, ServiceAddress, ServicePort}'
  echo "Metadata:"
  echo $CONSUL_DATA | jq '.[0].ServiceMeta | {api_path, base_path}'
else
  echo "NOT REGISTERED in Consul!"
fi

# 2. Check health status
echo -e "\n[2/4] Health Status:"
curl -s http://localhost:8500/v1/health/service/${SERVICE_NAME} | jq '.[0].Checks[] | {Name, Status}'

# 3. Check APISIX routes
echo -e "\n[3/4] APISIX Routes:"
curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: ${ADMIN_KEY}" | \
  jq ".list[] | select(.value.name | test(\"${SERVICE_NAME}\")) | {name: .value.name, uris: .value.uris}"

# 4. Test via gateway
echo -e "\n[4/4] Gateway Test (${API_PATH}/health):"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" http://localhost:9080${API_PATH}/health)
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE:")

if [ "$HTTP_CODE" = "200" ]; then
  echo "SUCCESS (HTTP 200)"
  echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
else
  echo "FAILED (HTTP ${HTTP_CODE})"
  echo "$BODY"
fi

echo -e "\n=== Check Complete ==="
```

### Usage Examples

```bash
# Check model_service
/api-service-operations
# Then say: "Full check for model_service at /api/v1/models"

# Check mcp_service
/api-service-operations
# Then say: "Check mcp_service registration and test /api/v1/mcp/health"

# Clear stale and re-sync
/api-service-operations
# Then say: "Clear stale records for data service and trigger APISIX sync"
```

## Operation 6: Auto-Cleanup Stale Entries

Automatically find and remove stale Consul registrations and orphaned APISIX routes.

### Usage

```bash
# Dry-run first (report only, no changes)
./scripts/consul-cleanup.sh

# Apply cleanup
./scripts/consul-cleanup.sh --apply

# Explicit environment
./scripts/consul-cleanup.sh local --apply
```

### What It Cleans

1. **Stale Consul services** — instances with critical health checks (crashed without deregistering)
2. **Non-standard names** — reports services not following `{name}_service` convention
3. **Orphaned APISIX routes** — routes pointing to services no longer registered in Consul
4. **Duplicate registrations** — same service registered multiple times

### Typical Workflow After Service Rename or Restart

```bash
# 1. Check what's stale (dry-run)
./scripts/consul-cleanup.sh

# 2. Clean up stale entries
./scripts/consul-cleanup.sh --apply

# 3. Re-sync APISIX routes from Consul
./scripts/trigger-sync.sh

# 4. Verify everything is healthy
./scripts/service-check.sh --all
```

## Troubleshooting

### Service Not in Consul

**Cause**: Service not registering or registration failed

**Fix**:
1. Check service logs for Consul registration errors
2. Verify `CONSUL_ENABLED=true` in service's dev.env
3. Verify `SERVICE_HOST=192.168.65.254` for local dev
4. Check Consul is accessible: `curl http://localhost:8500/v1/status/leader`

### Service in Consul but No APISIX Route

**Cause**: Missing `api_path` or `base_path` in service metadata

**Fix**:
1. Check service metadata: `curl -s http://localhost:8500/v1/catalog/service/${SERVICE_NAME} | jq '.[0].ServiceMeta'`
2. Verify `base_path` or `api_path` is set in routes_registry.py
3. Trigger manual sync after fixing

### APISIX Returns 502 Bad Gateway

**Cause**: APISIX can't reach the service (wrong address)

**Fix**:
1. Check service address in Consul - should be `192.168.65.254`, NOT `localhost`
2. Fix `SERVICE_HOST=192.168.65.254` in service's dev.env
3. Restart service and re-sync APISIX

### APISIX Returns 404 Not Found

**Cause**: Route doesn't exist or wrong path

**Fix**:
1. Check route exists: `curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: ${ADMIN_KEY}" | jq '.list[].value.name'`
2. Verify correct API path being used
3. Trigger manual sync if route missing

## Consul Registration Standard

All isA platform services MUST follow this standard pattern for Consul registration.

### Naming Convention

Service names use the format `{name}_service` (e.g., `model_service`, `agent_service`, `data_service`).

### Required ConsulRegistry Arguments

```python
consul_registry = ConsulRegistry(
    service_name="example_service",          # {name}_service format
    service_port=settings.port,
    consul_host=settings.consul_host,        # default: "localhost"
    consul_port=settings.consul_port,        # default: 8500
    service_host="127.0.0.1",               # for local dev
    tags=["v1", "example", "category"],      # MUST include version tag
    meta=consul_meta,                        # see meta structure below
    health_check_type="ttl",                 # MUST be "ttl" (not "http")
)
```

### Standard Meta Dict

```python
consul_meta = {
    "version": "1.0.0",
    "capabilities": "cap1,cap2,cap3",
    "health": "/health",
    "methods": "GET,POST",
    "base_path": "/api/v1/example",          # required for APISIX sync
    "route_count": str(len(routes)),
    "protected_count": str(protected),
    "public_count": str(public),
}
```

### Standard Tags

Tags MUST include a version tag (`v1`, `v2`) as the first element:
```python
tags = ["v1", "service-category", "feature1", "feature2"]
```

### Standard Lifespan Pattern

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: register + start heartbeat
    consul_registry = ConsulRegistry(...)
    consul_registry.register()
    consul_registry.start_maintenance()

    yield

    # Shutdown: stop heartbeat + deregister
    consul_registry.stop_maintenance()
    consul_registry.deregister()
```

### Service Registry Checklist

Before deploying a service, verify:
- [ ] Service name follows `{name}_service` convention
- [ ] `health_check_type="ttl"` (not `"http"`)
- [ ] Tags include version tag (`v1`)
- [ ] Meta includes `base_path`, `capabilities`, `health`, `methods`, `version`
- [ ] Shutdown calls `stop_maintenance()` before `deregister()`
- [ ] `service_host` is `127.0.0.1` for local dev

### All Platform Services

| # | Service Name | Port | Project | Base Path |
|---|-------------|------|---------|-----------|
| 1 | model_service | 8082 | isA_Model | /api/v1/models |
| 2 | mcp_service | 8081 | isA_MCP | /api/v1/mcp |
| 3 | data_service | 8084 | isA_Data | /api/v1/digital |
| 4 | agent_service | 8080 | isA_Agent | /api/v1/agents |
| 5 | web_service | 8083 | isA_OS | /api/v1/web |
| 6 | cloud_os_service | 8085 | isA_OS | /api/v1/vms |
| 7 | pool_manager_service | 8086 | isA_OS | /api/v1/pools |
| 8 | python_repl_service | 8087 | isA_OS | /api/v1/python_repl |
| 9 | auth_service | 8201 | isA_User | /api/v1/auth |
| 10 | account_service | 8202 | isA_User | /api/v1/accounts |
| 11 | session_service | 8203 | isA_User | /api/v1/sessions |
| 12 | authorization_service | 8204 | isA_User | /api/v1/authorization |
| 13 | audit_service | 8205 | isA_User | /api/v1/audit |
| 14 | notification_service | 8206 | isA_User | /api/v1/notifications |
| 15 | payment_service | 8207 | isA_User | /api/v1/payments |
| 16 | wallet_service | 8208 | isA_User | /api/v1/wallets |
| 17 | storage_service | 8209 | isA_User | /api/v1/storage |
| 18 | membership_service | 8210 | isA_User | /api/v1/memberships |
| 19 | subscription_service | 8211 | isA_User | /api/v1/subscriptions |
| 20 | document_service | 8212 | isA_User | /api/v1/documents |
| 21 | memory_service | 8223 | isA_User | /api/v1/memory |

## Quick Reference

### Service Registration Checklist

For a service to work via APISIX:

- [ ] `CONSUL_ENABLED=true` in dev.env
- [ ] `SERVICE_HOST=192.168.65.254` in dev.env (for local dev)
- [ ] `base_path` or `api_path` in routes_registry.py metadata
- [ ] Service import uses `from isa_common.consul_client import ConsulRegistry`
- [ ] Service started and running
- [ ] APISIX sync completed

### Common Commands

```bash
# List all Consul services
curl -s http://localhost:8500/v1/catalog/services | jq 'keys[]'

# Check service registration
curl -s http://localhost:8500/v1/catalog/service/SERVICE_NAME | jq '.[0]'

# Deregister service
curl -X PUT http://localhost:8500/v1/agent/service/deregister/SERVICE_ID

# Trigger APISIX sync
kubectl create job sync-$(date +%s) --from=cronjob/consul-apisix-sync -n isa-cloud-local

# Check APISIX routes
curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.total'

# Test via gateway
curl -s http://localhost:9080/api/v1/SERVICE_PATH/health
```
