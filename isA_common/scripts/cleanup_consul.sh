#!/bin/bash

# Cleanup script for stale Consul service registrations
# Removes all services with short container IDs (12 hex chars)

CONSUL_URL="http://localhost:8500"

echo "🔍 Fetching all registered services..."
services=$(curl -s "$CONSUL_URL/v1/agent/services" | jq -r 'keys[]')

# Valid hostnames we want to keep
VALID_PATTERNS=(
  "user-staging"
  "agent-staging-test"
  "model-staging-test"
  "mcp-staging-test"
  "isa-duckdb-grpc"
  "isa-loki-grpc"
  "isa-minio-grpc"
  "isa-nats-grpc"
  "isa-redis-grpc"
  "xenodenniss-MacBook-Air.local"  # test services
)

removed_count=0
kept_count=0

for service_id in $services; do
  # Check if service contains a short container ID (12 hex chars pattern)
  if echo "$service_id" | grep -qE '[0-9a-f]{12}'; then
    echo "❌ Removing stale: $service_id"
    curl -s -X PUT "$CONSUL_URL/v1/agent/service/deregister/$service_id" > /dev/null
    ((removed_count++))
  else
    # Check if it's a valid hostname
    is_valid=false
    for pattern in "${VALID_PATTERNS[@]}"; do
      if echo "$service_id" | grep -q "$pattern"; then
        is_valid=true
        break
      fi
    done
    
    if [ "$is_valid" = true ]; then
      echo "✅ Keeping valid: $service_id"
      ((kept_count++))
    else
      # Remove anything that doesn't match valid patterns
      echo "⚠️  Removing unknown: $service_id"
      curl -s -X PUT "$CONSUL_URL/v1/agent/service/deregister/$service_id" > /dev/null
      ((removed_count++))
    fi
  fi
done

echo ""
echo "📊 Summary:"
echo "  ✅ Kept: $kept_count services"
echo "  ❌ Removed: $removed_count stale services"
echo ""
echo "🔍 Remaining services:"
curl -s "$CONSUL_URL/v1/agent/services" | jq -r 'to_entries | map(.key) | sort[]'
