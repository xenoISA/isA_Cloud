#!/bin/bash

# IsA Cloud Gateway Development Start Script
# This script rebuilds and starts the gateway service for local development

set -e

# Get project root
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$PROJECT_ROOT"

echo "🚀 Starting IsA Cloud Gateway (Development Mode)..."

# Stop any existing gateway processes
echo "🛑 Stopping existing gateway processes..."
pkill -f "bin/gateway" || true
sleep 1

# Build the gateway
echo "🏗️  Building gateway..."
./scripts/build.sh

# Check if config exists
CONFIG_FILE="deployments/configs/dev/gateway.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Show configuration
echo ""
echo "📋 Configuration:"
echo "   Environment: development"
echo "   Config file: $CONFIG_FILE"
echo "   HTTP port: 8000"
echo "   gRPC port: 8001"
echo ""

# Start the gateway
echo "🔥 Starting gateway..."
exec ./bin/gateway --config "$CONFIG_FILE" "$@"
