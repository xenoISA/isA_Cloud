# isA Cloud 测试
# isA Cloud Tests

## 概述

这个目录包含 isA Cloud 平台的所有测试代码，包括单元测试、集成测试和端到端测试。

## 测试类型

### 1. 单元测试 (`unit/`)

测试单个函数或方法的功能。

```bash
# 运行所有单元测试
./scripts/test-unit.sh

# 或使用 go test
go test ./tests/unit/...
```

### 2. 集成测试 (`integration/`)

测试多个组件之间的集成。

```bash
# 运行所有集成测试
./scripts/test-integration.sh

# 或使用 go test
go test ./tests/integration/...
```

### 3. 端到端测试 (`e2e/`)

测试完整的用户场景。

```bash
# 运行端到端测试
./scripts/test-e2e.sh
```

## 当前测试文件

### 集成测试

| 文件 | 说明 |
|------|------|
| `integration/config_test.go` | 配置加载和验证测试 |
| `integration/infrastructure_integration_test.go` | 基础设施服务集成测试 |

## 测试规范

### 命名规范

```
单元测试：    <package>_test.go
集成测试：    <feature>_integration_test.go
端到端测试：  <scenario>_e2e_test.go
```

### 文件组织

```
tests/
├── unit/                              # 单元测试
│   ├── loki_test.go
│   ├── mqtt_test.go
│   └── ...
│
├── integration/                       # 集成测试
│   ├── config_test.go
│   ├── infrastructure_integration_test.go
│   └── ...
│
└── e2e/                              # 端到端测试
    └── ...
```

## 运行测试

### 快速运行

```bash
# 所有测试
make test

# 单元测试
make test-unit

# 集成测试
make test-integration

# 端到端测试
make test-e2e
```

### 使用脚本

```bash
# 所有测试
./scripts/test-all.sh

# 单元测试
./scripts/test-unit.sh

# 集成测试（需要启动服务）
./scripts/test-integration.sh

# SDK 测试
./scripts/test-sdk.sh
```

### 使用 go test

```bash
# 运行所有测试
go test ./...

# 运行特定目录
go test ./tests/unit/...
go test ./tests/integration/...

# 详细输出
go test -v ./tests/unit/...

# 代码覆盖率
go test -cover ./...
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out
```

## 测试前置条件

### 集成测试

集成测试需要启动相关服务：

```bash
# 使用 docker-compose 启动服务
cd deployments/envs/staging
docker-compose up -d

# 或单独启动服务
docker run -d --name loki -p 3100:3100 grafana/loki:latest
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:latest
docker run -d --name minio -p 9000:9000 minio/minio server /data
```

### 环境变量

某些测试需要环境变量：

```bash
export ISA_CLOUD_LOKI_URL="http://localhost:3100"
export ISA_CLOUD_MQTT_BROKER_URL="tcp://localhost:1883"
export ISA_CLOUD_MINIO_ENDPOINT="localhost:9000"
```

## 编写测试

### 单元测试示例

```go
// tests/unit/loki_test.go
package unit

import (
    "testing"
    "github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
)

func TestLokiClient(t *testing.T) {
    cfg := &loki.Config{
        URL: "http://localhost:3100",
    }
    
    client, err := loki.NewClient(cfg)
    if err != nil {
        t.Fatalf("Failed to create client: %v", err)
    }
    defer client.Close()
    
    // 测试功能...
}
```

### 集成测试示例

```go
// tests/integration/loki_integration_test.go
package integration

import (
    "context"
    "testing"
    "time"
)

func TestLokiIntegration(t *testing.T) {
    // 跳过测试如果服务未运行
    if testing.Short() {
        t.Skip("Skipping integration test")
    }
    
    // 测试与实际 Loki 服务的集成...
}
```

## 测试覆盖率

```bash
# 生成覆盖率报告
go test -coverprofile=coverage.out ./...

# 查看覆盖率
go tool cover -func=coverage.out

# 生成 HTML 报告
go tool cover -html=coverage.out -o coverage.html
```

## 持续集成

测试在 CI/CD 管道中自动运行：

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: |
          make test-unit
          make test-integration
```

## 相关资源

- [示例代码](../examples/)
- [SDK 文档](../pkg/infrastructure/)
- [配置文件](../configs/sdk/)

## 贡献

编写测试时请遵循：
1. 使用表驱动测试（table-driven tests）
2. 测试边界条件和错误情况
3. 使用有意义的测试名称
4. 添加必要的注释
5. 保持测试独立和可重复



