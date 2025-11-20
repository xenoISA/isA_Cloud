# APISIX API Gateway - Kubernetes Deployment

This directory contains the Kubernetes manifests for deploying Apache APISIX as the API Gateway for the isA Cloud platform.

## Components

### 1. etcd (Configuration Storage)
- **Deployment**: StatefulSet with persistent storage
- **Replicas**: 1 (staging) / 3 (production)
- **Port**: 2379 (client), 2380 (peer)
- **Storage**: 1Gi PersistentVolume

### 2. APISIX (API Gateway)
- **Deployment**: Deployment with 2 replicas
- **Image**: apache/apisix:3.14.1-debian
- **Ports**:
  - 9080: HTTP Gateway
  - 9443: HTTPS Gateway
  - 9180: Admin API
  - 9091: Prometheus metrics
  - 9092: Control API

### 3. APISIX Dashboard (Management UI)
- **Deployment**: Deployment with 1 replica
- **Image**: apache/apisix-dashboard:3.0.1-alpine
- **Port**: 9000 (Web UI, exposed as 9010 in kind)
- **Default Credentials**: admin / admin (change in production)

## Access Methods

### Local Development (kind)
With the kind cluster port mappings:
- Gateway: http://localhost:9080
- Admin API: http://localhost:9180
- Dashboard: http://localhost:9010

### Kubernetes Cluster (kubectl port-forward)
```bash
# Gateway
kubectl port-forward -n isa-cloud-staging svc/apisix-gateway 9080:9080

# Admin API
kubectl port-forward -n isa-cloud-staging svc/apisix-gateway 9180:9180

# Dashboard
kubectl port-forward -n isa-cloud-staging svc/apisix-dashboard 9010:9000
```

## Configuration

The APISIX configuration is managed through a ConfigMap (`apisix-config`) that includes:
- etcd connection settings
- Plugin configurations
- Admin API settings
- Nginx runtime settings

## Plugins Enabled

- prometheus - Metrics collection
- consul-kv - Consul integration
- request-id - Request tracking
- zipkin - Distributed tracing
- cors - Cross-Origin Resource Sharing
- jwt-auth - JWT authentication
- key-auth - API key authentication
- limit-count - Rate limiting (counter-based)
- limit-req - Rate limiting (leaky bucket)
- limit-conn - Connection limiting
- proxy-rewrite - Request/response rewriting
- response-rewrite - Response modification
- openid-connect - OIDC authentication

## Deployment

### Using Kustomize
```bash
# Deploy APISIX only
kubectl apply -k deployments/kubernetes/base/infrastructure/apisix/

# Deploy entire infrastructure (includes APISIX)
kubectl apply -k deployments/kubernetes/overlays/staging/
```

### Verify Deployment
```bash
# Check pods
kubectl get pods -n isa-cloud-staging -l component=api-gateway

# Check services
kubectl get svc -n isa-cloud-staging -l component=api-gateway

# Check APISIX status
curl http://localhost:9080/apisix/status

# Check Admin API
curl http://localhost:9180/apisix/admin/routes \
  -H 'X-API-KEY: edd1c9f034335f136f87ad84b625c8f1'
```

## Managing Routes

### Using Admin API
```bash
# Create a route
curl http://localhost:9180/apisix/admin/routes/1 \
  -H 'X-API-KEY: edd1c9f034335f136f87ad84b625c8f1' \
  -X PUT -d '{
    "uri": "/api/v1/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "service-name:8080": 1
      }
    }
  }'

# List routes
curl http://localhost:9180/apisix/admin/routes \
  -H 'X-API-KEY: edd1c9f034335f136f87ad84b625c8f1'
```

### Using Dashboard
1. Open http://localhost:9010
2. Login with admin / admin
3. Navigate to Routes section
4. Create/edit routes using the visual interface

## Monitoring

### Prometheus Metrics
APISIX exposes Prometheus metrics on port 9091:
```bash
curl http://localhost:9091/apisix/prometheus/metrics
```

### Logs
```bash
# APISIX logs
kubectl logs -n isa-cloud-staging -l app=apisix -f

# etcd logs
kubectl logs -n isa-cloud-staging -l app=etcd -f

# Dashboard logs
kubectl logs -n isa-cloud-staging -l app=apisix-dashboard -f
```

## Scaling

### APISIX Gateway
```bash
# Scale to 3 replicas
kubectl scale deployment -n isa-cloud-staging apisix --replicas=3
```

### etcd (for production)
Edit the StatefulSet replicas to 3 for high availability:
```yaml
spec:
  replicas: 3
```

## Security Considerations

⚠️ **Important**: Before production deployment:

1. **Change Admin API Key**: Update the admin key in `apisix-configmap.yaml`
2. **Change Dashboard Password**: Update credentials in `apisix-dashboard-deployment.yaml`
3. **Enable TLS**: Configure SSL certificates for HTTPS (port 9443)
4. **Restrict Admin Access**: Limit admin API access to specific IPs
5. **Enable Authentication**: Configure JWT or OAuth for API access

## Troubleshooting

### APISIX not starting
```bash
# Check pod status
kubectl describe pod -n isa-cloud-staging -l app=apisix

# Check logs
kubectl logs -n isa-cloud-staging -l app=apisix --tail=100

# Verify etcd connection
kubectl exec -n isa-cloud-staging -it etcd-0 -- etcdctl endpoint health
```

### Routes not working
```bash
# Check route configuration
curl http://localhost:9180/apisix/admin/routes \
  -H 'X-API-KEY: edd1c9f034335f136f87ad84b625c8f1'

# Check APISIX error logs
kubectl logs -n isa-cloud-staging -l app=apisix | grep ERROR
```

## Migration from Old Gateway

This APISIX deployment replaces the previous NGINX + Go Gateway setup. Key differences:

- **Old**: NGINX (port 80/443) → Go Gateway (port 8000)
- **New**: APISIX (port 9080/9443) with built-in routing and plugins

## Resources

- [APISIX Documentation](https://apisix.apache.org/docs/)
- [APISIX Dashboard Guide](https://apisix.apache.org/docs/dashboard/USER_GUIDE/)
- [APISIX Plugins](https://apisix.apache.org/docs/apisix/plugins/prometheus/)
