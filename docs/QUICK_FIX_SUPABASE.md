# Supabase Docker 快速修复指南

## 问题

使用 `docker-compose` 启动 Supabase 失败，但 `supabase local` 可以工作。

## 原因

❌ 错误配置在连接字符串中设置了 `search_path=test`  
✅ 应该使用默认 search_path，让 GoTrue 访问 `auth` schema

## 修复（3处改动）

**文件**: `deployments/compose/data-stores.yml`

### 1. GoTrue Auth (第201行)

```yaml
# 修复前
GOTRUE_DB_DATABASE_URL: postgres://...@postgres:5432/postgres?search_path=test

# 修复后  
GOTRUE_DB_DATABASE_URL: postgres://...@postgres:5432/postgres
```

### 2. PostgREST (第236-240行)

```yaml
# 修复前
PGRST_DB_URI: postgres://...@postgres:5432/postgres?search_path=test
PGRST_DB_SCHEMAS: test,storage,graphql_public

# 修复后
PGRST_DB_URI: postgres://...@postgres:5432/postgres
PGRST_DB_SCHEMAS: public,graphql_public,dev,test
PGRST_DB_EXTRA_SEARCH_PATH: public,extensions,dev,test
```

### 3. Realtime (第264行)

```yaml
# 修复前
DB_AFTER_CONNECT_QUERY: 'SET search_path TO test,_realtime'

# 修复后
DB_AFTER_CONNECT_QUERY: 'SET search_path TO _realtime,public,dev,test'
```

## 测试

```bash
# 自动测试
cd deployments/scripts
chmod +x test-supabase-fix.sh
./test-supabase-fix.sh

# 或手动测试
cd deployments
docker-compose -f compose/base.yml -f compose/data-stores.yml down
docker-compose -f compose/base.yml -f compose/data-stores.yml up -d postgres
sleep 10
docker-compose -f compose/base.yml -f compose/data-stores.yml up -d supabase-auth
docker logs -f isa-supabase-auth  # 应该看到 "GoTrue API started" ✅
```

## 完整文档

详细说明: [docs/SUPABASE_DOCKER_FIX.md](./SUPABASE_DOCKER_FIX.md)  
问题追踪: [docs/issues/issue2.md](./issues/issue2.md)

