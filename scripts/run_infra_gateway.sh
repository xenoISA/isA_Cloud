#!/bin/bash

# Infrastructure Gateway Build and Run Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "🚀 Infrastructure Gateway Startup Script"
echo "========================================"

# Change to project root
cd "${PROJECT_ROOT}"

# Load environment variables
if [ -f "deployments/envs/dev/.env" ]; then
    echo "📄 Loading development environment variables..."
    export $(grep -v '^#' deployments/envs/dev/.env | xargs)
fi

# Check Go installation
if ! command -v go &> /dev/null; then
    echo "❌ Go is not installed. Please install Go 1.21 or later."
    exit 1
fi

echo "✅ Go version: $(go version)"

# Check if go.mod needs update
echo "📦 Updating Go dependencies..."
go mod tidy
go mod download

# Build the application
echo "🔨 Building Infrastructure Gateway..."
go build -o bin/infra-gateway cmd/infra-gateway/main.go

if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
else
    echo "❌ Build failed!"
    exit 1
fi

# Set default environment variables if not set
export SUPABASE_URL="${SUPABASE_URL:-}"
export SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY:-}"
export REDIS_HOST="${REDIS_HOST:-localhost}"
export CONSUL_HOST="${CONSUL_HOST:-localhost}"

# Check if required environment variables are set
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_ANON_KEY" ]; then
    echo "⚠️  Warning: Supabase credentials not set"
    echo "   Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables"
    echo "   Gateway will start but Supabase operations will fail"
fi

# Create bin directory if it doesn't exist
mkdir -p bin

# Run the gateway
echo "🌐 Starting Infrastructure Gateway on port 8090..."
echo "   Health check: http://localhost:8090/health"
echo "   Metrics: http://localhost:9090/metrics"
echo "   API endpoint: http://localhost:8090/api/v1/infra/"
echo ""
echo "Press Ctrl+C to stop the gateway"
echo ""

# Run with config file
./bin/infra-gateway --config deployments/configs/infra-gateway.yaml