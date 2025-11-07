#!/bin/bash

# ============================================
# Consul Service Registry - Comprehensive Functional Tests
# ============================================
# Tests Consul operations including:
# - Service registration and deregistration
# - Service discovery (single and multiple instances)
# - Load balancing strategies (round-robin, health-weighted, random)
# - Health check mechanisms (TTL and HTTP)
# - Configuration management (KV store)
# - Service watching and updates
# - Best practices validation

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
CONSUL_HOST="${CONSUL_HOST:-localhost}"
CONSUL_PORT="${CONSUL_PORT:-8500}"
TEST_SERVICE_NAME="test-service"
TEST_SERVICE_PORT=9999
MULTI_INSTANCE_PORT_1=9991
MULTI_INSTANCE_PORT_2=9992
MULTI_INSTANCE_PORT_3=9993

# Counters
PASSED=0
FAILED=0
TOTAL=0

# Test result function
test_result() {
    TOTAL=$((TOTAL + 1))
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN} PASSED${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED} FAILED${NC}"
        FAILED=$((FAILED + 1))
    fi
}

# Cleanup function
cleanup() {
    echo ""
    echo -e "${CYAN}Cleaning up test resources...${NC}"
    python3 <<EOF 2>/dev/null
from isa_common.consul_client import ConsulRegistry

# Cleanup test services
test_services = [
    '${TEST_SERVICE_NAME}',
    '${TEST_SERVICE_NAME}-multi-1',
    '${TEST_SERVICE_NAME}-multi-2',
    '${TEST_SERVICE_NAME}-multi-3',
    'nats-test',
    'auth-test',
    'payment-test'
]

for service_name in test_services:
    try:
        registry = ConsulRegistry(
            service_name=service_name,
            service_port=${TEST_SERVICE_PORT},
            consul_host='${CONSUL_HOST}',
            consul_port=${CONSUL_PORT}
        )
        registry.deregister()
    except Exception:
        pass

# Cleanup KV store test keys
try:
    registry = ConsulRegistry(
        service_name='${TEST_SERVICE_NAME}',
        service_port=${TEST_SERVICE_PORT},
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT}
    )
    registry.consul.kv.delete('${TEST_SERVICE_NAME}/', recurse=True)
except Exception:
    pass
EOF
}

# ========================================
# Test Functions
# ========================================

test_consul_connectivity() {
    echo -e "${YELLOW}Test 1: Consul Server Connectivity${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
import consul
try:
    client = consul.Consul(host='${CONSUL_HOST}', port=${CONSUL_PORT})
    # Try to access the catalog
    services = client.catalog.services()
    if services:
        print("PASS: Connected to Consul successfully")
    else:
        print("FAIL: Could not retrieve catalog")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
        echo -e "${RED}Cannot proceed without Consul connectivity${NC}"
        exit 1
    fi
}

test_service_registration_ttl() {
    echo -e "${YELLOW}Test 2: Service Registration with TTL Health Check${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    registry = ConsulRegistry(
        service_name='${TEST_SERVICE_NAME}',
        service_port=${TEST_SERVICE_PORT},
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT},
        tags=['test', 'v1.0'],
        health_check_type='ttl'
    )

    if registry.register():
        # Verify the service is registered
        services = registry.consul.agent.services()
        if registry.service_id in services:
            print(f"PASS: Service registered with TTL health check - ID: {registry.service_id}")
        else:
            print("FAIL: Service not found in registry after registration")
    else:
        print("FAIL: Registration returned False")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_service_discovery_single() {
    echo -e "${YELLOW}Test 3: Discover Single Service Instance${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    registry = ConsulRegistry(
        service_name='${TEST_SERVICE_NAME}',
        service_port=${TEST_SERVICE_PORT},
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT}
    )

    instances = registry.discover_service('${TEST_SERVICE_NAME}')
    if len(instances) > 0:
        instance = instances[0]
        print(f"PASS: Discovered service - Address: {instance['address']}, Port: {instance['port']}, Tags: {instance['tags']}")
    else:
        print("FAIL: No service instances found")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_service_endpoint_retrieval() {
    echo -e "${YELLOW}Test 4: Get Service Endpoint URL${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    registry = ConsulRegistry(
        service_name='${TEST_SERVICE_NAME}',
        service_port=${TEST_SERVICE_PORT},
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT}
    )

    endpoint = registry.get_service_endpoint('${TEST_SERVICE_NAME}')
    if endpoint and 'http://' in endpoint and ':${TEST_SERVICE_PORT}' in endpoint:
        print(f"PASS: Retrieved endpoint URL: {endpoint}")
    else:
        print(f"FAIL: Invalid endpoint: {endpoint}")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_config_management() {
    echo -e "${YELLOW}Test 5: Configuration Management (KV Store)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
import json
try:
    registry = ConsulRegistry(
        service_name='${TEST_SERVICE_NAME}',
        service_port=${TEST_SERVICE_PORT},
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT}
    )

    # Set config values
    config_data = {
        'database_url': 'postgresql://localhost:5432/testdb',
        'cache_ttl': 3600,
        'feature_flags': {'new_ui': True, 'beta_features': False}
    }

    for key, value in config_data.items():
        if not registry.set_config(key, value):
            print(f"FAIL: Could not set config key: {key}")
            exit(1)

    # Retrieve individual config
    db_url = registry.get_config('database_url')
    if db_url != config_data['database_url']:
        print(f"FAIL: Config mismatch for database_url: {db_url}")
        exit(1)

    # Retrieve all config
    all_config = registry.get_all_config()
    if 'database_url' in all_config and 'cache_ttl' in all_config:
        print(f"PASS: Config management successful - {len(all_config)} keys stored")
    else:
        print(f"FAIL: Missing keys in all_config: {all_config.keys()}")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_multiple_instances_registration() {
    echo -e "${YELLOW}Test 6: Register Multiple Service Instances${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    # Register 3 instances of the same service
    instances = []
    ports = [${MULTI_INSTANCE_PORT_1}, ${MULTI_INSTANCE_PORT_2}, ${MULTI_INSTANCE_PORT_3}]

    for i, port in enumerate(ports, 1):
        registry = ConsulRegistry(
            service_name='${TEST_SERVICE_NAME}-multi-{}'.format(i),
            service_port=port,
            consul_host='${CONSUL_HOST}',
            consul_port=${CONSUL_PORT},
            tags=['multi-instance', f'instance-{i}', 'preferred' if i == 1 else 'standard'],
            health_check_type='ttl'
        )
        if registry.register():
            instances.append(registry.service_id)
        else:
            print(f"FAIL: Could not register instance {i}")
            exit(1)

    print(f"PASS: Registered {len(instances)} service instances")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_load_balancing_strategies() {
    echo -e "${YELLOW}Test 7: Load Balancing Strategies${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    # First, register a service with "preferred" tag for testing
    registry = ConsulRegistry(
        service_name='lb-test-service',
        service_port=8888,
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT},
        tags=['preferred'],
        health_check_type='ttl'
    )
    registry.register()

    # Test different strategies
    strategies = ['health_weighted', 'random', 'round_robin', 'least_connections']
    results = {}

    for strategy in strategies:
        endpoint = registry.get_service_endpoint('lb-test-service', strategy=strategy)
        if endpoint:
            results[strategy] = endpoint
        else:
            print(f"FAIL: Strategy {strategy} returned None")
            exit(1)

    # Cleanup
    registry.deregister()

    print(f"PASS: All {len(results)} load balancing strategies work: {list(results.keys())}")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_service_discovery_with_fallback() {
    echo -e "${YELLOW}Test 8: Service Discovery with Fallback${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    registry = ConsulRegistry(
        service_name='${TEST_SERVICE_NAME}',
        service_port=${TEST_SERVICE_PORT},
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT}
    )

    # Test discovery of existing service
    url1 = registry.get_service_address('${TEST_SERVICE_NAME}', fallback_url='http://localhost:9999')
    if not url1 or 'http://' not in url1:
        print(f"FAIL: Could not discover existing service: {url1}")
        exit(1)

    # Test discovery of non-existent service with fallback
    url2 = registry.get_service_address('non-existent-service', fallback_url='http://localhost:7777')
    if url2 != 'http://localhost:7777':
        print(f"FAIL: Fallback not used for non-existent service: {url2}")
        exit(1)

    print("PASS: Service discovery with fallback works correctly")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_ttl_health_check_update() {
    echo -e "${YELLOW}Test 9: TTL Health Check Update${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
import time
try:
    registry = ConsulRegistry(
        service_name='ttl-health-test',
        service_port=7777,
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT},
        health_check_type='ttl'
    )

    if not registry.register():
        print("FAIL: Could not register service")
        exit(1)

    # Manually update TTL
    try:
        registry.consul.agent.check.ttl_pass(
            f"service:{registry.service_id}",
            "Manual health check update"
        )
        print("PASS: TTL health check updated successfully")
    except Exception as e:
        print(f"FAIL: Could not update TTL: {e}")
    finally:
        registry.deregister()
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_service_deregistration() {
    echo -e "${YELLOW}Test 10: Service Deregistration${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    registry = ConsulRegistry(
        service_name='dereg-test',
        service_port=6666,
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT},
        health_check_type='ttl'
    )

    # Register
    if not registry.register():
        print("FAIL: Could not register service")
        exit(1)

    # Verify registration
    services = registry.consul.agent.services()
    if registry.service_id not in services:
        print("FAIL: Service not found after registration")
        exit(1)

    # Deregister
    if not registry.deregister():
        print("FAIL: Deregistration returned False")
        exit(1)

    # Verify deregistration
    services = registry.consul.agent.services()
    if registry.service_id in services:
        print("FAIL: Service still exists after deregistration")
    else:
        print("PASS: Service deregistered successfully")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_infrastructure_service_discovery() {
    echo -e "${YELLOW}Test 11: Infrastructure Service Discovery Pattern${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    # Register mock infrastructure services with proper naming convention
    # Infrastructure services should use the '-grpc-service' suffix
    services = {
        'nats-grpc-service': 4222,
        'redis-grpc-service': 6379,
        'loki-grpc-service': 3100
    }

    registries = []
    for svc_name, svc_port in services.items():
        registry = ConsulRegistry(
            service_name=svc_name,
            service_port=svc_port,
            consul_host='${CONSUL_HOST}',
            consul_port=${CONSUL_PORT},
            tags=['infrastructure'],
            health_check_type='ttl'
        )
        if registry.register():
            registries.append(registry)
        else:
            print(f"FAIL: Could not register {svc_name}")
            exit(1)

    # Use ConsulRegistry discovery methods (ServiceDiscovery has been merged into ConsulRegistry)
    consul = registries[0]

    # Discover NATS
    nats_url = consul.get_nats_url()
    if not nats_url or ':4222' not in nats_url:
        print(f"FAIL: NATS discovery failed: {nats_url}")
        for r in registries:
            r.deregister()
        exit(1)

    # Discover Redis
    redis_url = consul.get_redis_url()
    if not redis_url or ':6379' not in redis_url:
        print(f"FAIL: Redis discovery failed: {redis_url}")
        for r in registries:
            r.deregister()
        exit(1)

    # Discover Loki
    loki_url = consul.get_loki_url()
    if not loki_url or ':3100' not in loki_url:
        print(f"FAIL: Loki discovery failed: {loki_url}")
        for r in registries:
            r.deregister()
        exit(1)

    # Cleanup
    for r in registries:
        r.deregister()

    print(f"PASS: Infrastructure service discovery successful - NATS, Redis, Loki")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_round_robin_load_balancing() {
    echo -e "${YELLOW}Test 12: Round-Robin Load Balancing Verification${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    # Register multiple instances
    registries = []
    for i in range(1, 4):
        registry = ConsulRegistry(
            service_name='rr-test',
            service_port=5000 + i,
            consul_host='${CONSUL_HOST}',
            consul_port=${CONSUL_PORT},
            tags=['round-robin-test'],
            health_check_type='ttl'
        )
        if registry.register():
            registries.append(registry)

    # Get endpoints using round-robin
    endpoints = []
    for _ in range(6):  # Get 6 endpoints (2 full rounds)
        endpoint = registries[0].get_service_endpoint('rr-test', strategy='round_robin')
        if endpoint:
            endpoints.append(endpoint)

    # Verify round-robin behavior (should cycle through all instances)
    unique_endpoints = set(endpoints)
    if len(unique_endpoints) == 3 and len(endpoints) == 6:
        print(f"PASS: Round-robin load balancing verified - {len(unique_endpoints)} unique endpoints")
    else:
        print(f"FAIL: Round-robin not working - unique: {len(unique_endpoints)}, total: {len(endpoints)}")

    # Cleanup
    for r in registries:
        r.deregister()
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_best_practices_validation() {
    echo -e "${YELLOW}Test 13: Best Practices Validation${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.consul_client import ConsulRegistry
try:
    issues = []

    # Best Practice 1: Service should have meaningful tags
    registry = ConsulRegistry(
        service_name='bp-test',
        service_port=8888,
        consul_host='${CONSUL_HOST}',
        consul_port=${CONSUL_PORT},
        tags=['version:1.0.0', 'environment:test', 'team:platform'],
        health_check_type='ttl'
    )
    registry.register()

    # Verify tags are set
    services = registry.consul.agent.services()
    if registry.service_id in services:
        tags = services[registry.service_id].get('Tags', [])
        if len(tags) < 2:
            issues.append("Service should have meaningful tags (version, env, team)")

    # Best Practice 2: TTL interval should be reasonable (not too short, not too long)
    if registry.ttl_interval < 10:
        issues.append("TTL interval too short (< 10s) - causes excessive traffic")
    if registry.ttl_interval > 60:
        issues.append("TTL interval too long (> 60s) - slow failure detection")

    # Best Practice 3: Deregister timeout should be reasonable
    deregister_seconds = int(registry.deregister_after.rstrip('s'))
    if deregister_seconds < 30:
        issues.append("Deregister timeout too short - may cause premature deregistration")

    # Cleanup
    registry.deregister()

    if len(issues) == 0:
        print("PASS: All best practices validated successfully")
    else:
        print(f"FAIL: Best practice violations: {', '.join(issues)}")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

# ========================================
# Main Test Runner
# ========================================

echo ""
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}     CONSUL SERVICE REGISTRY COMPREHENSIVE FUNCTIONAL TESTS${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Configuration:"
echo "  Consul Host: ${CONSUL_HOST}"
echo "  Consul Port: ${CONSUL_PORT}"
echo "  Test Service: ${TEST_SERVICE_NAME}"
echo ""

# Initial cleanup
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Connectivity
test_consul_connectivity
echo ""

# Basic Service Registration & Discovery
echo -e "${CYAN}--- Service Registration & Discovery ---${NC}"
test_service_registration_ttl
echo ""
test_service_discovery_single
echo ""
test_service_endpoint_retrieval
echo ""

# Configuration Management
echo -e "${CYAN}--- Configuration Management (KV Store) ---${NC}"
test_config_management
echo ""

# Multi-Instance Management
echo -e "${CYAN}--- Multi-Instance Service Management ---${NC}"
test_multiple_instances_registration
echo ""
test_load_balancing_strategies
echo ""
test_round_robin_load_balancing
echo ""

# Advanced Features
echo -e "${CYAN}--- Advanced Features ---${NC}"
test_service_discovery_with_fallback
echo ""
test_ttl_health_check_update
echo ""

# Infrastructure Service Discovery Pattern
echo -e "${CYAN}--- Infrastructure Service Discovery Pattern ---${NC}"
test_infrastructure_service_discovery
echo ""

# Cleanup & Best Practices
echo -e "${CYAN}--- Service Lifecycle & Best Practices ---${NC}"
test_service_deregistration
echo ""
test_best_practices_validation
echo ""

# Cleanup
cleanup

# Print summary
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}                         TEST SUMMARY${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo -e "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"

if [ ${TOTAL} -gt 0 ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", (${PASSED}/${TOTAL})*100}")
    echo "Success Rate: ${SUCCESS_RATE}%"
fi
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN} ALL TESTS PASSED!${NC}"
    echo -e "${GREEN}Consul client is ready for production use with service discovery${NC}"
    exit 0
else
    echo -e "${RED} SOME TESTS FAILED${NC}"
    exit 1
fi
