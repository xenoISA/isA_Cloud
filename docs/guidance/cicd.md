# CI/CD

GitHub Actions pipelines for build, test, and deployment.

## Overview

CI/CD pipeline stages:

1. **Lint & Test** - Code quality and unit tests
2. **Build** - Docker image creation
3. **Security Scan** - Trivy vulnerability scanning
4. **Push** - Registry upload
5. **Deploy** - ArgoCD sync trigger

## Workflows

### Go Service CI

```yaml
# .github/workflows/ci-golang.yaml
name: Go CI

on:
  push:
    paths:
      - 'services/**'
      - 'go.mod'
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.23'
      - name: golangci-lint
        uses: golangci/golangci-lint-action@v3

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.23'
      - name: Run tests
        run: go test -v -race -coverprofile=coverage.out ./...
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  build:
    needs: [lint, test]
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service:
          - postgres-grpc
          - redis-grpc
          - neo4j-grpc
          - nats-grpc
          - mqtt-grpc
          - minio-grpc
          - qdrant-grpc
          - duckdb-grpc
          - loki-grpc
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: |
          cd services/${{ matrix.service }}
          go build -o ../../bin/${{ matrix.service }} ./cmd/server
```

### Image Build and Push

```yaml
# .github/workflows/cd-update-images.yaml
name: Build and Push Images

on:
  push:
    branches: [main]
    paths:
      - 'services/**'

jobs:
  build-push:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service:
          - postgres-grpc
          - redis-grpc
          - neo4j-grpc
    steps:
      - uses: actions/checkout@v4

      - name: Login to Harbor
        uses: docker/login-action@v3
        with:
          registry: harbor.isa.io
          username: ${{ secrets.HARBOR_USERNAME }}
          password: ${{ secrets.HARBOR_PASSWORD }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: services/${{ matrix.service }}/Dockerfile
          push: true
          tags: |
            harbor.isa.io/isa-cloud/${{ matrix.service }}:${{ github.sha }}
            harbor.isa.io/isa-cloud/${{ matrix.service }}:latest

      - name: Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: harbor.isa.io/isa-cloud/${{ matrix.service }}:${{ github.sha }}
          severity: 'CRITICAL,HIGH'
          exit-code: '1'
```

### Update Image Tags

```yaml
# Continues from build-push job
  update-manifests:
    needs: build-push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main

      - name: Update image tags
        run: |
          for service in postgres-grpc redis-grpc neo4j-grpc; do
            yq -i '.image.tag = "${{ github.sha }}"' \
              deployments/kubernetes/staging/values/${service}.yaml
          done

      - name: Commit and push
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git commit -am "Update images to ${{ github.sha }}"
          git push
```

### Deploy Workflow

```yaml
# .github/workflows/deploy.yaml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        type: choice
        options:
          - staging
          - production
      service:
        description: 'Service to deploy (or "all")'
        required: true
        default: 'all'

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4

      - name: Install ArgoCD CLI
        run: |
          curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
          chmod +x argocd

      - name: Sync ArgoCD
        run: |
          ./argocd login ${{ secrets.ARGOCD_SERVER }} \
            --username admin \
            --password ${{ secrets.ARGOCD_PASSWORD }}

          if [ "${{ inputs.service }}" = "all" ]; then
            ./argocd app sync isa-cloud-${{ inputs.environment }}
          else
            ./argocd app sync ${{ inputs.service }}
          fi
```

## Pipeline Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    Lint     │────▶│    Test     │────▶│    Build    │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Deploy    │◀────│  Update Git │◀────│  Push Image │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │ Trivy Scan  │
                                        └─────────────┘
```

## Branch Strategy

| Branch | Environment | Auto-deploy |
|--------|-------------|-------------|
| `develop` | local | No |
| `main` | staging | Yes |
| `production` | production | Manual |

## Secrets Configuration

Required secrets in GitHub:

| Secret | Description |
|--------|-------------|
| `HARBOR_USERNAME` | Registry username |
| `HARBOR_PASSWORD` | Registry password |
| `ARGOCD_SERVER` | ArgoCD server URL |
| `ARGOCD_PASSWORD` | ArgoCD admin password |
| `KUBECONFIG` | Kubernetes config |
| `AWS_ACCESS_KEY_ID` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |

## Testing in CI

### Unit Tests

```yaml
- name: Unit tests
  run: go test -v -short ./...
```

### Integration Tests

```yaml
- name: Integration tests
  run: |
    docker-compose -f docker-compose.test.yaml up -d
    go test -v -tags=integration ./...
    docker-compose -f docker-compose.test.yaml down
```

### Contract Tests

```yaml
- name: Contract tests
  run: |
    ./scripts/run-contract-tests.sh
```

## Build Caching

### Go Module Cache

```yaml
- uses: actions/cache@v3
  with:
    path: |
      ~/.cache/go-build
      ~/go/pkg/mod
    key: ${{ runner.os }}-go-${{ hashFiles('**/go.sum') }}
```

### Docker Layer Cache

```yaml
- uses: docker/build-push-action@v5
  with:
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

## Security Scanning

### Trivy (Container)

```yaml
- uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ env.IMAGE }}
    severity: 'CRITICAL,HIGH'
    exit-code: '1'
```

### CodeQL (Code)

```yaml
- uses: github/codeql-action/analyze@v2
  with:
    languages: go
```

### Dependency Scan

```yaml
- uses: snyk/actions/golang@master
  with:
    args: --severity-threshold=high
```

## Notifications

### Slack Notification

```yaml
- uses: slackapi/slack-github-action@v1
  with:
    channel-id: 'deploys'
    slack-message: |
      Deployment: ${{ job.status }}
      Service: ${{ matrix.service }}
      Environment: ${{ inputs.environment }}
  env:
    SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
```

## Monitoring Builds

### GitHub Actions Dashboard

- View workflow runs
- Check job status
- Download artifacts
- Re-run failed jobs

### Build Metrics

- Build duration
- Success rate
- Test coverage
- Security findings

## Next Steps

- [Testing](./testing) - Contract-driven development
- [Operations](./operations) - Monitoring & scripts
- [Deployment](./deployment) - ArgoCD setup
