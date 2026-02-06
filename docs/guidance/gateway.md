# API Gateway

Apache APISIX configuration, routing, and plugins.

## Overview

APISIX provides:

- Dynamic routing synchronized from Consul
- Authentication (JWT, API Key)
- Rate limiting and circuit breaking
- CORS and security headers
- SSL/TLS termination
- Prometheus metrics

## Ports

| Port | Purpose |
|------|---------|
| 9080 | HTTP Gateway |
| 9443 | HTTPS Gateway |
| 9180 | Admin API |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    External Traffic                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    APISIX Gateway                           │
│    ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐      │
│    │  Auth   │  │  Rate   │  │  CORS   │  │ Logging │      │
│    │ Plugin  │  │ Limiter │  │ Plugin  │  │ Plugin  │      │
│    └─────────┘  └─────────┘  └─────────┘  └─────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Consul Service Discovery                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Backend Services                         │
└─────────────────────────────────────────────────────────────┘
```

## Route Configuration

### Create Route

```bash
curl -X PUT http://localhost:9180/apisix/admin/routes/1 \
  -H "X-API-KEY: admin-key" \
  -H "Content-Type: application/json" \
  -d '{
    "uri": "/api/v1/users/*",
    "upstream": {
      "type": "roundrobin",
      "discovery_type": "consul",
      "service_name": "auth_service"
    },
    "plugins": {
      "jwt-auth": {},
      "limit-req": {
        "rate": 100,
        "burst": 50
      }
    }
  }'
```

### Route with Consul Discovery

```yaml
routes:
  - uri: /api/v1/auth/*
    upstream:
      discovery_type: consul
      service_name: auth_service
    plugins:
      limit-req:
        rate: 5
        burst: 10

  - uri: /api/v1/users/*
    upstream:
      discovery_type: consul
      service_name: profile_service
    plugins:
      jwt-auth: {}
```

## Consul Integration

### Automatic Route Sync

A CronJob syncs routes from Consul every 5 minutes:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: apisix-consul-sync
spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: sync
              image: isa/apisix-consul-sync
              command: ["python", "sync_routes.py"]
```

### Service Registration

Services auto-register to Consul with tags:
```json
{
  "service": "auth_service",
  "tags": ["api", "v1", "http"],
  "port": 8201,
  "check": {
    "http": "http://localhost:8201/health",
    "interval": "10s"
  }
}
```

## Plugins

### JWT Authentication

```json
{
  "plugins": {
    "jwt-auth": {
      "key": "user-key",
      "secret": "your-secret"
    }
  }
}
```

### Rate Limiting

```json
{
  "plugins": {
    "limit-req": {
      "rate": 100,
      "burst": 50,
      "key_type": "consumer_name"
    },
    "limit-count": {
      "count": 1000,
      "time_window": 3600,
      "key_type": "var",
      "key": "remote_addr"
    }
  }
}
```

### CORS

```json
{
  "plugins": {
    "cors": {
      "allow_origins": "https://app.isa.io",
      "allow_methods": "GET,POST,PUT,DELETE",
      "allow_headers": "Authorization,Content-Type",
      "max_age": 3600
    }
  }
}
```

### Request/Response Transform

```json
{
  "plugins": {
    "response-rewrite": {
      "headers": {
        "X-Server": "isA-Cloud"
      }
    },
    "proxy-rewrite": {
      "uri": "/internal$uri"
    }
  }
}
```

## Rate Limits by Tier

| Endpoint Type | Rate | Burst |
|---------------|------|-------|
| Public (login) | 5/min | 10 |
| Authenticated | 100/min | 200 |
| Admin | 1000/min | 500 |
| Internal | Unlimited | - |

## SSL/TLS Configuration

```yaml
ssl:
  - sni: "api.isa.io"
    cert: |
      -----BEGIN CERTIFICATE-----
      ...
      -----END CERTIFICATE-----
    key: |
      -----BEGIN RSA PRIVATE KEY-----
      ...
      -----END RSA PRIVATE KEY-----
```

## Monitoring

### Prometheus Metrics

```bash
curl http://localhost:9091/apisix/prometheus/metrics
```

Available metrics:
- `apisix_http_status` - HTTP status codes
- `apisix_bandwidth` - Bandwidth usage
- `apisix_http_latency` - Request latency
- `apisix_upstream_status` - Upstream health

### Health Check

```bash
curl http://localhost:9080/apisix/status
```

## Admin API

### List Routes

```bash
curl http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: admin-key"
```

### List Upstreams

```bash
curl http://localhost:9180/apisix/admin/upstreams \
  -H "X-API-KEY: admin-key"
```

### List Consumers

```bash
curl http://localhost:9180/apisix/admin/consumers \
  -H "X-API-KEY: admin-key"
```

## Troubleshooting

### Route Not Working

```bash
# Check route exists
curl http://localhost:9180/apisix/admin/routes/1 -H "X-API-KEY: admin-key"

# Check upstream health
curl http://localhost:9180/apisix/admin/upstreams/1 -H "X-API-KEY: admin-key"
```

### Service Not Found

```bash
# Verify Consul registration
curl http://localhost:8500/v1/catalog/service/auth_service

# Check APISIX logs (replace namespace: isa-cloud-local, isa-cloud-staging, or isa-cloud-production)
kubectl logs -l app=apisix -n isa-cloud-local
```

## Next Steps

- [Discovery](./discovery) - Consul service discovery
- [SDK](./sdk) - Client library
- [Deployment](./deployment) - Production setup
