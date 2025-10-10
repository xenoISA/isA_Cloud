#!/bin/bash

# IsA Cloud Gateway Build Script

set -e

echo "🏗️ Building IsA Cloud Gateway..."

# Get project root
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"

# Check if Go is installed
if ! command -v go &> /dev/null; then
    echo "❌ Go is not installed. Please install Go 1.21 or later."
    exit 1
fi

# Check Go version
GO_VERSION=$(go version | awk '{print $3}' | sed 's/go//')
echo "🔍 Go version: $GO_VERSION"

# Initialize go.mod if it doesn't exist
if [ ! -f "go.mod" ]; then
    echo "📦 Initializing go.mod..."
    go mod init github.com/isa-cloud/isa_cloud
fi

# Download dependencies
echo "📥 Downloading dependencies..."
go mod download

# Add missing dependencies
echo "🔧 Adding missing dependencies..."
go get github.com/gin-gonic/gin@latest
go get github.com/gin-contrib/cors@latest
go get github.com/spf13/cobra@latest
go get github.com/spf13/viper@latest
go get github.com/google/uuid@latest
go get golang.org/x/time/rate@latest
go get google.golang.org/grpc@latest
go get google.golang.org/protobuf@latest

# Tidy up
go mod tidy

# Create bin directory
mkdir -p bin

# Build the gateway
echo "🔨 Building gateway..."
CGO_ENABLED=0 go build -ldflags="-w -s" -o bin/gateway ./cmd/gateway

echo "✅ Build completed successfully!"
echo "📁 Binary location: bin/gateway"
echo ""
echo "🚀 To run the gateway:"
echo "   ./bin/gateway --config deployments/configs/gateway.yaml"