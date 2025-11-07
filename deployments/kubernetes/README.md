# isA Cloud - Kubernetes Deployment

Multi-cloud Kubernetes deployment for the isA Cloud platform.

## 🎯 Quick Start

### Prerequisites
- **Docker Desktop** - Required for kind
- **kubectl** v1.28+
- **kind** v0.20+ - Local Kubernetes cluster
- `kustomize` (built into kubectl)

### Local Development with kind (Recommended)

**3-Step Quick Start**:
```bash
cd scripts/

# 1. Create kind cluster
./kind-setup.sh

# 2. Build and load images
./kind-build-load.sh

# 3. Deploy services
./kind-deploy.sh
```

**Manual Deployment**:
```bash
# Create kind cluster
kind create cluster --config kind-config.yaml

# Build and load an image
docker build -t redis:staging -f deployments/dockerfiles/Staging/Dockerfile.redis.staging .
kind load docker-image redis:staging --name isa-cloud-local

# Deploy with Kustomize
kubectl apply -k overlays/staging/
```

### Deploy with Kustomize Overlays
```bash
# Staging (kind/local)
kubectl apply -k overlays/staging/

# Production (cloud)
kubectl apply -k overlays/production/
```

### Access Services
With kind port mappings configured:
- **Consul UI**: http://localhost:8500
- **MinIO Console**: http://localhost:9001
- **Grafana**: http://localhost:3000
- **Gateway**: http://localhost:8080

See [QUICK_START.md](./QUICK_START.md) for detailed instructions.

## 📁 Directory Structure

- `base/` - Base Kubernetes manifests
  - `namespace/` - Namespace definitions
  - `infrastructure/` - Consul, Redis, MinIO, NATS, etc.
  - `grpc-services/` - 7 gRPC microservices
  - `gateway/` - Gateway and OpenResty
  - `applications/` - Agent, Model, MCP, User services

- `overlays/` - Environment-specific configurations
  - `dev/` - Development environment
  - `staging/` - Staging environment
  - `production/` - Production environment

- `helm-charts/` - Custom Helm charts (optional)

- `scripts/` - Deployment and management scripts

## 🔧 Management Commands

### View Resources
```bash
# All resources in namespace
kubectl get all -n isa-cloud-staging

# Specific service
kubectl get pods -n isa-cloud-staging -l app=consul

# Logs
kubectl logs -n isa-cloud-staging -l app=consul --tail=100 -f
```

### Port Forwarding (Local Access)
```bash
# Consul UI
kubectl port-forward -n isa-cloud-staging svc/consul 8500:8500

# Grafana
kubectl port-forward -n isa-cloud-staging svc/grafana 3000:3000

# MinIO Console
kubectl port-forward -n isa-cloud-staging svc/minio 9001:9001
```

### Scaling
```bash
# Manual scaling
kubectl scale deployment/gateway -n isa-cloud-staging --replicas=3

# Auto-scaling (HPA)
kubectl autoscale deployment/gateway -n isa-cloud-staging --min=2 --max=10 --cpu-percent=70
```

### Debugging
```bash
# Describe pod
kubectl describe pod <pod-name> -n isa-cloud-staging

# Execute command in pod
kubectl exec -it <pod-name> -n isa-cloud-staging -- /bin/sh

# View events
kubectl get events -n isa-cloud-staging --sort-by='.lastTimestamp'
```

## 🌐 Multi-Cloud Deployment

### AWS EKS
```bash
cd ../terraform/environments/aws-staging/
terraform init
terraform apply

# Update kubeconfig
aws eks update-kubeconfig --region us-east-1 --name isa-cloud-staging

# Deploy
kubectl apply -k ../../kubernetes/overlays/staging/
```

### Google GKE
```bash
cd ../terraform/environments/gcp-staging/
terraform init
terraform apply

# Update kubeconfig
gcloud container clusters get-credentials isa-cloud-staging --region us-central1

# Deploy
kubectl apply -k ../../kubernetes/overlays/staging/
```

### Azure AKS
```bash
cd ../terraform/environments/azure-staging/
terraform init
terraform apply

# Update kubeconfig
az aks get-credentials --resource-group isa-cloud-rg --name isa-cloud-staging

# Deploy
kubectl apply -k ../../kubernetes/overlays/staging/
```

## 📊 Monitoring

Access monitoring dashboards:
```bash
# Grafana
kubectl port-forward -n isa-cloud-staging svc/grafana 3000:3000
# Open http://localhost:3000

# Loki (for logs)
kubectl port-forward -n isa-cloud-staging svc/loki 3100:3100
```

## 🔐 Secrets Management

Using External Secrets Operator (recommended):
```bash
# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets-system --create-namespace

# Secrets will sync from AWS Secrets Manager / GCP Secret Manager / Azure Key Vault
```

## 📚 Documentation

- [Migration Plan](./MIGRATION_PLAN.md) - Detailed migration strategy
- [Architecture](../../docs/architecture.md) - System architecture
- [Troubleshooting](./TROUBLESHOOTING.md) - Common issues and solutions

## 🆘 Support

For issues or questions, check:
- `kubectl get events -n isa-cloud-staging`
- Pod logs: `kubectl logs -n isa-cloud-staging <pod-name>`
- [Kubernetes Docs](https://kubernetes.io/docs/)
