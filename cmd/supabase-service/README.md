# Supabase gRPC Service

**统一的 Supabase 数据库与向量搜索服务**

提供 PostgreSQL 数据库操作和 pgvector 向量搜索的 gRPC 接口，支持多租户隔离和认证。

---

## 📋 目录

- [功能特性](#功能特性)
- [架构说明](#架构说明)
- [快速开始](#快速开始)
- [Supabase 配置](#supabase-配置)
- [数据库操作](#数据库操作)
- [向量搜索](#向量搜索)
- [Python 客户端](#python-客户端)
- [部署指南](#部署指南)
- [故障排查](#故障排查)

---

## 功能特性

### ✅ 数据库操作
- **CRUD 操作**: Query, Insert, Update, Delete, Upsert
- **RPC 调用**: 执行 PostgreSQL 函数和存储过程
- **批量操作**: 批量插入，提高性能
- **事务支持**: 通过 PostgreSQL 函数实现事务

### 🔍 向量搜索 (pgvector)
- **向量存储**: 存储和管理高维向量 (支持 OpenAI embeddings)
- **相似度搜索**: Cosine, L2, Inner Product 距离度量
- **混合搜索**: 文本全文搜索 + 向量语义搜索
- **元数据过滤**: 基于元数据的条件过滤

### 🔒 安全特性
- **多租户隔离**: 自动按用户/组织隔离数据
- **JWT 认证**: 支持 JWT token 验证
- **权限控制**: 细粒度权限管理
- **Row Level Security**: 利用 Supabase RLS

### 🚀 性能优化
- **连接池**: PostgreSQL 连接池管理
- **批量操作**: 减少网络往返
- **流式响应**: 大数据集流式传输 (TODO)
- **缓存支持**: 查询结果缓存 (TODO)

---

## 架构说明

```
Python 服务 → Supabase gRPC Service → Supabase (Local/Cloud)
                     ↓
              PostgreSQL + pgvector
```

### 关键设计

1. **不使用 Docker 容器**
   - 本地开发: Supabase Local (通过 CLI 管理)
   - 生产环境: Supabase Cloud

2. **双模式支持**
   - **开发模式**: 连接到 `localhost:54321` (Supabase Local)
   - **生产模式**: 连接到 Supabase Cloud URL

3. **四层架构**
   - Proto 层: `api/proto/supabase_service.proto`
   - SDK 层: `pkg/infrastructure/database/supabase/client.go`
   - Service 层: `cmd/supabase-service/server/server.go`
   - Config 层: `configs/sdk/supabase.yaml`

---

## 快速开始

### 前置要求

- Go 1.23+
- [Supabase CLI](https://supabase.com/docs/guides/cli) (本地开发)
- Docker & Docker Compose (容器部署)
- protoc (生成 gRPC 代码)

### 1. 安装 Supabase CLI

```bash
# macOS
brew install supabase/tap/supabase

# 其他平台
# 参考: https://supabase.com/docs/guides/cli/getting-started
```

### 2. 启动 Supabase Local

⚠️ **重要**: Supabase 不在 Docker 中运行，需要单独启动

```bash
# 如果还没有初始化，先初始化 (只需一次)
cd /Users/xenodennis/Documents/Fun/isA_Cloud
supabase init  # 会创建 supabase/ 目录

# 启动 Supabase Local
supabase start

# 查看状态和凭证
supabase status
```

**输出示例**:
```
API URL: http://localhost:54321
DB URL: postgresql://postgres:postgres@localhost:54322/postgres
Studio URL: http://localhost:54323
anon key: eyJhbGc...
service_role key: eyJhbGc...
```

**重要端口**:
- `54321`: Supabase API (PostgREST)
- `54322`: PostgreSQL 直连
- `54323`: Supabase Studio (管理界面)

### 3. 启用 pgvector 扩展

```bash
# 进入 Supabase SQL 编辑器
supabase db reset  # 重置数据库

# 或者手动执行 SQL
psql postgresql://postgres:postgres@localhost:54322/postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 4. 创建向量表

在 Supabase Studio (`http://localhost:54323`) 或通过 SQL 创建:

```sql
-- 创建向量表 (1536 维，OpenAI ada-002)
CREATE TABLE embeddings (
    id TEXT PRIMARY KEY,
    embedding vector(1536),
    metadata JSONB,
    user_id TEXT NOT NULL,  -- 多租户隔离
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 创建索引 (HNSW，加速向量搜索)
CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops);

-- 创建搜索函数
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.5,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id text,
    similarity float,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        embeddings.id,
        1 - (embeddings.embedding <=> query_embedding) AS similarity,
        embeddings.metadata
    FROM embeddings
    WHERE 1 - (embeddings.embedding <=> query_embedding) > match_threshold
    ORDER BY embeddings.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

### 5. 配置环境变量

创建 `.env` 文件:

```bash
# 本地开发 (Supabase Local)
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=eyJhbGc...  # 从 supabase status 获取
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...  # 从 supabase status 获取

# PostgreSQL 直连 (可选)
SUPABASE_POSTGRES_HOST=localhost
SUPABASE_POSTGRES_PORT=54322
SUPABASE_POSTGRES_DB=postgres
SUPABASE_POSTGRES_USER=postgres
SUPABASE_POSTGRES_PASSWORD=postgres
SUPABASE_POSTGRES_SSL_MODE=disable

# 向量配置
SUPABASE_VECTOR_ENABLED=true
SUPABASE_VECTOR_TABLE=embeddings
SUPABASE_VECTOR_DIMENSIONS=1536

# gRPC 配置
GRPC_PORT=50057
CONSUL_ENABLED=false  # 本地开发禁用 Consul
```

### 6. 启动 gRPC 服务

#### 方式 1: 本地运行

```bash
# 生成 gRPC 代码
protoc --proto_path=api/proto \
    --go_out=. --go_opt=module=github.com/isa-cloud/isa_cloud \
    --go-grpc_out=. --go-grpc_opt=module=github.com/isa-cloud/isa_cloud \
    api/proto/common.proto \
    api/proto/supabase_service.proto

# 构建服务
go build -o bin/supabase-service cmd/supabase-service/main.go

# 运行服务
./bin/supabase-service
```

#### 方式 2: Docker 运行

```bash
# 构建镜像
docker build -f deployments/dockerfiles/Dockerfile.supabase-service -t isa-supabase-service .

# 运行容器 (连接到宿主机的 Supabase Local)
docker run -p 50057:50057 \
  -e SUPABASE_URL=http://host.docker.internal:54321 \
  -e SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY \
  isa-supabase-service
```

#### 方式 3: Docker Compose

```bash
# 确保 Supabase Local 已启动
supabase status

# 启动 gRPC 服务
docker-compose -f deployments/compose/grpc-services.yml up supabase-grpc-service
```

### 7. 测试服务

```bash
# 使用 grpcurl 测试
grpcurl -plaintext -d '{
  "metadata": {"user_id": "test_user"}
}' localhost:50057 isa.supabase.SupabaseService/HealthCheck
```

**预期输出**:
```json
{
  "metadata": {
    "success": true,
    "timestamp": "2024-01-01T12:00:00Z"
  },
  "healthy": true,
  "supabaseStatus": "healthy",
  "postgresVersion": "PostgreSQL 15.1...",
  "pgvectorEnabled": true
}
```

---

## Supabase 配置

### 本地开发 vs 生产环境

| 环境 | Supabase 类型 | URL | 管理方式 |
|------|--------------|-----|----------|
| **开发** | Supabase Local | `http://localhost:54321` | Supabase CLI |
| **Staging** | Supabase Cloud | `https://xxx.supabase.co` | Supabase Dashboard |
| **生产** | Supabase Cloud | `https://yyy.supabase.co` | Supabase Dashboard |

### 环境变量配置

```bash
# 开发环境 (.env.local)
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<local_anon_key>
SUPABASE_SERVICE_ROLE_KEY=<local_service_role_key>

# 生产环境 (.env.production)
SUPABASE_URL=https://ugloxikfljpuvakwiadf.supabase.co
SUPABASE_ANON_KEY=<cloud_anon_key>
SUPABASE_SERVICE_ROLE_KEY=<cloud_service_role_key>
```

### 迁移 Supabase Local 数据到项目

如果你已经有现有的 Supabase Local 配置 (在 `/Users/xenodennis/Documents/Fun/isA_MCP/resources/dbs/supabase/dev/supabase`):

```bash
# 方式 1: 复制配置
cp -r /Users/xenodennis/Documents/Fun/isA_MCP/resources/dbs/supabase/dev/supabase /Users/xenodennis/Documents/Fun/isA_Cloud/supabase

# 方式 2: 链接到项目 (推荐，共享配置)
cd /Users/xenodennis/Documents/Fun/isA_Cloud
ln -s /Users/xenodennis/Documents/Fun/isA_MCP/resources/dbs/supabase/dev/supabase supabase

# 重启 Supabase
cd /Users/xenodennis/Documents/Fun/isA_Cloud
supabase start
```

---

## 数据库操作

### Query 查询

```python
from supabase_client import SupabaseGRPCClient

client = SupabaseGRPCClient(user_id='user_123')

# 查询数据
results = client.query(
    table='users',
    select='id,name,email',
    filter='age.gte.18',
    limit=10
)
```

### Insert 插入

```python
# 插入单条
client.insert('users', [
    {'name': 'Alice', 'email': 'alice@example.com', 'age': 25}
])

# 批量插入
users = [
    {'name': 'Bob', 'email': 'bob@example.com'},
    {'name': 'Charlie', 'email': 'charlie@example.com'},
]
client.insert('users', users)
```

### Update 更新

```python
client.update(
    table='users',
    data={'age': 26},
    filter='email.eq.alice@example.com'
)
```

### Delete 删除

```python
client.delete(
    table='users',
    filter='age.lt.18'
)
```

---

## 向量搜索

### 插入向量

```python
# 使用 OpenAI 生成向量
import openai

def get_embedding(text):
    response = openai.Embedding.create(
        input=text,
        model="text-embedding-ada-002"
    )
    return response['data'][0]['embedding']

# 插入文档向量
embedding = get_embedding("How to use Supabase with Python")

client.upsert_embedding(
    table='embeddings',
    doc_id='doc_001',
    embedding=embedding,
    metadata={
        'title': 'Supabase Python Guide',
        'content': 'Full content here...',
        'category': 'tutorial',
        'tags': ['python', 'database', 'supabase']
    }
)
```

### 相似度搜索

```python
# 搜索相似文档
query_embedding = get_embedding("python database tutorial")

results = client.similarity_search(
    table='embeddings',
    query_embedding=query_embedding,
    limit=5,
    filter='category.eq.tutorial',  # 只搜索 tutorial 分类
    threshold=0.7  # 相似度阈值
)

for result in results:
    print(f"文档: {result['metadata']['title']}")
    print(f"相似度: {result['similarity']:.2f}")
```

### 混合搜索

```python
# 结合文本搜索和向量搜索
results = client.hybrid_search(
    table='embeddings',
    text_query='supabase tutorial',  # 全文搜索
    vector_query=query_embedding,     # 向量搜索
    limit=10,
    text_weight=0.3,    # 文本权重
    vector_weight=0.7   # 向量权重
)
```

### 批量插入向量

```python
# 批量处理文档
documents = [
    {'title': 'Doc 1', 'content': 'Content 1'},
    {'title': 'Doc 2', 'content': 'Content 2'},
    # ... 更多文档
]

embeddings_data = []
for i, doc in enumerate(documents):
    embedding = get_embedding(doc['content'])
    embeddings_data.append({
        'id': f'doc_{i:03d}',
        'embedding': embedding,
        'metadata': doc
    })

# 批量插入
client.batch_upsert_embeddings('embeddings', embeddings_data)
```

---

## Python 客户端

### 安装依赖

```bash
pip install grpcio grpcio-tools protobuf
```

### 生成 Python gRPC 代码

```bash
python -m grpc_tools.protoc \
    -I api/proto \
    --python_out=. \
    --grpc_python_out=. \
    api/proto/common.proto \
    api/proto/supabase_service.proto
```

### 使用示例

```python
# 参考 examples/supabase_client_example.py
from supabase_client import SupabaseGRPCClient

# 创建客户端
client = SupabaseGRPCClient(
    host='localhost',
    port=50057,
    user_id='your_user_id'
)

# 使用客户端
results = client.query('users', select='*')
print(results)
```

完整示例: [`examples/supabase_client_example.py`](./examples/supabase_client_example.py)

---

## 部署指南

### Docker 部署

```bash
# 1. 设置环境变量
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# 2. 启动服务
docker-compose -f deployments/compose/grpc-services.yml up -d supabase-grpc-service

# 3. 检查日志
docker logs -f isa-supabase-grpc
```

### 生产环境配置

**重要**: 生产环境使用 Supabase Cloud

```yaml
# .env.production
SUPABASE_URL=https://ugloxikfljpuvakwiadf.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
SUPABASE_POSTGRES_HOST=db.ugloxikfljpuvakwiadf.supabase.co
SUPABASE_POSTGRES_PORT=5432
SUPABASE_POSTGRES_SSL_MODE=require
CONSUL_ENABLED=true
CONSUL_HOST=consul.production.local
```

### Kubernetes 部署 (TODO)

---

## 故障排查

### 1. Supabase Local 无法连接

**检查**:
```bash
# 确认 Supabase Local 正在运行
supabase status

# 如果没有运行，启动它
supabase start

# 测试连接
curl http://localhost:54321
```

### 2. pgvector 未启用

**解决方法**:
```sql
-- 连接到数据库
psql postgresql://postgres:postgres@localhost:54322/postgres

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 验证
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### 3. Docker 容器无法访问 Supabase Local

**问题**: Docker 容器内部无法访问 `localhost:54321`

**解决方法**:
```yaml
# docker-compose.yml
services:
  supabase-grpc-service:
    environment:
      - SUPABASE_URL=http://host.docker.internal:54321
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### 4. 认证失败

**检查**:
```bash
# 验证 JWT token
echo $SUPABASE_SERVICE_ROLE_KEY | base64 -d

# 检查元数据
# RequestMetadata 必须包含 user_id 或 access_token
```

### 5. 向量搜索返回空结果

**检查**:
1. 确认 pgvector 已启用
2. 确认向量维度匹配 (1536)
3. 确认 `match_documents` 函数已创建
4. 检查相似度阈值 (threshold)
5. 检查多租户过滤 (user_id)

---

## 相关文档

- [Proto 定义](../../api/proto/supabase_service.proto)
- [SDK 客户端](../../pkg/infrastructure/database/supabase/client.go)
- [配置文件](../../configs/sdk/supabase.yaml)
- [总体架构](../../docs/infra_grpc_service.md)
- [Supabase 官方文档](https://supabase.com/docs)
- [pgvector 文档](https://github.com/pgvector/pgvector)

---

## 常见问题 FAQ

**Q: 为什么不把 Supabase 放在 Docker 里？**

A: Supabase 是一个完整的平台，包含多个服务 (PostgreSQL, PostgREST, GoTrue, Realtime 等)。使用官方的 Supabase CLI 管理更简单，且可以无缝切换到 Supabase Cloud。

**Q: 本地开发和生产环境如何切换？**

A: 通过环境变量切换。本地使用 `http://localhost:54321`，生产使用 Supabase Cloud URL。

**Q: 如何迁移现有数据库到 Supabase？**

A: 使用 Supabase 的迁移工具或手动导入 SQL。参考: [Supabase 迁移指南](https://supabase.com/docs/guides/database/migrating-to-supabase)

**Q: 支持哪些向量维度？**

A: pgvector 支持任意维度，常用的有:
- OpenAI ada-002: 1536
- OpenAI text-embedding-3-small: 1536
- OpenAI text-embedding-3-large: 3072
- Cohere: 1024

**Q: 如何优化向量搜索性能？**

A:
1. 创建 HNSW 索引
2. 使用适当的 `m` 和 `ef_construction` 参数
3. 限制搜索结果数量
4. 使用元数据过滤减小搜索范围

---

**就这么简单！Supabase + pgvector + gRPC = 强大的向量数据库服务** 🚀

