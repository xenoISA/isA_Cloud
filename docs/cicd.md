 正确的架构理解

```
isA_Cloud (GitOps 中心仓库)
├── cmd/                         # ✅ Go 微服务源码 (auth, account...)
│   ├── auth-service/
│   ├── account-service/
│   └── ...                      # 46 个 Go 微服务
│
├── deployments/kubernetes/
│   └── base/
│       ├── infrastructure/      # ✅ Consul, Redis, APISIX
│       ├── grpc-services/       # ✅ gRPC 包装服务
│       └── applications/        # ✅ 外部服务的 K8s 配置
│           ├── agent-deployment.yaml    # → isA_Agent 仓库
│           ├── mcp-deployment.yaml      # → isA_MCP 仓库
│           ├── model-deployment.yaml    # → isA_Model 仓库
│           └── user-deployment.yaml     # → isA_user 仓库
```

---

## 🔄 完整的多仓库 CI/CD 流程

```
┌─────────────────────────────────────────────────────────────────┐
│  场景：开发者在 isA_Agent 仓库修改代码                          │
└─────────────────────────────────────────────────────────────────┘

1️⃣  isA_Agent 仓库 (代码仓库)
    ├── agent/              # Python 源码
    ├── Dockerfile
    └── .github/workflows/ci.yaml

    开发者操作：
    $ git commit -m "Add new feature"
    $ git push

    触发 CI Pipeline:
    ├─ Lint & Test
    ├─ Build Docker Image
    ├─ Push to ECR: agent:sha-abc123
    └─ 🔔 通知 isA_Cloud 仓库

                ↓

2️⃣  isA_Cloud 仓库 (GitOps 仓库)

    接收 webhook/repository_dispatch:

    自动更新镜像标签：
    deployments/kubernetes/base/applications/agent-deployment.yaml

    FROM:
    image: isa-agent-staging:latest

    TO:
    image: 123456789.dkr.ecr.us-east-1.amazonaws.com/isa-agent:sha-abc123

    自动提交：
    $ git commit -m "Update agent image to sha-abc123"
    $ git push

                ↓

3️⃣  ArgoCD (监听 isA_Cloud 仓库)

    检测到变化 (30秒内):
    - Diff: agent image changed
    - Auto sync to EKS

    部署到 EKS:
    ├─ 创建新的 Pod
    ├─ 等待健康检查
    ├─ 替换旧 Pod
    └─ ✅ 部署完成

                ↓

4️⃣  通知
    └─ Slack: "Agent v1.2.3 deployed to staging ✅"
```

---

## 📝 具体实现配置

### 1️⃣ isA_Agent 仓库的 CI 配置

创建这个文件在 `isA_Agent/.github/workflows/ci.yaml`:

```yaml
name: CI - Build and Push Agent

on:
  push:
    branches: [main, develop]
    paths:
      - 'agent/**'
      - 'Dockerfile'
      - '.github/workflows/ci.yaml'

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: isa-agent
  GITOPS_REPO: your-org/isA_Cloud  # 你的 isA_Cloud 仓库

jobs:
  build-and-push:
    runs-on: ubuntu-latest

    steps:
      # ═════════════════════════════════════════════
      # Step 1: Checkout 代码
      # ═════════════════════════════════════════════
      - name: Checkout code
        uses: actions/checkout@v4

      # ═════════════════════════════════════════════
      # Step 2: 设置 Python 环境
      # ═════════════════════════════════════════════
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      # ═════════════════════════════════════════════
      # Step 3: Lint 和测试
      # ═════════════════════════════════════════════
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest flake8 black

      - name: Lint with flake8
        run: flake8 agent/ --max-line-length=120

      - name: Format check with black
        run: black --check agent/

      - name: Run tests
        run: pytest tests/ -v

      # ═════════════════════════════════════════════
      # Step 4: 配置 AWS 凭证
      # ═════════════════════════════════════════════
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      # ═════════════════════════════════════════════
      # Step 5: 构建和推送 Docker 镜像
      # ═════════════════════════════════════════════
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY }}:${{ github.sha }}
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY }}:latest
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY }}:${{ github.ref_name }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      # ═════════════════════════════════════════════
      # Step 6: 镜像安全扫描
      # ═════════════════════════════════════════════
      - name: Scan image with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY }}:${{ github.sha }}
          severity: 'CRITICAL,HIGH'
          exit-code: '0'  # 不阻塞，只警告

      # ═════════════════════════════════════════════
      # Step 7: 触发 GitOps 仓库更新
      # ═════════════════════════════════════════════
      - name: Trigger GitOps update
        uses: peter-evans/repository-dispatch@v2
        with:
          token: ${{ secrets.GITOPS_PAT }}  # 需要创建 Personal Access Token
          repository: ${{ env.GITOPS_REPO }}
          event-type: update-agent-image
          client-payload: |
            {
              "image": "${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY }}:${{ github.sha }}",
              "service": "agent",
              "sha": "${{ github.sha }}",
              "ref": "${{ github.ref_name }}",
              "actor": "${{ github.actor }}"
            }
```

---

### 2️⃣ isA_Cloud 仓库的 CD 配置

创建这个文件在 `isA_Cloud/.github/workflows/cd-update-images.yaml`:

```yaml
name: CD - Update Service Images

on:
  repository_dispatch:
    types:
      - update-agent-image
      - update-mcp-image
      - update-model-image
      - update-user-image

jobs:
  update-manifest:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Update image in manifest
        run: |
          SERVICE="${{ github.event.client_payload.service }}"
          NEW_IMAGE="${{ github.event.client_payload.image }}"
          SHA="${{ github.event.client_payload.sha }}"

          # 更新 deployment.yaml 中的镜像
          MANIFEST="deployments/kubernetes/base/applications/${SERVICE}-deployment.yaml"

          # 使用 yq 更新镜像 (需要安装 yq)
          yq eval ".spec.template.spec.containers[0].image = \"${NEW_IMAGE}\"" -i $MANIFEST

          echo "Updated $MANIFEST with image: $NEW_IMAGE"

      - name: Commit and push
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"

          git add deployments/kubernetes/base/applications/

          git commit -m "chore: update ${{ github.event.client_payload.service }} image to ${{ github.event.client_payload.sha }}" || exit 0

          git push

      - name: Comment on source PR (if applicable)
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.GITOPS_PAT }}
          script: |
            const service = '${{ github.event.client_payload.service }}';
            const sha = '${{ github.event.client_payload.sha }}';
            console.log(`Image updated for ${service}: ${sha}`);
            // 可以添加更多通知逻辑
```

---

### 3️⃣ isA_Cloud 自己的 CI 配置

对于 isA_Cloud 仓库中的 Go 微服务：

```yaml
# .github/workflows/ci-golang.yaml
name: CI - Build Go Microservices

on:
  push:
    branches: [main, develop]
    paths:
      - 'cmd/**'
      - 'internal/**'
      - 'go.mod'
      - 'go.sum'

env:
  AWS_REGION: us-east-1
  ECR_REGISTRY: 123456789.dkr.ecr.us-east-1.amazonaws.com

jobs:
  # 检测哪些服务被修改了
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      services: ${{ steps.filter.outputs.changes }}
    steps:
      - uses: actions/checkout@v4

      - uses: dorny/paths-filter@v2
        id: filter
        with:
          filters: |
            auth:
              - 'cmd/auth-service/**'
            account:
              - 'cmd/account-service/**'
            session:
              - 'cmd/session-service/**'
            # ... 添加所有 46 个服务

  # 只构建被修改的服务
  build-services:
    needs: detect-changes
    if: ${{ needs.detect-changes.outputs.services != '[]' }}
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: ${{ fromJSON(needs.detect-changes.outputs.services) }}

    steps:
      - uses: actions/checkout@v4

      - name: Setup Go
        uses: actions/setup-go@v4
        with:
          go-version: '1.23'

      - name: Test
        run: |
          go test ./cmd/${{ matrix.service }}/... -v

      - name: Build
        run: |
          CGO_ENABLED=0 GOOS=linux go build \
            -o bin/${{ matrix.service }} \
            ./cmd/${{ matrix.service }}/main.go

      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./deployments/dockerfiles/Dockerfile.${{ matrix.service }}
          push: true
          tags: |
            ${{ env.ECR_REGISTRY }}/isa-cloud/${{ matrix.service }}:${{ github.sha }}
            ${{ env.ECR_REGISTRY }}/isa-cloud/${{ matrix.service }}:latest

      # Go 服务的镜像直接在同一个仓库，不需要触发，ArgoCD 会自动检测
```

---

## 📊 完整流程总结

| 仓库 | 职责 | CI/CD |
|------|------|-------|
| **isA_Cloud** | ✅ Go 微服务源码<br>✅ K8s 配置 (GitOps)<br>✅ 基础设施配置 | CI: 构建 Go 服务<br>CD: 接收其他仓库的镜像更新 |
| **isA_Agent** | ✅ Agent 源码 (Python) | CI: 构建镜像 → 通知 isA_Cloud |
| **isA_MCP** | ✅ MCP 源码 (Python) | CI: 构建镜像 → 通知 isA_Cloud |
| **isA_Model** | ✅ Model 源码 (Python) | CI: 构建镜像 → 通知 isA_Cloud |
| **isA_user** | ✅ User 源码 (Python) | CI: 构建镜像 → 通知 isA_Cloud |

---

## 🚀 部署流程

```
1. 开发者在任意仓库 push 代码
   ↓
2. 该仓库的 CI 构建镜像
   ↓
3. 推送到 ECR
   ↓
4. 触发 isA_Cloud 仓库更新对应的 deployment.yaml
   ↓
5. isA_Cloud 自动 commit & push
   ↓
6. ArgoCD 检测到 isA_Cloud 变化
   ↓
7. 自动部署到 EKS ✅
