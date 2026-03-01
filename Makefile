# isA Cloud Makefile
# Python infrastructure SDK (isa_common) + Docker Compose local dev

.PHONY: help install test lint fmt clean dev dev-down dev-logs dev-status health ports

# Variables
COMPOSE_FILE := docker-compose.yml
PYTHON := python3
PIP := pip3
PYTEST := $(PYTHON) -m pytest
SDK_DIR := isA_common

# ==================== Help ====================

help: ## Display this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# ==================== Python SDK ====================

install: ## Install isa_common in development mode
	@echo "Installing isa_common..."
	@cd $(SDK_DIR) && $(PIP) install -e ".[dev]"
	@echo "Done"

test: ## Run all tests (integration tests skip if services unavailable)
	@echo "Running tests..."
	@cd $(SDK_DIR) && $(PYTEST) tests/ -v
	@echo "Done"

test-unit: ## Run unit tests only (no infrastructure needed)
	@echo "Running unit tests..."
	@cd $(SDK_DIR) && $(PYTEST) tests/nats/test_async_nats_reconnect.py tests/component/ -v
	@echo "Done"

test-smoke: ## Run billing pipeline smoke tests
	@echo "Running smoke tests..."
	@cd $(SDK_DIR) && $(PYTEST) tests/smoke/ -m smoke -v
	@echo "Done"

test-service: ## Run tests for a specific service (usage: make test-service s=redis)
ifdef s
	@cd $(SDK_DIR) && $(PYTEST) tests/$(s)/ -v
else
	@echo "Specify service: make test-service s=redis"
	@echo "Available: redis postgres nats mqtt minio qdrant neo4j duck"
endif

lint: ## Run linter (flake8)
	@echo "Running linter..."
	@cd $(SDK_DIR) && $(PYTHON) -m flake8 isa_common/ --max-line-length=100
	@echo "Done"

fmt: ## Format code (black)
	@echo "Formatting code..."
	@cd $(SDK_DIR) && $(PYTHON) -m black isa_common/ tests/ --line-length=100
	@echo "Done"

typecheck: ## Run type checker (mypy)
	@echo "Running type checker..."
	@cd $(SDK_DIR) && $(PYTHON) -m mypy isa_common/
	@echo "Done"

clean: ## Clean Python build artifacts
	@echo "Cleaning..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Done"

# ==================== Local Development (Docker Compose) ====================

dev: ## Start all infrastructure services for local development
	@echo "Starting infrastructure services..."
	@docker compose -f $(COMPOSE_FILE) up -d
	@echo "Done — run 'make dev-status' to check service health"

dev-down: ## Stop all infrastructure services
	@echo "Stopping infrastructure services..."
	@docker compose -f $(COMPOSE_FILE) down
	@echo "Done"

dev-destroy: ## Stop services and remove all data volumes
	@echo "Stopping services and removing volumes..."
	@docker compose -f $(COMPOSE_FILE) down -v
	@echo "Done"

dev-logs: ## View infrastructure service logs (usage: make dev-logs or make dev-logs s=redis)
ifdef s
	@docker compose -f $(COMPOSE_FILE) logs -f $(s)
else
	@docker compose -f $(COMPOSE_FILE) logs -f
endif

dev-status: ## Check status of infrastructure services
	@docker compose -f $(COMPOSE_FILE) ps

dev-restart: ## Restart a specific service (usage: make dev-restart s=redis)
ifdef s
	@docker compose -f $(COMPOSE_FILE) restart $(s)
else
	@echo "Specify service: make dev-restart s=redis"
endif

# ==================== Service Endpoints ====================

ports: ## Display all service endpoints
	@echo "Infrastructure Endpoints:"
	@echo "  PostgreSQL:       localhost:5432"
	@echo "  Redis:            localhost:6379"
	@echo "  Neo4j HTTP:       http://localhost:7474"
	@echo "  Neo4j Bolt:       localhost:7687"
	@echo "  NATS:             localhost:4222"
	@echo "  NATS Monitor:     http://localhost:8222"
	@echo "  MinIO API:        http://localhost:9000"
	@echo "  MinIO Console:    http://localhost:9001"
	@echo "  Mosquitto/MQTT:   localhost:1883"
	@echo "  Qdrant:           http://localhost:6333"
	@echo "  Loki:             http://localhost:3100"
	@echo "  Grafana:          http://localhost:3000"
	@echo "  Consul:           http://localhost:8500"

health: ## Quick health check for all services
	@echo "Checking service health..."
	@echo -n "  PostgreSQL:  " && (docker compose -f $(COMPOSE_FILE) exec -T postgres pg_isready -U postgres > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  Redis:       " && (docker compose -f $(COMPOSE_FILE) exec -T redis redis-cli ping > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  Neo4j:       " && (curl -sf http://localhost:7474/ > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  NATS:        " && (curl -sf http://localhost:8222/healthz > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  MinIO:       " && (curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  Qdrant:      " && (curl -sf http://localhost:6333/ > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  Loki:        " && (curl -sf http://localhost:3100/ready > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  Grafana:     " && (curl -sf http://localhost:3000/api/health > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  Consul:      " && (curl -sf http://localhost:8500/v1/status/leader > /dev/null 2>&1 && echo "OK" || echo "DOWN")
	@echo -n "  Mosquitto:   " && (docker compose -f $(COMPOSE_FILE) exec -T mosquitto mosquitto_sub -t '$$SYS/#' -C 1 -W 2 > /dev/null 2>&1 && echo "OK" || echo "DOWN")
