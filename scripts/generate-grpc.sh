#!/bin/bash
# 生成所有 Proto 文件的 gRPC 代码
# Generate gRPC code for all proto files
#
# 文件名: scripts/generate-grpc.sh
#
# 使用方法:
#   chmod +x scripts/generate-grpc.sh
#   ./scripts/generate-grpc.sh

set -e

echo "============================================"
echo "Generating gRPC code from Proto files"
echo "============================================"

# 进入项目根目录
cd "$(dirname "$0")/.."

# 检查 protoc 是否已安装（用于 Go 代码生成）
if command -v protoc &> /dev/null; then
    echo ""
    echo "Generating Go code..."
    echo ""

    # 检查 Go plugins 是否已安装
    if ! command -v protoc-gen-go &> /dev/null; then
        echo "Installing protoc-gen-go..."
        go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
    fi

    if ! command -v protoc-gen-go-grpc &> /dev/null; then
        echo "Installing protoc-gen-go-grpc..."
        go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
    fi

    # 确保 $GOPATH/bin 在 PATH 中
    export PATH="$PATH:$(go env GOPATH)/bin"

    # 生成 common.proto
    echo "→ Generating common.proto..."
    protoc --proto_path=api/proto \
        --go_out=. --go_opt=module=github.com/isa-cloud/isa_cloud \
        api/proto/common.proto

    # 生成所有服务的 proto
    SERVICES=("minio" "duckdb" "mqtt" "loki" "redis" "nats" "postgres" "qdrant" "neo4j")

    for service in "${SERVICES[@]}"; do
        echo "→ Generating ${service}_service.proto..."
        protoc --proto_path=api/proto \
            --go_out=. --go_opt=module=github.com/isa-cloud/isa_cloud \
            --go-grpc_out=. --go-grpc_opt=module=github.com/isa-cloud/isa_cloud \
            api/proto/${service}_service.proto
    done
else
    echo "⚠️  protoc not found - skipping Go code generation"
    echo "   Please install protoc to generate Go code locally"
    echo "   Run: brew install protobuf (macOS) or apt-get install protobuf-compiler (Linux)"
fi

SERVICES=("minio" "duckdb" "mqtt" "loki" "redis" "nats" "postgres" "qdrant" "neo4j")

echo ""
echo "============================================"
echo "Generating Python code for isA_common/isa_common/proto..."
echo "============================================"
echo ""

# 创建 Python proto 目录（如果不存在）
mkdir -p isA_common/isa_common/proto

# 生成 common.proto (Python)
echo "→ Generating common.proto (Python)..."
python3 -m grpc_tools.protoc \
    --proto_path=api/proto \
    --python_out=isA_common/isa_common/proto \
    --grpc_python_out=isA_common/isa_common/proto \
    api/proto/common.proto

# 生成所有服务的 proto (Python)
for service in "${SERVICES[@]}"; do
    echo "→ Generating ${service}_service.proto (Python)..."
    python3 -m grpc_tools.protoc \
        --proto_path=api/proto \
        --python_out=isA_common/isa_common/proto \
        --grpc_python_out=isA_common/isa_common/proto \
        api/proto/${service}_service.proto
done

# Fix imports in generated Python files (convert to relative imports)
echo "→ Fixing Python imports..."
for file in isA_common/isa_common/proto/*_pb2.py isA_common/isa_common/proto/*_pb2_grpc.py; do
    if [ -f "$file" ]; then
        # Fix: import common_pb2 -> from . import common_pb2
        sed -i.bak 's/^import common_pb2/from . import common_pb2/g' "$file"
        # Fix: import xxx_service_pb2 as -> from . import xxx_service_pb2 as
        sed -i.bak 's/^import \([a-z0-9_]*\)_service_pb2 as/from . import \1_service_pb2 as/g' "$file"
        # Fix: import xxx_service_pb2 (with space at end) -> from . import xxx_service_pb2
        sed -i.bak 's/^import \([a-z0-9_]*\)_service_pb2 /from . import \1_service_pb2 /g' "$file"
        # Remove backup files
        rm -f "$file.bak"
    fi
done

# 创建 __init__.py
echo "→ Creating __init__.py..."
cat > isA_common/isa_common/proto/__init__.py << 'EOF'
"""
gRPC Proto Generated Files
"""
from . import common_pb2
from . import minio_service_pb2, minio_service_pb2_grpc
from . import duckdb_service_pb2, duckdb_service_pb2_grpc
from . import mqtt_service_pb2, mqtt_service_pb2_grpc
from . import loki_service_pb2, loki_service_pb2_grpc
from . import redis_service_pb2, redis_service_pb2_grpc
from . import nats_service_pb2, nats_service_pb2_grpc
from . import postgres_service_pb2, postgres_service_pb2_grpc
from . import qdrant_service_pb2, qdrant_service_pb2_grpc
from . import neo4j_service_pb2, neo4j_service_pb2_grpc

__all__ = [
    'common_pb2',
    'minio_service_pb2', 'minio_service_pb2_grpc',
    'duckdb_service_pb2', 'duckdb_service_pb2_grpc',
    'mqtt_service_pb2', 'mqtt_service_pb2_grpc',
    'loki_service_pb2', 'loki_service_pb2_grpc',
    'redis_service_pb2', 'redis_service_pb2_grpc',
    'nats_service_pb2', 'nats_service_pb2_grpc',
    'postgres_service_pb2', 'postgres_service_pb2_grpc',
    'qdrant_service_pb2', 'qdrant_service_pb2_grpc',
    'neo4j_service_pb2', 'neo4j_service_pb2_grpc',
]
EOF

echo ""
echo "============================================"
echo "✅ All gRPC code generated successfully!"
echo "============================================"
echo ""
echo "Generated files:"
ls -lh api/proto/*.pb.go 2>/dev/null || echo "  (files will appear after first run)"

echo ""
echo "Next steps:"
echo "  1. Review generated code in api/proto/"
echo "  2. Build services: make build-services"
echo "  3. Run services: docker-compose up"
echo ""



