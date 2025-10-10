#!/bin/bash

# ============================================
# isA Platform - Infrastructure Services Launcher
# ============================================
# 用于启动和管理完整的基础设施服务栈
#
# 作者: isA Platform Team
# 日期: 2024

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOYMENTS_DIR="$PROJECT_ROOT/deployments"
COMPOSE_FILE="$DEPLOYMENTS_DIR/docker-compose.infrastructure-all.yml"

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示横幅
show_banner() {
    cat << "EOF"
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║     isA Platform - Infrastructure Services Manager            ║
║                                                                ║
║     完整的基础设施服务栈管理工具                               ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
EOF
    echo ""
}

# 显示帮助信息
show_help() {
    cat << EOF
使用方法: $0 [command] [options]

命令:
  up              启动所有基础设施服务
  down            停止所有基础设施服务
  restart         重启所有基础设施服务
  status          查看服务状态
  logs [service]  查看服务日志 (可选指定服务名)
  ps              查看运行中的容器
  clean           清理所有数据和容器
  health          检查所有服务健康状态
  init            初始化配置文件
  list            列出所有基础设施服务
  help            显示此帮助信息

选项:
  -d, --detach    后台运行 (用于 up 命令)
  -v, --volumes   同时删除数据卷 (用于 down 和 clean 命令)
  -f, --follow    跟踪日志输出 (用于 logs 命令)

示例:
  $0 up -d                  # 后台启动所有服务
  $0 status                 # 查看服务状态
  $0 logs -f consul         # 跟踪Consul日志
  $0 restart redis          # 重启Redis服务
  $0 down                   # 停止所有服务
  $0 clean -v               # 清理服务和数据

服务列表:
  - consul           服务发现和配置管理
  - nats-1,2,3       消息队列集群
  - mosquitto        MQTT代理
  - postgres         PostgreSQL数据库
  - redis            缓存服务
  - minio            对象存储
  - neo4j            图数据库
  - influxdb         时序数据库
  - loki             日志聚合
  - grafana          监控仪表板
  - supabase-*       Supabase服务栈

EOF
}

# 检查Docker和Docker Compose
check_dependencies() {
    log_info "检查依赖..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose 未安装或版本过旧，请安装 Docker Compose V2"
        exit 1
    fi
    
    log_success "依赖检查通过"
}

# 检查compose文件是否存在
check_compose_file() {
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_error "Compose文件不存在: $COMPOSE_FILE"
        exit 1
    fi
}

# 初始化环境配置
init_config() {
    log_info "初始化环境配置..."
    
    ENV_FILE="$DEPLOYMENTS_DIR/.env.infrastructure"
    ENV_EXAMPLE="$DEPLOYMENTS_DIR/.env.infrastructure.example"
    
    if [ -f "$ENV_FILE" ]; then
        log_warning "环境配置文件已存在: $ENV_FILE"
        read -p "是否覆盖? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "保持现有配置"
            return
        fi
    fi
    
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        log_success "已创建环境配置文件: $ENV_FILE"
        log_warning "请根据需要编辑此文件"
    else
        log_warning "示例配置文件不存在，将使用默认值"
    fi
}

# 启动服务
start_services() {
    local detach_flag=""
    if [[ "$1" == "-d" ]] || [[ "$1" == "--detach" ]]; then
        detach_flag="-d"
    fi
    
    log_info "启动基础设施服务..."
    cd "$DEPLOYMENTS_DIR"
    
    if [ -f ".env.infrastructure" ]; then
        export $(grep -v '^#' .env.infrastructure | xargs)
    fi
    
    docker compose -f "$COMPOSE_FILE" up $detach_flag
    
    if [ -n "$detach_flag" ]; then
        log_success "服务已在后台启动"
        log_info "使用 '$0 status' 查看状态"
        log_info "使用 '$0 logs -f' 查看实时日志"
    fi
}

# 停止服务
stop_services() {
    local volumes_flag=""
    if [[ "$1" == "-v" ]] || [[ "$1" == "--volumes" ]]; then
        volumes_flag="-v"
        log_warning "将同时删除数据卷！"
        read -p "确认继续? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "操作已取消"
            return
        fi
    fi
    
    log_info "停止基础设施服务..."
    cd "$DEPLOYMENTS_DIR"
    docker compose -f "$COMPOSE_FILE" down $volumes_flag
    log_success "服务已停止"
}

# 重启服务
restart_services() {
    local service=""
    if [ -n "$1" ]; then
        service="$1"
        log_info "重启服务: $service"
    else
        log_info "重启所有服务..."
    fi
    
    cd "$DEPLOYMENTS_DIR"
    docker compose -f "$COMPOSE_FILE" restart $service
    log_success "服务已重启"
}

# 查看状态
show_status() {
    log_info "查看服务状态..."
    cd "$DEPLOYMENTS_DIR"
    docker compose -f "$COMPOSE_FILE" ps
}

# 查看日志
show_logs() {
    local follow_flag=""
    local service=""
    
    # 解析参数
    while [ $# -gt 0 ]; do
        case "$1" in
            -f|--follow)
                follow_flag="-f"
                shift
                ;;
            *)
                service="$1"
                shift
                ;;
        esac
    done
    
    if [ -n "$service" ]; then
        log_info "查看服务日志: $service"
    else
        log_info "查看所有服务日志..."
    fi
    
    cd "$DEPLOYMENTS_DIR"
    docker compose -f "$COMPOSE_FILE" logs $follow_flag $service
}

# 查看运行中的容器
show_containers() {
    log_info "运行中的容器..."
    docker ps --filter "network=isa-network" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# 清理所有服务和数据
clean_all() {
    local volumes_flag=""
    if [[ "$1" == "-v" ]] || [[ "$1" == "--volumes" ]]; then
        volumes_flag="-v"
    fi
    
    log_warning "这将删除所有基础设施服务容器"
    if [ -n "$volumes_flag" ]; then
        log_warning "同时会删除所有数据卷（数据将永久丢失）！"
    fi
    
    read -p "确认继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "操作已取消"
        return
    fi
    
    log_info "清理服务..."
    cd "$DEPLOYMENTS_DIR"
    docker compose -f "$COMPOSE_FILE" down $volumes_flag
    
    log_info "清理未使用的镜像..."
    docker image prune -f
    
    log_success "清理完成"
}

# 检查健康状态
check_health() {
    log_info "检查服务健康状态..."
    cd "$DEPLOYMENTS_DIR"
    
    echo ""
    echo "服务健康状态:"
    echo "============================================"
    
    docker compose -f "$COMPOSE_FILE" ps --format json | jq -r '.[] | "\(.Name)\t\(.Health)"' | while IFS=$'\t' read -r name health; do
        if [ -z "$health" ] || [ "$health" == "null" ]; then
            echo -e "${YELLOW}⚠${NC}  $name - 无健康检查"
        elif [[ "$health" == *"healthy"* ]]; then
            echo -e "${GREEN}✓${NC}  $name - 健康"
        else
            echo -e "${RED}✗${NC}  $name - $health"
        fi
    done
    
    echo "============================================"
    echo ""
}

# 列出所有服务
list_services() {
    log_info "基础设施服务列表:"
    echo ""
    cat << EOF
╔══════════════════╦═════════════════════════════╦═══════════════════════╗
║ 服务名称         ║ 描述                        ║ 默认端口              ║
╠══════════════════╬═════════════════════════════╬═══════════════════════╣
║ consul           ║ 服务发现和配置管理          ║ 8500, 8600            ║
║ nats-1           ║ NATS消息队列节点1           ║ 4222, 6222, 8222      ║
║ nats-2           ║ NATS消息队列节点2           ║ 4223, 6223, 8223      ║
║ nats-3           ║ NATS消息队列节点3           ║ 4224, 6224, 8224      ║
║ mosquitto        ║ MQTT消息代理                ║ 1883, 9001            ║
║ postgres         ║ PostgreSQL数据库            ║ 5432                  ║
║ redis            ║ 缓存服务                    ║ 6379                  ║
║ minio            ║ 对象存储                    ║ 9000, 9001            ║
║ neo4j            ║ 图数据库                    ║ 7474, 7687            ║
║ influxdb         ║ 时序数据库                  ║ 8086                  ║
║ loki             ║ 日志聚合                    ║ 3100                  ║
║ promtail         ║ 日志收集器                  ║ -                     ║
║ grafana          ║ 监控仪表板                  ║ 3003                  ║
║ supabase-kong    ║ Supabase API网关            ║ 54321, 54322          ║
║ supabase-auth    ║ Supabase认证服务            ║ -                     ║
║ supabase-rest    ║ Supabase REST API           ║ -                     ║
║ supabase-realtime║ Supabase实时服务            ║ -                     ║
║ supabase-storage ║ Supabase存储服务            ║ -                     ║
║ supabase-meta    ║ Supabase元数据服务          ║ -                     ║
║ supabase-studio  ║ Supabase管理界面            ║ 通过Kong访问          ║
║ gateway          ║ isA API网关                 ║ 8000                  ║
╚══════════════════╩═════════════════════════════╩═══════════════════════╝

访问地址:
  Consul UI:        http://localhost:8500
  MinIO Console:    http://localhost:9001
  Neo4j Browser:    http://localhost:7474
  InfluxDB:         http://localhost:8086
  Grafana:          http://localhost:3003
  Supabase API:     http://localhost:54321
  Gateway API:      http://localhost:8000

EOF
}

# 主程序
main() {
    show_banner
    check_dependencies
    
    # 如果没有参数，显示帮助
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    # 对于非help和init命令，检查compose文件
    if [[ "$1" != "help" ]] && [[ "$1" != "init" ]] && [[ "$1" != "list" ]]; then
        check_compose_file
    fi
    
    # 解析命令
    case "$1" in
        up|start)
            shift
            start_services "$@"
            ;;
        down|stop)
            shift
            stop_services "$@"
            ;;
        restart)
            shift
            restart_services "$@"
            ;;
        status)
            show_status
            ;;
        logs)
            shift
            show_logs "$@"
            ;;
        ps)
            show_containers
            ;;
        clean)
            shift
            clean_all "$@"
            ;;
        health)
            check_health
            ;;
        init)
            init_config
            ;;
        list)
            list_services
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主程序
main "$@"

