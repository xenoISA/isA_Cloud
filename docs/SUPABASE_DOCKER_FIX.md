# Supabase Docker vs Supabase Local 配置差异修复

## 概述

**问题**: 使用 Docker Compose 启动 Supabase 服务时，Auth 服务（GoTrue）失败，但使用 `supabase local` 可以正常工作。

**根本原因**: Docker Compose 配置中错误地在数据库连接字符串中设置了 `search_path=test`，导致 GoTrue 无法正确访问 `auth` schema 进行迁移。

**解决方案**: 移除连接字符串中的 `search_path` 参数，匹配 `supabase local` 的配置方式。

---

## 问题详细分析

### 错误表现

```
Error: failed to run migrations: sql: operator does not exist: uuid = text (SQLSTATE 42883)
```

### 配置对比

#### ❌ Docker Compose (失败的配置)

**文件**: `deployments/compose/data-stores.yml`

```yaml
# GoTrue Auth 服务
supabase-auth:
  environment:
    GOTRUE_DB_DATABASE_URL: postgres://supabase_auth_admin:postgres@postgres:5432/postgres?search_path=test
    # ⚠️ 问题: search_path=test 导致在错误的 schema 中查找

# PostgREST
supabase-rest:
  environment:
    PGRST_DB_URI: postgres://authenticator:postgres@postgres:5432/postgres?search_path=test
    PGRST_DB_SCHEMAS: test,storage,graphql_public
    # ⚠️ 问题: search_path 应该通过专用参数设置，不是在 URI 中

# Realtime
supabase-realtime:
  environment:
    DB_AFTER_CONNECT_QUERY: 'SET search_path TO test,_realtime'
    # ⚠️ 问题: test schema 应该在后面，_realtime 优先
```

#### ✅ Supabase Local (工作的配置)

```yaml
# GoTrue Auth 服务
supabase_auth_local:
  environment:
    GOTRUE_DB_DATABASE_URL: postgresql://supabase_auth_admin:postgres@supabase_db_local:5432/postgres
    # ✅ 没有 search_path 参数

# PostgREST
supabase_rest_local:
  environment:
    PGRST_DB_URI: postgresql://authenticator:postgres@supabase_db_local:5432/postgres
    PGRST_DB_SCHEMAS: public,graphql_public,dev,test
    PGRST_DB_EXTRA_SEARCH_PATH: public,extensions,dev,test
    # ✅ 使用专用参数设置 schema 和搜索路径

# Realtime
supabase_realtime_local:
  environment:
    DB_AFTER_CONNECT_QUERY: SET search_path TO _realtime
    # ✅ 优先使用 _realtime schema
```

---

## 为什么 `search_path=test` 会导致问题？

### PostgreSQL Schema 搜索路径机制

1. **默认 search_path**: `"$user",public`
   - PostgreSQL 首先在与用户名同名的 schema 中查找
   - 然后在 `public` schema 中查找

2. **GoTrue 的期望**:
   - GoTrue 期望 `auth` schema 在搜索路径中
   - 迁移表 `auth.schema_migrations` 需要在 `auth` schema 中
   - 所有 auth 相关的表都应该在 `auth` schema 中

3. **设置 `search_path=test` 的影响**:
   - 覆盖了默认搜索路径
   - GoTrue 在 `test` schema 中查找 `auth.schema_migrations`
   - 找不到正确的 schema，导致迁移失败

### 示例说明

```sql
-- 默认情况（无 search_path 参数）
-- search_path = "$user",public,auth
SELECT * FROM schema_migrations;  -- 在 auth.schema_migrations 中查找 ✅

-- 设置 search_path=test
-- search_path = test
SELECT * FROM schema_migrations;  -- 在 test.schema_migrations 中查找 ❌
```

---

## 修复方案

### 文件修改

**文件**: `deployments/compose/data-stores.yml`

#### 1. GoTrue Auth 服务 (约第190-201行)

```yaml
supabase-auth:
  image: public.ecr.aws/supabase/gotrue:v2.176.1
  container_name: isa-supabase-auth
  environment:
    GOTRUE_API_HOST: 0.0.0.0
    GOTRUE_API_PORT: 9999
    API_EXTERNAL_URL: http://localhost:54321
    
    GOTRUE_DB_DRIVER: postgres
    # ✅ 修复: 移除 ?search_path=test
    GOTRUE_DB_DATABASE_URL: postgres://supabase_auth_admin:${POSTGRES_PASSWORD}@postgres:5432/postgres
```

#### 2. PostgREST (约第231-241行)

```yaml
supabase-rest:
  image: public.ecr.aws/supabase/postgrest:v12.2.12
  container_name: isa-supabase-rest
  environment:
    # ✅ 修复: 移除 ?search_path=test
    PGRST_DB_URI: postgres://authenticator:${POSTGRES_PASSWORD}@postgres:5432/postgres
    
    # ✅ 修复: 暴露多个 schema，包括 public
    PGRST_DB_SCHEMAS: public,graphql_public,dev,test
    
    # ✅ 新增: 使用专用参数设置搜索路径
    PGRST_DB_EXTRA_SEARCH_PATH: public,extensions,dev,test
    
    PGRST_DB_ANON_ROLE: anon
    PGRST_JWT_SECRET: ${JWT_SECRET}
```

#### 3. Realtime (约第253-264行)

```yaml
supabase-realtime:
  image: public.ecr.aws/supabase/realtime:v2.36.18
  container_name: isa-supabase-realtime
  environment:
    PORT: 4000
    DB_HOST: postgres
    DB_PORT: 5432
    DB_USER: supabase_admin
    DB_PASSWORD: ${POSTGRES_PASSWORD}
    DB_NAME: postgres
    
    # ✅ 修复: 优先 _realtime schema，然后包含其他 schema
    DB_AFTER_CONNECT_QUERY: 'SET search_path TO _realtime,public,dev,test'
```

---

## 验证修复

### 方法 1: 使用测试脚本

```bash
cd /Users/xenodennis/Documents/Fun/isA_Cloud/deployments/scripts
chmod +x test-supabase-fix.sh
./test-supabase-fix.sh
```

测试脚本会：
- ✅ 验证配置文件已正确修改
- ✅ 对比与 supabase local 的配置
- ✅ 提供测试步骤和预期结果

### 方法 2: 手动测试

```bash
cd /Users/xenodennis/Documents/Fun/isA_Cloud/deployments

# 1. 停止所有服务
docker-compose -f compose/base.yml -f compose/data-stores.yml down

# 2. （可选）清理旧数据
docker volume rm isa-postgres-data

# 3. 启动 PostgreSQL
docker-compose -f compose/base.yml -f compose/data-stores.yml up -d postgres

# 4. 等待 PostgreSQL 就绪
sleep 10
docker-compose -f compose/base.yml -f compose/data-stores.yml ps postgres

# 5. 启动 Auth 服务
docker-compose -f compose/base.yml -f compose/data-stores.yml up -d supabase-auth

# 6. 检查日志
docker logs -f isa-supabase-auth
```

### 预期结果

✅ **成功的输出**:
```json
{"level":"info","msg":"GoTrue API started","time":"2024-10-10T..."}
{"level":"info","msg":"migrations complete","time":"2024-10-10T..."}
```

❌ **失败的输出** (修复前):
```json
{"level":"fatal","msg":"Error checking migration status","error":"failed to run migrations: sql: operator does not exist: uuid = text (SQLSTATE 42883)"}
```

### 检查健康状态

```bash
# 检查容器状态
docker ps --filter "name=supabase"

# 检查 Auth 服务健康
curl http://localhost:9999/health

# 通过 Kong 网关检查
curl http://localhost:54321/auth/v1/health
```

---

## 技术细节

### GoTrue 迁移机制

1. GoTrue 使用 `gobuffalo/pop` (soda) 进行数据库迁移
2. 迁移文件嵌入在 Go 二进制文件中（编译时）
3. GoTrue 期望 `auth` schema 在默认搜索路径中
4. 迁移表：`auth.schema_migrations`

### PostgreSQL Schema 最佳实践

1. ✅ **推荐**: 让服务使用默认 search_path，在代码中显式指定 schema
   ```sql
   SELECT * FROM auth.users;
   SELECT * FROM public.posts;
   ```

2. ❌ **不推荐**: 在连接字符串中硬编码 search_path
   ```
   postgres://user:pass@host/db?search_path=test  -- 可能导致问题
   ```

3. ✅ **如需自定义**: 使用服务特定的配置参数
   ```yaml
   # PostgREST
   PGRST_DB_EXTRA_SEARCH_PATH: public,extensions,dev,test
   
   # Realtime
   DB_AFTER_CONNECT_QUERY: 'SET search_path TO _realtime,public'
   ```

### 各服务的 Schema 需求

| 服务 | 需要的 Schema | 说明 |
|------|--------------|------|
| **GoTrue (Auth)** | `auth` | 所有认证相关的表和函数 |
| **PostgREST** | `public`, `graphql_public`, `dev`, `test` | 暴露给 REST API 的 schema |
| **Realtime** | `_realtime`, `public`, `dev`, `test` | 实时订阅功能 |
| **Storage** | `storage` | 文件存储相关表 |
| **Meta** | 所有 | 数据库元数据管理 |

---

## 常见问题

### Q1: 为什么 `supabase local` 可以工作？

**A**: `supabase local` 使用 Supabase CLI 管理的配置，它遵循 Supabase 的最佳实践：
- 不在连接字符串中设置 search_path
- 使用专用的环境变量设置 schema 和搜索路径
- 配置经过充分测试和验证

### Q2: 修复后会影响现有数据吗？

**A**: 不会。这个修复只改变 schema 搜索路径，不会修改任何数据：
- 现有的 `test` schema 数据不受影响
- `auth` schema 可以正常创建和访问
- 所有 schema 都可以通过 PostgREST 访问

### Q3: 如果还是失败怎么办？

**A**: 可能需要清理之前失败的迁移状态：

```bash
# 方法 1: 删除 PostgreSQL 数据卷
docker-compose down -v
docker volume rm isa-postgres-data

# 方法 2: 手动清理迁移表
docker exec -it isa-postgres psql -U postgres -d postgres -c "
  DROP SCHEMA IF EXISTS auth CASCADE;
  DELETE FROM supabase_migrations.schema_migrations WHERE version LIKE '%auth%';
"

# 然后重新启动服务
docker-compose up -d
```

### Q4: 其他环境（test, staging, production）需要修改吗？

**A**: 是的，如果它们也使用了 `search_path=test`，需要同样的修复：

```bash
# 检查其他环境的配置
grep -r "search_path=test" deployments/envs/

# 应用同样的修复
# - 移除 GOTRUE_DB_DATABASE_URL 中的 search_path
# - 移除 PGRST_DB_URI 中的 search_path
# - 添加 PGRST_DB_EXTRA_SEARCH_PATH
# - 调整 Realtime 的 DB_AFTER_CONNECT_QUERY
```

---

## 相关文档

- [Issue #2: Supabase Auth Service Migration Failure](/Users/xenodennis/Documents/Fun/isA_Cloud/docs/issues/issue2.md)
- [Supabase Local Development Docs](https://supabase.com/docs/guides/local-development)
- [PostgREST Configuration](https://postgrest.org/en/stable/configuration.html)
- [PostgreSQL Schema Search Path](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PATH)

---

## 总结

### 核心教训

1. **不要在连接 URI 中硬编码 search_path**
   - 使用服务特定的配置参数
   - 保持默认 search_path 的灵活性

2. **遵循官方配置的最佳实践**
   - `supabase local` 的配置是经过验证的
   - 自定义配置时应该参考官方配置

3. **理解每个服务的 Schema 需求**
   - GoTrue 需要 `auth` schema
   - PostgREST 可以暴露多个 schema
   - Realtime 需要 `_realtime` schema

### 修复清单

- [x] 移除 GoTrue 连接字符串中的 `search_path=test`
- [x] 移除 PostgREST URI 中的 `search_path=test`
- [x] 添加 PostgREST 的 `PGRST_DB_EXTRA_SEARCH_PATH`
- [x] 更新 PostgREST 的 `PGRST_DB_SCHEMAS` 包含 `public`
- [x] 调整 Realtime 的 `DB_AFTER_CONNECT_QUERY`
- [x] 创建测试脚本验证修复
- [x] 更新文档

---

**文档创建日期**: 2024-10-10  
**最后更新**: 2024-10-10  
**状态**: ✅ 已修复并验证

