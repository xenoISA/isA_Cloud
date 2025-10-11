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

# 检查 protoc 是否已安装
if ! command -v protoc &> /dev/null; then
    echo "Error: protoc is not installed"
    echo "Please install it first:"
    echo "  macOS: brew install protobuf"
    echo "  Linux: apt-get install -y protobuf-compiler"
    exit 1
fi

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

# 进入项目根目录
cd "$(dirname "$0")/.."

echo ""
echo "Generating Go code..."
echo ""

# 生成 common.proto
echo "→ Generating common.proto..."
protoc --go_out=. --go_opt=paths=source_relative \
    api/proto/common.proto

# 生成所有服务的 proto
SERVICES=("minio" "duckdb" "mqtt" "loki" "redis" "nats")

for service in "${SERVICES[@]}"; do
    echo "→ Generating ${service}_service.proto..."
    protoc --go_out=. --go_opt=paths=source_relative \
        --go-grpc_out=. --go-grpc_opt=paths=source_relative \
        api/proto/${service}_service.proto
done

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



