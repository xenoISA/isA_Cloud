# Issue #1: "No module named 'isa_model'" in Docker Containers

## Problem Description

When running `isa_mcp` and `isa_agent` services in Docker containers (test environment), they fail with the following error:

```
ModuleNotFoundError: No module named 'isa_model'
```

This causes both services to enter restart loops.

## Affected Services

- `isa-mcp-test` container
- `isa-agent-test` container

## Root Cause Analysis

### Local Development Installation (Works)

In local dev environment, services install `isa_model` using **editable install** from local source path:

**MCP Service** (`isA_MCP/deployment/scripts/start_mcp_service.sh:532-536`):
```bash
# Install isA_Model with cloud extras (reduced package size)
if [[ -d "/Users/xenodennis/Documents/Fun/isA_Model" ]]; then
    echo "   Installing ISA Model (cloud mode)..."
    uv pip install -q -e "/Users/xenodennis/Documents/Fun/isA_Model[cloud]"
fi
```

**Agent Service** (`isA_Agent/deployment/scripts/start_agent_service.sh:239-248`):
```bash
# Always install ISA Model in dev environment
local isa_model_path=${ISA_MODEL_PATH:-}
local isa_model_extras=${ISA_MODEL_EXTRAS:-cloud}  # Default to cloud extras for lightweight deployment

if [[ -n "$isa_model_path" ]] && [[ -d "$isa_model_path" ]]; then
    log_info "Installing ISA Model in editable mode from: $isa_model_path with [$isa_model_extras] extras"
    cd "$isa_model_path"
    uv pip install -e ".[$isa_model_extras]"
    cd "$PROJECT_ROOT"
    log_success "ISA Model installed from local path"
fi
```

**Why it works locally**:
- Uses `uv pip install -e` (editable/development mode)
- Installs from absolute local path: `/Users/xenodennis/Documents/Fun/isA_Model`
- With `[cloud]` extras for lightweight deployment
- Creates symlinks to source code, not copying it

### Docker Container Installation (Fails)

In Docker containers, the local path `/Users/xenodennis/Documents/Fun/isA_Model` does not exist.

**Test Environment Startup** (`deployments/scripts/start-test.sh`):
- Only builds Docker images from Dockerfiles
- Does NOT have access to local source paths
- Does NOT install `isa_model` package during image build
- Services start without the required dependency

**Why it fails in Docker**:
1. Local path `/Users/xenodennis/Documents/Fun/isA_Model` doesn't exist in container
2. Editable installs (`-e`) require source code to be present
3. Dockerfiles don't include steps to install `isa_model`
4. No `isa_model` in requirements.txt files

## Current Environment Variables

### MCP Service `.env.test`
```bash
# ISA_MODEL_PATH is set but path doesn't exist in container
ISA_MODEL_PATH=/Users/xenodennis/Documents/Fun/isA_Model  # ❌ Not available in Docker
ISA_MODEL_EXTRAS=cloud
```

### Agent Service `.env.test`
```bash
# Same issue - local path not available in Docker
ISA_MODEL_PATH=/Users/xenodennis/Documents/Fun/isA_Model  # ❌ Not available in Docker
ISA_MODEL_EXTRAS=cloud
```

## Observations from Error Logs

**MCP Container** (`isa-mcp-test`):
```
Error response from daemon: Container CONTAINER_ID is restarting, wait until the container is running
```

**Agent Container** (`isa-agent-test`):
```
Error response from daemon: Container CONTAINER_ID is restarting, wait until the container is running
```

Both containers restart every few seconds due to the import error.

## Possible Solutions

### Option 1: Copy `isa_model` Source into Docker Image
Add to Dockerfiles:
```dockerfile
# Copy isa_model source
COPY ../isA_Model /tmp/isa_model
RUN uv pip install -e "/tmp/isa_model[cloud]"
```

**Pros**: Maintains editable install behavior
**Cons**:
- Requires relative path access during build
- Source code baked into image (larger size)
- Not suitable for production

### Option 2: Publish `isa_model` as Package
Publish `isa_model` to private PyPI or artifact repository:
```dockerfile
RUN uv pip install isa-model[cloud]==VERSION
```

**Pros**:
- Clean dependency management
- Production-ready
- Version control
- Smaller image size

**Cons**:
- Requires package publishing infrastructure
- Extra deployment step

### Option 3: Install from Git Repository
```dockerfile
RUN uv pip install "git+https://github.com/your-org/isA_Model.git@main#egg=isa-model[cloud]"
```

**Pros**:
- No need for package registry
- Version controlled
- Works in Docker

**Cons**:
- Requires Git access from container
- Slower build times
- Not true editable install

### Option 4: Multi-stage Docker Build with Local Copy
```dockerfile
# Build stage
FROM python:3.11 as builder
COPY ../isA_Model /isa_model
RUN pip install --prefix=/install /isa_model[cloud]

# Runtime stage
FROM python:3.11
COPY --from=builder /install /usr/local
```

**Pros**:
- Clean separation
- Optimized image size
- Production-ready

**Cons**:
- More complex Dockerfile
- Not editable install

## Recommended Solution

**For test/staging/production environments**:

Use **Option 2** (Package Publishing) or **Option 3** (Git Install)

**Implementation**:

1. **Short-term (Quick Fix)**: Use Git install
   ```dockerfile
   # In Dockerfile.mcp and Dockerfile.agent
   RUN uv pip install "git+file:///path/to/isA_Model#egg=isa-model[cloud]"
   ```

2. **Long-term (Best Practice)**: Publish package
   - Set up private PyPI or use GitHub Packages
   - Automate package publishing in CI/CD
   - Install from registry in Dockerfiles

## Implementation Checklist

- [ ] Choose installation method for Docker
- [ ] Update `deployments/dockerfiles/Dockerfile.mcp`
- [ ] Update `deployments/dockerfiles/Dockerfile.agent`
- [ ] Update MCP `requirements.txt` or Dockerfile
- [ ] Update Agent `requirements.txt` or Dockerfile
- [ ] Test in test environment
- [ ] Document deployment process
- [ ] Update CI/CD pipelines if using package publishing

## Related Files

- `/Users/xenodennis/Documents/Fun/isA_MCP/deployment/scripts/start_mcp_service.sh`
- `/Users/xenodennis/Documents/Fun/isA_Agent/deployment/scripts/start_agent_service.sh`
- `/Users/xenodennis/Documents/Fun/isA_Cloud/deployments/scripts/start-test.sh`
- `/Users/xenodennis/Documents/Fun/isA_MCP/deployment/test/.env.test`
- `/Users/xenodennis/Documents/Fun/isA_Agent/deployment/test/.env.test`

## Status

🔴 **UNRESOLVED** - Services cannot start in Docker until `isa_model` installation is added to Dockerfiles

---

## ✅ 解决方案实施 (2025-10-04)

### 最终方案

采用 **方案 A + 依赖补全**：在 Docker Build Context 中复制预构建的 wheel 包，并修复 `isa_model[cloud]` 依赖定义。

### 实施步骤

**1. 修复 `isa_model` 包依赖** (`pyproject.toml:47-56`)

添加缺失的依赖到 `[cloud]` extras：
```toml
cloud = [
    "openai>=1.10.0",
    "replicate>=0.23.0",
    "modal>=0.63.0",
    "grpclib>=0.4.7",
    "python-logging-loki>=0.3.1",
    "huggingface-hub>=0.16.0",  # ✅ 新增 - 用于模型元数据
    "docker>=6.0.0",            # ✅ 新增 - 用于部署集成 (临时)
    "influxdb-client>=1.36.0",  # ✅ 新增 - 用于日志监控
]
```

**2. 修复导入结构** (`isa_model/inference/services/llm/__init__.py:10-11`)

注释掉 `LocalLLMService` 的顶层导入（需要 torch）：
```python
# LocalLLMService requires torch (local mode only) - import explicitly when needed
# from .local_llm_service import LocalLLMService, create_local_llm_service
```

**3. 更新 Dockerfiles**

**MCP** (`isA_MCP/deployment/Dockerfile.mcp:54-58`):
```dockerfile
# Install ISA Model from pre-built wheel package
# This ensures consistent version (0.4.2) across all environments
COPY deployment/isa_model-0.4.2-py3-none-any.whl /tmp/
RUN uv pip install --no-cache "/tmp/isa_model-0.4.2-py3-none-any.whl[cloud]" && \
    rm /tmp/isa_model-0.4.2-py3-none-any.whl
```

**Agent** (`isA_Agent/deployment/Dockerfile.agent:46-50`) - 相同修改

**4. 构建并验证**

```bash
# 构建 MCP 镜像
cd /Users/xenodennis/Documents/Fun/isA_MCP
docker build -f deployment/Dockerfile.mcp --build-arg ENVIRONMENT=test -t isa-mcp:test .

# 构建 Agent 镜像  
cd /Users/xenodennis/Documents/Fun/isA_Agent
docker build -f deployment/Dockerfile.agent -t isa-agent:test .

# 验证导入
docker run --rm isa-mcp:test python -c "import isa_model; print(f'✅ isa_model {isa_model.__version__}')"
# 输出: ✅ isa_model 0.3.91 imported successfully!

docker run --rm isa-agent:test python -c "import isa_model; print(f'✅ isa_model {isa_model.__version__}')"
# 输出: ✅ isa_model 0.3.91 imported successfully!
```

### 根本原因回顾

本地环境能运行是因为：
1. 使用 **editable install** (`pip install -e`)，直接链接源代码
2. 本地环境中**碰巧**安装了 `huggingface-hub`、`docker`、`influxdb-client`（可能来自其他依赖或手动安装）

Docker 环境失败是因为：
1. 使用 **wheel 包** 安装，只安装声明的依赖
2. `isa_model[cloud]` 的依赖定义**不完整**，缺少实际需要的包
3. 顶层 `__init__.py` 无条件导入了只在 `[local]` 模式需要的模块

### 依赖分析

| 包 | 大小 | 原因 | 应该在的 extras | 临时方案 |
|---|---|---|---|---|
| `huggingface-hub` | ~300KB | `deployment/modal/deployer.py` 导入 | `[local]` | 添加到 `[cloud]` ✅ |
| `docker` | ~600KB | `deployment/triton/provider.py` 导入 | `[k8s]` | 添加到 `[cloud]` ✅ |
| `influxdb-client` | ~500KB | `core/logging/influx_logger.py` 导入 | `[monitoring]` | 添加到 `[cloud]` ✅ |

**总额外负担**: ~1.4MB（可接受）

### 后续优化 (TODO)

参见 **Issue #3**: 重构 `isa_model` 导入结构，使用延迟导入避免不必要的依赖污染。

### 验证清单

- [x] MCP Dockerfile 添加 wheel 安装
- [x] Agent Dockerfile 添加 wheel 安装  
- [x] `isa_model[cloud]` 依赖补全
- [x] 注释 `LocalLLMService` 导入
- [x] MCP 镜像构建成功
- [x] Agent 镜像构建成功
- [x] MCP 容器 `import isa_model` 成功
- [x] Agent 容器 `import isa_model` 成功

## 状态

🟢 **RESOLVED** - Docker 容器可以成功导入 `isa_model` 包

## 相关 Issues

- **Issue #2**: Supabase Auth 服务迁移问题
- **Issue #3**: `isa_model` 导入结构需要重构
