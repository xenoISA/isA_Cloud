# IsA Cloud Makefile

.PHONY: help proto build clean test docker-build docker-push dev

# Variables
PROJECT_NAME := isa_cloud
PROTO_DIR := api/proto
PKG_DIR := pkg/proto
GO_FILES := $(shell find . -name "*.go" -type f)
DOCKER_REGISTRY := ghcr.io/isa-cloud

# Help
help: ## Display this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Protocol Buffers
proto: ## Generate gRPC code from proto files
	@echo "Generating gRPC code..."
	@mkdir -p $(PKG_DIR)
	@protoc --go_out=$(PKG_DIR) --go_opt=paths=source_relative \
		--go-grpc_out=$(PKG_DIR) --go-grpc_opt=paths=source_relative \
		$(PROTO_DIR)/*.proto
	@echo "✅ gRPC code generated"

# Build
build: proto ## Build the application
	@echo "Building $(PROJECT_NAME)..."
	@go mod download
	@echo "✅ Build completed"

# Clean
clean: ## Clean build artifacts
	@echo "Cleaning..."
	@rm -rf bin/
	@rm -rf $(PKG_DIR)
	@go clean
	@echo "✅ Clean completed"

# Test
test: ## Run tests
	@echo "Running tests..."
	@go test -v ./...
	@echo "✅ Tests completed"

# Docker
docker-build: ## Build Docker images
	@echo "Building Docker images..."
	@echo "✅ Docker images built"

docker-push: docker-build ## Push Docker images
	@echo "Pushing Docker images..."
	@echo "✅ Docker images pushed"

# Development
dev: build ## Start development environment
	@echo "Starting development environment..."
	@docker-compose -f deployments/compose/docker-compose.dev.yml up -d
	@echo "✅ Development environment started"

# Dependencies
deps: ## Download dependencies
	@echo "Downloading dependencies..."
	@go mod download
	@go mod tidy
	@echo "✅ Dependencies updated"

# Lint
lint: ## Run linter
	@echo "Running linter..."
	@golangci-lint run
	@echo "✅ Lint completed"

# Format
fmt: ## Format code
	@echo "Formatting code..."
	@go fmt ./...
	@echo "✅ Code formatted"

# ====================
# Service Management
# ====================

SERVICE_MANAGER := ./scripts/service_manager.sh

# Start all services
start-all: ## Start all microservices
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) start all

# Stop all services  
stop-all: ## Stop all microservices
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) stop all

# Restart all services
restart-all: ## Restart all microservices
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) restart all

# Service status
status: ## Check status of all services
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) status

# Service health check
health: ## Health check for all services
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) health

# View service logs
logs: ## View logs (usage: make logs service=<service_name>)
ifdef service
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) logs $(service)
else
	@echo "Please specify a service: make logs service=<service_name>"
endif

# Start specific service
start-%: ## Start specific service (e.g., make start-auth)
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) start $*

# Stop specific service
stop-%: ## Stop specific service (e.g., make stop-auth)
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) stop $*

# Restart specific service
restart-%: ## Restart specific service (e.g., make restart-auth)
	@chmod +x $(SERVICE_MANAGER)
	@$(SERVICE_MANAGER) restart $*

# Show service ports
ports: ## Display all service ports
	@echo "Service Endpoints:"
	@echo "  APISIX Gateway:   http://localhost:9080"
	@echo "  APISIX Admin:     http://localhost:9180"
	@echo "  Consul UI:        http://localhost:8500"
	@echo "  Account Service:  http://localhost:8201"
	@echo "  Auth Service:     http://localhost:8202"
	@echo "  Authorization:    http://localhost:8203"
	@echo "  Audit Service:    http://localhost:8204"
	@echo "  Notification:     http://localhost:8206"
	@echo "  Payment Service:  http://localhost:8207"
	@echo "  Storage Service:  http://localhost:8209"

# Docker Compose management
docker-services-up: ## Start services with Docker Compose
	@docker-compose up -d

docker-services-down: ## Stop Docker Compose services
	@docker-compose down

docker-services-logs: ## View Docker Compose logs
	@docker-compose logs -f