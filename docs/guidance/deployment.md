# Deployment

ArgoCD GitOps deployment and Helm chart management.

## Overview

isA Cloud uses GitOps with:

- **ArgoCD** - Continuous deployment
- **Helm** - Package management
- **Multi-environment** - dev, staging, production

## Environments

| Environment | Cluster | Namespace | Branch |
|-------------|---------|-----------|--------|
| **Local** | KIND | isa-cloud-local | develop |
| **Staging** | EKS | isa-cloud-staging | main |
| **Production** | EKS/GKE | isa-cloud-production | production |

### Namespace Convention

Each environment has its own isolated namespace:

```
isa-cloud-local       # Local KIND development
isa-cloud-staging     # Staging environment
isa-cloud-production  # Production environment
```

Deployment scripts and manifests are organized by environment:

```
deployments/kubernetes/
├── local/              # Local KIND cluster
│   ├── scripts/
│   ├── manifests/
│   └── values/
├── staging/            # Staging environment
│   ├── scripts/
│   ├── manifests/
│   ├── values/
│   └── secrets/
└── production/         # Production environment
    ├── scripts/
    ├── manifests/
    ├── values/
    └── secrets/
```

## GitOps Workflow

```
Developer Push Code
        │
        ▼
GitHub Actions CI
  ├─ Lint & Test
  ├─ Build Docker Images
  ├─ Push to Harbor/ECR
  └─ Security Scan (Trivy)
        │
        ▼
Update Image Tag in Git
        │
        ▼
ArgoCD Detects Changes (30s)
        │
        ▼
ArgoCD Syncs to Kubernetes
        │
        ▼
Rolling Update
        │
        ▼
Service Registers to Consul
        │
        ▼
APISIX Syncs Routes
```

## ArgoCD Applications

### App-of-Apps Pattern

```
deployments/argocd/
├── applications/              # Root applications
│   ├── isa-cloud-dev.yaml
│   ├── isa-cloud-staging.yaml
│   └── isa-cloud-production.yaml
└── apps/                      # Child applications
    ├── dev/
    ├── staging/
    └── production/
```

### Root Application

```yaml
# deployments/argocd/applications/isa-cloud-staging.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: isa-cloud-staging
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/isA_Cloud
    targetRevision: main
    path: deployments/argocd/apps/staging
  destination:
    server: https://kubernetes.default.svc
    namespace: isa-cloud-staging
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Child Application

```yaml
# deployments/argocd/apps/staging/auth-service.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: auth-service
spec:
  source:
    repoURL: https://github.com/org/isA_Cloud
    path: deployments/charts/isa-service
    helm:
      valueFiles:
        - ../../kubernetes/staging/values/auth-service.yaml
```

## Helm Charts

### Generic Service Chart

```
deployments/charts/isa-service/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── configmap.yaml
    ├── secret.yaml
    ├── hpa.yaml
    └── ingress.yaml
```

### Values File

```yaml
# deployments/kubernetes/staging/values/auth-service.yaml
replicaCount: 2

image:
  repository: harbor.isa.io/isa-cloud/auth-service
  tag: "1.0.0"
  pullPolicy: Always

service:
  type: ClusterIP
  port: 8201

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"

env:
  - name: ISA_ENV
    value: staging
  - name: POSTGRES_HOST
    valueFrom:
      secretKeyRef:
        name: database-secrets
        key: host

consul:
  enabled: true
  serviceName: auth_service

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilization: 70
```

## Deploy Commands

### Deploy Script

```bash
# Deploy single service
./deployments/scripts/deploy.sh auth staging

# Deploy all user services
./deployments/scripts/deploy.sh user all staging

# Deploy everything
./deployments/scripts/deploy.sh all staging
```

### Manual Helm Deploy

```bash
helm upgrade --install auth-service \
  deployments/charts/isa-service \
  -f deployments/kubernetes/staging/values/auth-service.yaml \
  -n isa-cloud-staging
```

## Image Management

### Build and Push

```bash
# Build service image
docker build -t harbor.isa.io/isa-cloud/auth-service:1.0.0 \
  -f services/auth/Dockerfile .

# Push to registry
docker push harbor.isa.io/isa-cloud/auth-service:1.0.0
```

### Automated Image Update

GitHub Actions updates image tags:

```yaml
# .github/workflows/cd-update-images.yaml
- name: Update image tag
  run: |
    yq -i '.image.tag = "${{ github.sha }}"' \
      deployments/kubernetes/staging/values/${{ matrix.service }}.yaml

    git commit -am "Update ${{ matrix.service }} to ${{ github.sha }}"
    git push
```

## Environment Configuration

### Staging

```yaml
# deployments/kubernetes/staging/values/common.yaml
global:
  environment: staging
  domain: staging.isa.io
  registry: harbor.staging.isa.io

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"

replicas:
  min: 2
  max: 5
```

### Production

```yaml
# deployments/kubernetes/production/values/common.yaml
global:
  environment: production
  domain: isa.io
  registry: harbor.isa.io

resources:
  requests:
    memory: "512Mi"
    cpu: "200m"
  limits:
    memory: "1Gi"
    cpu: "1000m"

replicas:
  min: 3
  max: 20

# HA settings
podDisruptionBudget:
  minAvailable: 2

topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
```

## Secrets Management

### Template Secrets

```yaml
# deployments/kubernetes/staging/secrets/database-secrets.yaml.template
apiVersion: v1
kind: Secret
metadata:
  name: database-secrets
type: Opaque
stringData:
  host: "${POSTGRES_HOST}"
  password: "${POSTGRES_PASSWORD}"
```

### Apply Secrets

```bash
envsubst < secrets/database-secrets.yaml.template | kubectl apply -f -
```

### External Secrets (Production)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: database-secrets
spec:
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: database-secrets
  data:
    - secretKey: host
      remoteRef:
        key: isa-cloud/production/postgres
        property: host
```

## Terraform (AWS Infrastructure)

### Module Structure

```
deployments/terraform/
├── modules/
│   ├── secrets/
│   ├── networking/
│   ├── storage/
│   └── ecs-cluster/
└── environments/
    ├── staging/
    │   ├── main.tf
    │   └── terraform.tfvars
    └── production/
        ├── main.tf
        └── terraform.tfvars
```

### Deploy Infrastructure

```bash
cd deployments/terraform/environments/staging
terraform init
terraform plan
terraform apply
```

## Monitoring Deployment

### ArgoCD UI

Access at `https://argocd.isa.io`:

- View sync status
- Check application health
- Trigger manual sync
- View deployment history

### kubectl Commands

```bash
# Check rollout status
kubectl rollout status deployment/auth-service -n isa-cloud-staging

# View pods
kubectl get pods -n isa-cloud-staging -l app=auth-service

# Check events
kubectl get events -n isa-cloud-staging --sort-by='.lastTimestamp'
```

## Rollback

### ArgoCD Rollback

```bash
argocd app rollback auth-service --revision 5
```

### Helm Rollback

```bash
helm rollback auth-service 1 -n isa-cloud-staging
```

### kubectl Rollback

```bash
kubectl rollout undo deployment/auth-service -n isa-cloud-staging
```

## Next Steps

- [CI/CD](./cicd) - GitHub Actions pipelines
- [Testing](./testing) - Contract-driven development
- [Operations](./operations) - Monitoring & scripts
