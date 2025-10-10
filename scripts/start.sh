#!/bin/bash

# IsA Cloud Gateway Start Script

set -e

# Get project root
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"

echo "🚀 Starting IsA Cloud Gateway..."

# Check if binary exists
if [ ! -f "bin/gateway" ]; then
    echo "📦 Gateway binary not found. Building..."
    ./scripts/build.sh
fi

# Check if config exists
if [ ! -f "deployments/configs/dev/gateway.yaml" ]; then
    echo "❌ Configuration file not found: deployments/configs/dev/gateway.yaml"
    exit 1
fi

# Show configuration
echo "📋 Configuration:"
echo "   Config file: deployments/configs/dev/gateway.yaml"
echo "   HTTP port: $(grep 'http_port:' deployments/configs/dev/gateway.yaml | awk '{print $2}')"
echo "   gRPC port: $(grep 'grpc_port:' deployments/configs/dev/gateway.yaml | awk '{print $2}')"
echo ""

# Start the gateway
echo "🔥 Starting gateway..."
exec ./bin/gateway --config deployments/configs/dev/gateway.yaml "$@"