# isA Cloud Deployments

Complete deployment guide for the isA platform across local, staging, and production environments.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEPLOYMENT PIPELINE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Developer Push                                                             │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────────────────┐   │
│  │  Git    │────▶│ Harbor  │────▶│ ArgoCD  │────▶│    Kubernetes       │   │
│  │  Repo   │     │Registry │     │ GitOps  │     │    (Kind/EKS)       │   │
│  └─────────┘     └─────────┘     └─────────┘     └─────────────────────┘   │
│       │                                                 │                   │
│       │         ┌─────────────────────────────────────┐│                   │
│       └────────▶│        Terraform (Cloud Infra)      ││                   │
│                 └─────────────────────────────────────┘│                   │
│                                                        │                   │
│                                                        ▼                   │
│                 ┌─────────────────────────────────────────────────────┐    │
│                 │                  RUNTIME                             │    │
│                 │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │    │
│                 │  │ APISIX  │  │ Consul  │  │  Pods   │  │ Redis/  │ │    │
│                 │  │ Gateway │─▶│Discovery│─▶│Services │─▶│Postgres │ │    │
│                 │  └─────────┘  └─────────┘  └─────────┘  └─────────┘ │    │
│                 └─────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
deployments/
├── README.md                    # This file
├── argocd/                      # ArgoCD GitOps configurations
│   ├── applications/            # Root app-of-apps definitions
│   │   ├── isa-cloud-dev.yaml
│   │   ├── isa-cloud-staging.yaml
│   │   └── isa-cloud-production.yaml
│   ├── apps/                    # Child Application manifests
│   │   ├── dev/                 # Dev environment apps
│   │   ├── staging/             # Staging environment apps
│   │   └── production/          # Production environment apps
│   └── bootstrap/               # Initial ArgoCD setup
├── charts/                      # Helm charts
│   └── isa-service/             # Generic chart for all isA services
├── kubernetes/                  # Environment-specific configs
│   ├── local/                   # Local Kind cluster
│   │   ├── kind-config.yaml     # Kind cluster configuration
│   │   ├── values/              # Helm values (NodePort)
│   │   ├── manifests/           # Custom K8s manifests
│   │   └── scripts/             # Local cluster scripts
│   ├── staging/                 # Staging environment
│   │   ├── values/              # Helm values (ClusterIP)
│   │   └── secrets/             # Secret templates
│   ├── production/              # Production environment
│   │   ├── values/              # Helm values (HA configs)
│   │   ├── scripts/             # Production deploy scripts
│   │   └── secrets/             # Secret templates
│   └── _legacy/                 # Old Kustomize configs (archived)
├── scripts/                     # Deployment scripts
│   ├── build-and-push.sh        # Build images and push to Harbor
│   └── deploy.sh                # Deploy services with Helm
└── terraform/                   # Cloud infrastructure as code
    ├── modules/                 # Reusable Terraform modules
    └── environments/            # Environment-specific configs
```

## Services Overview

### Core Services
| Service | Port | Description |
|---------|------|-------------|
| mcp     | 8081 | Model Control Plane |
| model   | 8082 | Model Service |
| agent   | 8080 | Agent Service |
| data    | 8084 | Data Service |

### OS Services
| Service | Port | Description |
|---------|------|-------------|
| web-services  | 8083 | Web automation (Playwright) |
| cloud-os      | 8086 | Cloud OS orchestration |
| python-repl   | 8085 | Python REPL sandbox |
| pool-manager  | 8090 | Resource pool management |

### User Microservices (31 services)
| Range | Services |
|-------|----------|
| 8201-8210 | auth, account, profile, preference, notification, subscription, payment, billing, invoice, usage |
| 8211-8220 | quota, rate-limit, api-key, oauth, sso, mfa, session, audit, activity, analytics |
| 8221-8229 | report, export, import, webhook, integration, team, organization, role, permission |
| 8249-8250 | invitation, membership |

---

## Quick Start

### 1. Local Development (Kind)

```bash
# Create Kind cluster
cd kubernetes/local
./scripts/kind-setup.sh

# Or manually:
kind create cluster --config kind-config.yaml

# Create namespace
kubectl create namespace isa-cloud-staging

# Add Helm repos
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo add nats https://nats-io.github.io/k8s/helm/charts
helm repo add qdrant https://qdrant.github.io/qdrant-helm
helm repo add neo4j https://neo4j.github.io/helm-charts
helm repo add apisix https://charts.apiseven.com
helm repo add emqx https://repos.emqx.io/charts
helm repo add minio https://charts.min.io
helm repo add harbor https://helm.goharbor.io
helm repo update

# Install infrastructure
helm install postgresql bitnami/postgresql -n isa-cloud-staging -f values/postgresql.yaml
helm install redis bitnami/redis -n isa-cloud-staging -f values/redis.yaml
helm install minio minio/minio -n isa-cloud-staging -f values/minio.yaml
helm install consul hashicorp/consul -n isa-cloud-staging -f values/consul.yaml
helm install nats nats/nats -n isa-cloud-staging -f values/nats.yaml
helm install qdrant qdrant/qdrant -n isa-cloud-staging -f values/qdrant.yaml
helm install neo4j neo4j/neo4j -n isa-cloud-staging -f values/neo4j.yaml
helm install emqx emqx/emqx -n isa-cloud-staging -f values/emqx.yaml
helm install harbor harbor/harbor -n isa-cloud-staging -f values/harbor.yaml

# etcd (for APISIX)
kubectl apply -f manifests/etcd.yaml -n isa-cloud-staging

# APISIX
helm install apisix apisix/apisix -n isa-cloud-staging -f values/apisix.yaml
```

### 2. Deploy Services

```bash
# Using deploy.sh script
cd deployments/scripts

# Deploy individual services
./deploy.sh mcp                    # Deploy MCP service
./deploy.sh model                  # Deploy Model service
./deploy.sh agent                  # Deploy Agent service
./deploy.sh data                   # Deploy Data service

# Deploy OS services
./deploy.sh web-services
./deploy.sh cloud-os
./deploy.sh python-repl
./deploy.sh pool-manager

# Deploy user microservices
./deploy.sh user auth              # Deploy auth service
./deploy.sh user list              # List all user services
./deploy.sh user all               # Deploy ALL 31 user services

# Batch deployments
./deploy.sh all                    # Deploy all core + OS services
./deploy.sh all-core               # Deploy all core services
./deploy.sh all-os                 # Deploy all OS services

# With specific namespace/version
./deploy.sh mcp isa-cloud-staging v1.2.3
./deploy.sh agent isa-cloud-production v2.0.0

# Management commands
./deploy.sh list                   # List deployed services
./deploy.sh rollback mcp-service   # Rollback a service
./deploy.sh uninstall mcp-service  # Uninstall a service
./deploy.sh logs mcp-service       # Stream service logs
```

### 3. Build and Push Images

```bash
cd deployments/scripts

# Build and push to Harbor
./build-and-push.sh mcp v1.2.3
./build-and-push.sh model v1.2.3
./build-and-push.sh all            # Build all services
```

---

## Environment Configuration

### Local (Kind)
- **Namespace**: `isa-cloud-staging`
- **Service Type**: NodePort (direct localhost access)
- **Harbor**: `harbor.local:30443`

| Service    | Localhost Port |
|------------|----------------|
| PostgreSQL | 5432           |
| Redis      | 6379           |
| MinIO      | 9000, 9001     |
| Consul     | 8500           |
| NATS       | 4222           |
| Qdrant     | 6333, 6334     |
| Neo4j      | 7474, 7687     |
| EMQX       | 1883, 18083    |
| APISIX     | 9080, 9180     |
| Harbor     | 30443          |

### Staging
- **Namespace**: `isa-cloud-staging`
- **Service Type**: ClusterIP (internal access)
- **Harbor**: `harbor.staging.isa.io`

### Production
- **Namespace**: `isa-cloud-production`
- **Service Type**: ClusterIP with HA
- **Harbor**: `harbor.isa.io`
- **Deployment**: Manual approval required

---

## ArgoCD (GitOps)

### App-of-Apps Pattern

```
isa-cloud-staging (root app)
    └── argocd/apps/staging/
        ├── mcp-service.yaml
        ├── model-service.yaml
        ├── agent-service.yaml
        ├── data-service.yaml
        ├── os-services.yaml
        └── user-services-appset.yaml (ApplicationSet for 31 microservices)
```

### Setup ArgoCD

```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Apply bootstrap
kubectl apply -f argocd/bootstrap/install.yaml

# Apply root application
kubectl apply -f argocd/applications/isa-cloud-staging.yaml

# Get admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# Port-forward UI
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

### Sync Applications

```bash
# Sync all apps
argocd app sync isa-cloud-staging

# Sync specific service
argocd app sync mcp-service-staging
argocd app sync user-auth-staging
```

---

## Secrets Management

### Local/Staging (Templates)

```bash
# Copy template
cp kubernetes/staging/secrets/infrastructure-secrets.yaml \
   kubernetes/staging/secrets/infrastructure-secrets.local.yaml

# Edit with actual values
vim kubernetes/staging/secrets/infrastructure-secrets.local.yaml

# Apply
kubectl apply -f kubernetes/staging/secrets/infrastructure-secrets.local.yaml

# Delete local file (don't commit!)
rm kubernetes/staging/secrets/infrastructure-secrets.local.yaml
```

### Production (Recommended: External Secrets)

```bash
# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace

# Configure SecretStore for AWS Secrets Manager
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secrets-manager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-west-2
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
            namespace: external-secrets
EOF
```

### Local Credentials

| Service    | Username   | Password              |
|------------|------------|----------------------|
| PostgreSQL | postgres   | staging_postgres_2024 |
| Redis      | -          | staging_redis_2024    |
| MinIO      | minioadmin | staging_minio_2024    |
| Neo4j      | neo4j      | staging_neo4j_2024    |
| EMQX       | admin      | staging_emqx_2024     |
| APISIX     | admin      | edd1c9f034335f136f87ad84b625c8f1 |
| Harbor     | admin      | Harbor12345           |

---

## Production Deployment

### Prerequisites

```bash
# Verify kubectl context
kubectl config current-context

# Create secrets FIRST
kubectl apply -f kubernetes/production/secrets/infrastructure-secrets.local.yaml
```

### Deploy Infrastructure

```bash
cd kubernetes/production/scripts

# Deploy HA infrastructure (requires confirmation)
./deploy.sh infrastructure

# Check status
./deploy.sh status

# Rollback if needed
./deploy.sh rollback postgresql
```

### Deploy Services (via ArgoCD)

```bash
# Production uses manual sync (no auto-sync)
argocd app sync mcp-service-production
argocd app sync model-service-production

# Or sync all (with caution)
argocd app sync isa-cloud-production
```

---

## Terraform (Cloud Infrastructure)

For AWS/cloud deployments:

```bash
cd terraform/environments/staging

# Initialize
terraform init

# Plan
terraform plan -out=plan.tfplan

# Apply
terraform apply plan.tfplan
```

---

## Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n isa-cloud-staging
kubectl describe pod <pod-name> -n isa-cloud-staging
kubectl logs <pod-name> -n isa-cloud-staging
```

### Check Services
```bash
kubectl get svc -n isa-cloud-staging
kubectl get endpoints -n isa-cloud-staging
```

### Check Helm Releases
```bash
helm list -n isa-cloud-staging
helm history <release-name> -n isa-cloud-staging
```

### Reset Local Cluster
```bash
kind delete cluster --name isa-cloud
./kubernetes/local/scripts/kind-setup.sh
```

---

## Environment URLs

| Environment | API Gateway              | Consul UI                    | Harbor                       |
|-------------|--------------------------|------------------------------|------------------------------|
| Local       | http://localhost:9080    | http://localhost:8500        | https://harbor.local:30443   |
| Staging     | https://api.staging.isa.io | https://consul.staging.isa.io | https://harbor.staging.isa.io |
| Production  | https://api.isa.io       | Internal only                | https://harbor.isa.io        |
