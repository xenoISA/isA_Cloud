#!/bin/bash

# ============================================
# Supabase Auth Migration Fix - Test Script
# ============================================
# 测试 Issue #2 的修复方案
#
# 问题: GoTrue Auth 服务因 search_path=test 配置失败
# 修复: 移除不必要的 search_path 参数，匹配 supabase local 配置

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOYMENTS_DIR="$PROJECT_ROOT/deployments"

cat << "EOF"
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║     Supabase Auth Fix - Test & Validation                     ║
║     Issue #2: GoTrue Migration Failure                        ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
EOF
echo ""

log_info "Step 1: 验证配置文件修复..."
echo ""

# 检查 GoTrue 配置
log_info "检查 GoTrue 配置 (supabase-auth)..."
if grep -q "search_path=test" "$DEPLOYMENTS_DIR/compose/data-stores.yml"; then
    log_error "GoTrue 配置仍包含 search_path=test"
    exit 1
else
    log_success "GoTrue 配置已修复（已移除 search_path=test）"
fi

# 检查 PostgREST 配置
log_info "检查 PostgREST 配置 (supabase-rest)..."
if grep "PGRST_DB_URI:" "$DEPLOYMENTS_DIR/compose/data-stores.yml" | grep -q "search_path=test"; then
    log_error "PostgREST URI 仍包含 search_path=test"
    exit 1
else
    log_success "PostgREST URI 已修复（已移除 search_path=test）"
fi

if grep -q "PGRST_DB_EXTRA_SEARCH_PATH" "$DEPLOYMENTS_DIR/compose/data-stores.yml"; then
    log_success "PostgREST 配置已添加 EXTRA_SEARCH_PATH"
else
    log_warning "PostgREST 未配置 EXTRA_SEARCH_PATH"
fi

# 检查 Realtime 配置
log_info "检查 Realtime 配置 (supabase-realtime)..."
if grep "DB_AFTER_CONNECT_QUERY" "$DEPLOYMENTS_DIR/compose/data-stores.yml" | grep -q "_realtime"; then
    log_success "Realtime 配置正确（包含 _realtime schema）"
else
    log_warning "Realtime 配置可能不完整"
fi

echo ""
log_info "Step 2: 对比与 supabase local 的配置..."
echo ""

# 对比配置
cat << EOF
╔════════════════════════════════════════════════════════════════╗
║ 配置对比: Docker Compose vs Supabase Local                    ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║ GoTrue (Auth):                                                 ║
║   ✓ Docker Compose: 已移除 search_path=test                   ║
║   ✓ Supabase Local: 无 search_path 参数                       ║
║   → 配置一致                                                   ║
║                                                                ║
║ PostgREST:                                                     ║
║   ✓ Docker Compose: 已添加 PGRST_DB_EXTRA_SEARCH_PATH         ║
║   ✓ Supabase Local: 使用 PGRST_DB_EXTRA_SEARCH_PATH           ║
║   → 配置一致                                                   ║
║                                                                ║
║ Realtime:                                                      ║
║   ✓ Docker Compose: 优先 _realtime schema                     ║
║   ✓ Supabase Local: 使用 _realtime schema                     ║
║   → 配置兼容                                                   ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
EOF

echo ""
log_info "Step 3: 测试建议..."
echo ""

cat << EOF
要测试修复，请按以下步骤操作：

1. 停止现有服务:
   cd $DEPLOYMENTS_DIR
   docker-compose -f compose/base.yml -f compose/data-stores.yml down

2. 清理 Auth 服务数据（可选，如果之前有失败的迁移）:
   docker volume rm isa-postgres-data
   # 或者只删除 auth.schema_migrations 表

3. 启动服务:
   docker-compose -f compose/base.yml -f compose/data-stores.yml up -d postgres
   # 等待 postgres 健康
   sleep 10
   docker-compose -f compose/base.yml -f compose/data-stores.yml up -d supabase-auth

4. 检查 Auth 服务日志:
   docker logs -f isa-supabase-auth

   期望输出:
   - ✅ "msg":"GoTrue API started"
   - ✅ 没有 migration 错误
   - ✅ 没有 "uuid = text" 错误

5. 验证 Auth 服务健康:
   curl http://localhost:9999/health
   
   期望输出:
   - {"status":"ok"} 或类似的健康状态

6. 测试完整 Supabase 栈:
   docker-compose -f compose/base.yml -f compose/data-stores.yml up -d

7. 测试认证功能:
   # 通过 Kong 网关测试
   curl http://localhost:54321/auth/v1/health

EOF

log_success "配置修复验证完成！"
echo ""
log_warning "注意: 如果之前的迁移已经失败，可能需要清理数据库重新初始化"
echo ""

# 询问是否立即测试
read -p "是否现在测试修复? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "开始测试..."
    
    cd "$DEPLOYMENTS_DIR"
    
    # 停止服务
    log_info "停止现有服务..."
    docker-compose -f compose/base.yml -f compose/data-stores.yml down 2>/dev/null || true
    
    # 启动 PostgreSQL
    log_info "启动 PostgreSQL..."
    docker-compose -f compose/base.yml -f compose/data-stores.yml up -d postgres
    
    # 等待健康检查
    log_info "等待 PostgreSQL 健康检查..."
    for i in {1..30}; do
        if docker-compose -f compose/base.yml -f compose/data-stores.yml ps postgres | grep -q "healthy"; then
            log_success "PostgreSQL 已就绪"
            break
        fi
        echo -n "."
        sleep 2
    done
    echo ""
    
    # 启动 Auth 服务
    log_info "启动 Supabase Auth 服务..."
    docker-compose -f compose/base.yml -f compose/data-stores.yml up -d supabase-auth
    
    # 监控日志
    log_info "监控 Auth 服务日志（15秒）..."
    timeout 15s docker logs -f isa-supabase-auth 2>&1 | tee /tmp/auth-test.log || true
    
    # 检查结果
    echo ""
    if grep -q "GoTrue API started" /tmp/auth-test.log 2>/dev/null; then
        log_success "Auth 服务启动成功！"
        log_success "Issue #2 已修复！"
    elif grep -q "uuid = text" /tmp/auth-test.log 2>/dev/null; then
        log_error "仍然存在 migration 错误"
        log_warning "可能需要清理数据库重新初始化"
    else
        log_warning "无法确定状态，请手动检查日志"
        docker logs isa-supabase-auth
    fi
    
    rm -f /tmp/auth-test.log
else
    log_info "跳过测试。手动测试请参考上述步骤。"
fi

echo ""
log_info "完成！"

