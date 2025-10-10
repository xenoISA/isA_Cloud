# Issue #3: isa_model 包的导入结构问题 - 不必要的依赖污染

## 问题描述

`isa_model[cloud]` extras 本应是轻量级的云 API 模式依赖，但由于不合理的导入结构，被迫引入了本应只在 `[local]` 模式需要的依赖：
- `huggingface-hub` (原本在 `[local]`)
- `docker` (用于 Triton 部署)

这导致 Docker 镜像体积增大，依赖管理混乱。

## 根本原因

### 导入链分析

**问题导入链**:
```
isa_model/__init__.py
  └─> client.py
      └─> inference/ai_factory.py
          └─> inference/services/__init__.py
              └─> inference/services/llm/__init__.py:10
                  └─> LocalLLMService  ❌ 无条件导入
                      └─> deployment/local/__init__.py
                          └─> deployment/__init__.py:7
                              └─> deployment/modal/deployer.py:16
                                  └─> huggingface_hub  ❌ 强制依赖
                              └─> deployment/triton/provider.py:16
                                  └─> docker  ❌ 强制依赖
```

### 问题文件

**1. `isa_model/inference/services/llm/__init__.py`** (第 10 行)
```python
# ❌ 无条件导入 LocalLLMService
from .local_llm_service import LocalLLMService, create_local_llm_service
```

**问题**: `LocalLLMService` 只在本地模型推理时需要，cloud 模式根本不应该导入。

**2. `isa_model/deployment/__init__.py`** (第 7-8 行)
```python
# ❌ 顶层导入 deployment 子模块
from .modal.deployer import ModalDeployer
from .triton.provider import TritonProvider
```

**问题**: 这些 deployer 只在部署场景使用，不应在模块初始化时导入。

**3. `isa_model/deployment/modal/deployer.py`** (第 16 行)
```python
from huggingface_hub import HfApi, model_info
```

**4. `isa_model/deployment/triton/provider.py`** (第 16 行)
```python
import docker
```

## 影响范围

### 当前 workaround
在 `pyproject.toml` 的 `[cloud]` extras 中添加了这些依赖：
```toml
cloud = [
    ...
    "huggingface-hub>=0.16.0",  # 本应在 [local]
    "docker>=6.0.0",  # 本应在 k8s/deployment extras
]
```

### 包大小影响
- `huggingface-hub`: ~300KB
- `docker`: ~600KB
- **总额外负担**: ~900KB + 依赖链

### 正确的依赖分配应该是

| 包 | 应该在的 extras | 当前在的 extras | 实际用途 |
|---|---|---|---|
| `huggingface-hub` | `[local]` | `[cloud]` ✅ (workaround) | 本地模型下载 |
| `docker` | `[k8s]` 或单独使用 | `[cloud]` ✅ (workaround) | Triton 容器部署 |

## 建议的修复方案

### 方案 A: 延迟导入（推荐）

**修改 `isa_model/inference/services/llm/__init__.py`**:
```python
"""
LLM Services - Business logic services for Language Models
"""

# Cloud-mode services (always available)
from .ollama_llm_service import OllamaLLMService
from .openai_llm_service import OpenAILLMService
from .yyds_llm_service import YydsLLMService
from .huggingface_llm_service import ISALLMService, HuggingFaceLLMService, HuggingFaceInferenceService

# Lazy import for local-mode services (avoid loading heavy deps)
# Only import when actually used:
#   from isa_model.inference.services.llm.local_llm_service import LocalLLMService

__all__ = [
    "OllamaLLMService",
    "OpenAILLMService", 
    "YydsLLMService",
    "ISALLMService",
    "HuggingFaceLLMService", 
    "HuggingFaceInferenceService",
    # "LocalLLMService",  # Available via explicit import
]
```

**修改 `isa_model/deployment/__init__.py`**:
```python
"""
ISA Model Deployment - Multi-provider deployment system

Unified deployment architecture supporting Modal and Triton platforms.
"""

# Lazy imports - only load when explicitly used:
#   from isa_model.deployment.modal.deployer import ModalDeployer
#   from isa_model.deployment.triton.provider import TritonProvider
#   from isa_model.deployment.core.deployment_manager import DeploymentManager

__all__ = ["ModalDeployer", "TritonProvider", "DeploymentManager"]
```

### 方案 B: 条件导入

```python
# isa_model/inference/services/llm/__init__.py
import sys

# ... 其他导入 ...

# 只在 local extras 可用时导入
if "torch" in sys.modules or "transformers" in sys.modules:
    try:
        from .local_llm_service import LocalLLMService, create_local_llm_service
        __all__.extend(["LocalLLMService", "create_local_llm_service"])
    except ImportError:
        pass
```

### 方案 C: 拆分子包（长期方案）

将 `isa_model` 拆分为多个可选安装的子包：
- `isa-model-core` - 核心 API
- `isa-model-cloud` - 云服务集成
- `isa-model-local` - 本地推理
- `isa-model-deploy` - 部署工具

## 测试验证

修复后应验证：

```bash
# 1. Cloud 模式不应导入本地依赖
docker run --rm isa-mcp:test python -c "
import sys
import isa_model
print('Loaded modules:', [m for m in sys.modules if 'torch' in m or 'docker' in m])
# 应该输出: Loaded modules: ['docker'] (docker 用于部署)
# 不应该包含: torch, transformers
"

# 2. 包大小检查
pip install isa_model[cloud]
pip list --format=freeze | grep -E "docker|huggingface|torch"
# 应该只有云 API 相关依赖
```

## 实施优先级

- **P0 (高优先级)**: 修复 `deployment/__init__.py` - 避免导入 deployer 模块
- **P1 (中优先级)**: 修复 `services/llm/__init__.py` - LocalLLMService 延迟导入
- **P2 (低优先级)**: 拆分子包结构

## 临时 Workaround

当前已在 `pyproject.toml:54` 添加 TODO 注释：
```toml
"docker>=6.0.0",  # TODO: Should not be needed for cloud mode, fix import structure (see issue3.md)
```

## 相关文件

- `/Users/xenodennis/Documents/Fun/isA_Model/isa_model/inference/services/llm/__init__.py:10`
- `/Users/xenodennis/Documents/Fun/isA_Model/isa_model/deployment/__init__.py:7-8`
- `/Users/xenodennis/Documents/Fun/isA_Model/isa_model/deployment/modal/deployer.py:16`
- `/Users/xenodennis/Documents/Fun/isA_Model/isa_model/deployment/triton/provider.py:16`
- `/Users/xenodennis/Documents/Fun/isA_Model/pyproject.toml:47-55`

## 状态

🟡 **WORKAROUND IN PLACE** - 已添加依赖到 `[cloud]` extras，等待重构修复

## 相关 Issues

- Issue #1: "No module named 'isa_model'" - 引发此问题的调查
