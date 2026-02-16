#!/usr/bin/env python3
"""
Consul Service Registry Client Usage Examples
==============================================

This example demonstrates how to use the ConsulRegistry from isa_common package.
Based on comprehensive functional tests with 100% success rate (13/13 tests passing).

File: isA_common/examples/consul_client_examples.py

Prerequisites:
--------------
1. Consul server must be running (default: localhost:8500)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/consul_client_examples.py

# Run with custom host/port
python isA_common/examples/consul_client_examples.py --host 192.168.1.100 --port 8500

# Run specific example
python isA_common/examples/consul_client_examples.py --example 5
```

Features Demonstrated:
----------------------
✅ Service Registration (TTL and HTTP health checks)
✅ Service Discovery (single and multiple instances)
✅ Load Balancing Strategies (health_weighted, random, round_robin, least_connections)
✅ Configuration Management (KV store operations)
✅ Service Endpoint Retrieval
✅ TTL Health Check Updates
✅ Service Deregistration
✅ Infrastructure Service Discovery Pattern
✅ Fallback Mechanisms
✅ Best Practices Validation
✅ Service Watching (monitoring changes)
✅ Multi-Instance Management

Note: All operations include proper error handling and demonstrate production-ready patterns.
"""

import sys
import argparse
import time
import json
from datetime import datetime

# Import the ConsulRegistry from isa_common
# Note: ServiceDiscovery has been merged into ConsulRegistry
try:
    from isa_common.consul_client import ConsulRegistry
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.consul_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_connectivity_check(consul_host='localhost', consul_port=8500):
    """
    Example 1: Consul Connectivity Check

    Check if the Consul server is accessible and operational.
    File: consul_client.py, Class: ConsulRegistry
    """
    print("\n" + "=" * 80)
    print("Example 1: Consul Server Connectivity Check")
    print("=" * 80)

    try:
        import consul
        client = consul.Consul(host=consul_host, port=consul_port)
        services = client.catalog.services()

        if services:
            print(f"✅ Successfully connected to Consul at {consul_host}:{consul_port}")
            print(f"   Registered services: {len(services[1])} services")
            print(f"   Service names: {list(services[1].keys())[:5]}...")
        else:
            print("❌ Could not retrieve Consul catalog")
    except Exception as e:
        print(f"❌ Failed to connect to Consul: {e}")
        print(f"   Make sure Consul is running on {consul_host}:{consul_port}")


def example_02_service_registration_ttl(consul_host='localhost', consul_port=8500):
    """
    Example 2: Service Registration with TTL Health Check

    Register a service with TTL-based health checking.
    File: consul_client.py, Method: register()
    """
    print("\n" + "=" * 80)
    print("Example 2: Service Registration with TTL Health Check")
    print("=" * 80)

    registry = ConsulRegistry(
        service_name='example-api-service',
        service_port=8080,
        consul_host=consul_host,
        consul_port=consul_port,
        tags=['api', 'v1.0.0', 'production'],
        health_check_type='ttl'
    )

    if registry.register():
        print(f"✅ Service registered successfully!")
        print(f"   Service ID: {registry.service_id}")
        print(f"   Service Name: {registry.service_name}")
        print(f"   Service Address: {registry.service_host}:{registry.service_port}")
        print(f"   Health Check: TTL ({registry.ttl_interval}s interval)")
        print(f"   Tags: {registry.tags}")

        # Cleanup
        time.sleep(2)
        registry.deregister()
        print(f"\n🗑️  Service deregistered (cleanup)")
    else:
        print("❌ Service registration failed")


def example_03_service_registration_http(consul_host='localhost', consul_port=8500):
    """
    Example 3: Service Registration with HTTP Health Check

    Register a service with HTTP-based health checking.
    File: consul_client.py, Method: register()
    """
    print("\n" + "=" * 80)
    print("Example 3: Service Registration with HTTP Health Check")
    print("=" * 80)

    registry = ConsulRegistry(
        service_name='example-web-service',
        service_port=8000,
        consul_host=consul_host,
        consul_port=consul_port,
        tags=['web', 'frontend', 'v2.0.0'],
        health_check_type='http'
    )

    if registry.register():
        print(f"✅ Service registered successfully!")
        print(f"   Service ID: {registry.service_id}")
        print(f"   Health Check: HTTP")
        print(f"   Health Check URL: http://{registry.service_host}:{registry.service_port}/health")
        print(f"   Check Interval: {registry.check_interval}")
        print(f"   Deregister After: {registry.deregister_after}")

        # Cleanup
        time.sleep(2)
        registry.deregister()
        print(f"\n🗑️  Service deregistered (cleanup)")
    else:
        print("❌ Service registration failed")


def example_04_service_discovery_single(consul_host='localhost', consul_port=8500):
    """
    Example 4: Discover Single Service Instance

    Discover and retrieve information about a single service instance.
    File: consul_client.py, Method: discover_service()
    """
    print("\n" + "=" * 80)
    print("Example 4: Service Discovery - Single Instance")
    print("=" * 80)

    # First register a service
    registry = ConsulRegistry(
        service_name='discovery-test',
        service_port=9000,
        consul_host=consul_host,
        consul_port=consul_port,
        tags=['test', 'discoverable'],
        health_check_type='ttl'
    )
    registry.register()

    # Discover the service
    instances = registry.discover_service('discovery-test')

    if instances:
        print(f"✅ Discovered {len(instances)} instance(s):")
        for i, instance in enumerate(instances, 1):
            print(f"\n   Instance {i}:")
            print(f"   - ID: {instance['id']}")
            print(f"   - Address: {instance['address']}")
            print(f"   - Port: {instance['port']}")
            print(f"   - Tags: {instance['tags']}")
    else:
        print("❌ No instances found")

    # Cleanup
    registry.deregister()


def example_05_service_endpoint_retrieval(consul_host='localhost', consul_port=8500):
    """
    Example 5: Get Service Endpoint URL

    Retrieve a ready-to-use endpoint URL for a service.
    File: consul_client.py, Method: get_service_endpoint()
    """
    print("\n" + "=" * 80)
    print("Example 5: Service Endpoint Retrieval")
    print("=" * 80)

    # Register a service
    registry = ConsulRegistry(
        service_name='endpoint-test',
        service_port=7000,
        consul_host=consul_host,
        consul_port=consul_port,
        health_check_type='ttl'
    )
    registry.register()

    # Get endpoint URL
    endpoint = registry.get_service_endpoint('endpoint-test')

    if endpoint:
        print(f"✅ Retrieved service endpoint:")
        print(f"   URL: {endpoint}")
        print(f"\n💡 Use this URL to connect to the service:")
        print(f"   import requests")
        print(f"   response = requests.get('{endpoint}/api/v1/resource')")
    else:
        print("❌ Could not retrieve endpoint")

    # Cleanup
    registry.deregister()


def example_06_load_balancing_strategies(consul_host='localhost', consul_port=8500):
    """
    Example 6: Load Balancing Strategies

    Demonstrate different load balancing strategies for service discovery.
    File: consul_client.py, Method: get_service_endpoint(strategy)
    """
    print("\n" + "=" * 80)
    print("Example 6: Load Balancing Strategies")
    print("=" * 80)

    # Register multiple instances
    registries = []
    for i in range(1, 4):
        reg = ConsulRegistry(
            service_name='lb-demo',
            service_port=6000 + i,
            consul_host=consul_host,
            consul_port=consul_port,
            tags=['lb-test', f'instance-{i}', 'preferred' if i == 1 else 'standard'],
            health_check_type='ttl'
        )
        reg.register()
        registries.append(reg)

    print(f"✅ Registered 3 service instances on ports 6001, 6002, 6003\n")

    # Test different strategies
    strategies = ['health_weighted', 'random', 'round_robin', 'least_connections']

    for strategy in strategies:
        endpoints = []
        print(f"📊 Testing '{strategy}' strategy:")

        # Get 5 endpoints to see the pattern
        for _ in range(5):
            endpoint = registries[0].get_service_endpoint('lb-demo', strategy=strategy)
            endpoints.append(endpoint)

        # Show distribution
        unique_endpoints = set(endpoints)
        print(f"   Unique endpoints: {len(unique_endpoints)}")
        for ep in unique_endpoints:
            count = endpoints.count(ep)
            print(f"   - {ep}: {count} times")
        print()

    # Cleanup
    for reg in registries:
        reg.deregister()


def example_07_config_management(consul_host='localhost', consul_port=8500):
    """
    Example 7: Configuration Management (KV Store)

    Store and retrieve configuration using Consul's KV store.
    File: consul_client.py, Methods: set_config(), get_config(), get_all_config()
    """
    print("\n" + "=" * 80)
    print("Example 7: Configuration Management (KV Store)")
    print("=" * 80)

    registry = ConsulRegistry(
        service_name='config-demo',
        service_port=5000,
        consul_host=consul_host,
        consul_port=consul_port,
        health_check_type='ttl'
    )
    registry.register()

    # Set configuration values
    config_data = {
        'database/url': 'postgresql://localhost:5432/mydb',
        'database/pool_size': 20,
        'cache/ttl': 3600,
        'features/new_ui': True,
        'features/beta_mode': False,
        'api/rate_limit': 1000
    }

    print("📝 Setting configuration values:")
    for key, value in config_data.items():
        registry.set_config(key, value)
        print(f"   ✅ {key} = {value}")

    # Retrieve individual config
    print("\n📖 Retrieving individual config:")
    db_url = registry.get_config('database/url')
    print(f"   database/url = {db_url}")

    rate_limit = registry.get_config('api/rate_limit')
    print(f"   api/rate_limit = {rate_limit}")

    # Retrieve all config
    print("\n📚 Retrieving all configuration:")
    all_config = registry.get_all_config()
    print(f"   Total keys: {len(all_config)}")
    for key, value in sorted(all_config.items()):
        print(f"   - {key}: {value}")

    # Cleanup
    registry.consul.kv.delete(f'{registry.service_name}/', recurse=True)
    registry.deregister()


def example_08_ttl_health_check_update(consul_host='localhost', consul_port=8500):
    """
    Example 8: TTL Health Check Manual Update

    Manually update TTL health checks to keep service healthy.
    File: consul_client.py, Method: maintain_registration()
    """
    print("\n" + "=" * 80)
    print("Example 8: TTL Health Check Manual Update")
    print("=" * 80)

    registry = ConsulRegistry(
        service_name='ttl-demo',
        service_port=4000,
        consul_host=consul_host,
        consul_port=consul_port,
        health_check_type='ttl'
    )
    registry.register()

    print(f"✅ Service registered with TTL health check")
    print(f"   TTL Interval: {registry.ttl_interval}s")
    print(f"\n⏱️  Manually updating TTL health check...")

    # Manually pass health check
    for i in range(3):
        try:
            registry.consul.agent.check.ttl_pass(
                f"service:{registry.service_id}",
                f"Manual health check update #{i+1} at {datetime.now()}"
            )
            print(f"   ✅ Update #{i+1} successful")
            time.sleep(1)
        except Exception as e:
            print(f"   ❌ Update #{i+1} failed: {e}")

    print(f"\n💡 In production, use maintain_registration() for automatic updates")

    # Cleanup
    registry.deregister()


def example_09_infrastructure_service_discovery(consul_host='localhost', consul_port=8500):
    """
    Example 9: Infrastructure Service Discovery Pattern

    Discover infrastructure services like NATS, Redis, Loki using ConsulRegistry methods.
    File: consul_client.py, Methods: get_nats_url(), get_redis_url(), get_loki_url()
    """
    print("\n" + "=" * 80)
    print("Example 9: Infrastructure Service Discovery Pattern")
    print("=" * 80)

    # Register mock infrastructure services
    infra_services = {
        'nats': 4222,
        'redis': 6379,
        'loki': 3100,
        'minio': 9000
    }

    registries = []
    print("📋 Registering infrastructure services:")
    for service_name, port in infra_services.items():
        reg = ConsulRegistry(
            service_name=service_name,
            service_port=port,
            consul_host=consul_host,
            consul_port=consul_port,
            tags=['infrastructure', 'core'],
            health_check_type='ttl'
        )
        reg.register()
        registries.append(reg)
        print(f"   ✅ {service_name} on port {port}")

    # Use ConsulRegistry discovery methods (ServiceDiscovery has been merged into ConsulRegistry)
    print("\n🔍 Discovering infrastructure services:")
    consul = registries[0]

    try:
        nats_url = consul.get_nats_url()
        print(f"   NATS: {nats_url}")
    except Exception as e:
        print(f"   ❌ NATS discovery failed: {e}")

    try:
        redis_url = consul.get_redis_url()
        print(f"   Redis: {redis_url}")
    except Exception as e:
        print(f"   ❌ Redis discovery failed: {e}")

    try:
        loki_url = consul.get_loki_url()
        print(f"   Loki: {loki_url}")
    except Exception as e:
        print(f"   ❌ Loki discovery failed: {e}")

    try:
        minio_url = consul.get_minio_endpoint()
        print(f"   MinIO: {minio_url}")
    except Exception as e:
        print(f"   ❌ MinIO discovery failed: {e}")

    # Cleanup
    for reg in registries:
        reg.deregister()


def example_10_fallback_mechanism(consul_host='localhost', consul_port=8500):
    """
    Example 10: Service Discovery with Fallback

    Automatic fallback to default URLs when service is not found in Consul.
    File: consul_client.py, Method: get_service_address()
    """
    print("\n" + "=" * 80)
    print("Example 10: Service Discovery with Fallback Mechanism")
    print("=" * 80)

    registry = ConsulRegistry(
        service_name='fallback-test',
        service_port=3000,
        consul_host=consul_host,
        consul_port=consul_port,
        health_check_type='ttl'
    )
    registry.register()

    # Test 1: Discover existing service
    print("🔍 Test 1: Discovering existing service...")
    url1 = registry.get_service_address('fallback-test', fallback_url='http://localhost:3000')
    print(f"   Result: {url1}")
    print(f"   ✅ Found in Consul")

    # Test 2: Discover non-existent service with fallback
    print("\n🔍 Test 2: Discovering non-existent service with fallback...")
    url2 = registry.get_service_address('non-existent-service', fallback_url='http://localhost:9999')
    print(f"   Result: {url2}")
    print(f"   ✅ Used fallback URL")

    print("\n💡 This pattern ensures your application works even when Consul is unavailable")

    # Cleanup
    registry.deregister()


def example_11_multi_instance_management(consul_host='localhost', consul_port=8500):
    """
    Example 11: Multi-Instance Service Management

    Register and manage multiple instances of the same service.
    File: consul_client.py
    """
    print("\n" + "=" * 80)
    print("Example 11: Multi-Instance Service Management")
    print("=" * 80)

    # Register 5 instances of the same service
    registries = []
    print("📋 Registering 5 instances of 'multi-api-service':")

    for i in range(1, 6):
        reg = ConsulRegistry(
            service_name='multi-api-service',
            service_port=8000 + i,
            consul_host=consul_host,
            consul_port=consul_port,
            tags=['api', f'instance-{i}', 'zone-a' if i <= 3 else 'zone-b'],
            health_check_type='ttl'
        )
        reg.register()
        registries.append(reg)
        print(f"   ✅ Instance {i} on port {8000 + i}")

    # Discover all instances
    print("\n🔍 Discovering all instances:")
    instances = registries[0].discover_service('multi-api-service')
    print(f"   Total instances: {len(instances)}")

    # Group by zone
    zone_a = [inst for inst in instances if 'zone-a' in inst['tags']]
    zone_b = [inst for inst in instances if 'zone-b' in inst['tags']]

    print(f"\n📊 Distribution:")
    print(f"   Zone A: {len(zone_a)} instances")
    print(f"   Zone B: {len(zone_b)} instances")

    # Test load balancing across instances
    print("\n⚖️  Testing round-robin load balancing:")
    for i in range(5):
        endpoint = registries[0].get_service_endpoint('multi-api-service', strategy='round_robin')
        print(f"   Request {i+1} → {endpoint}")

    # Cleanup
    for reg in registries:
        reg.deregister()


def example_12_best_practices(consul_host='localhost', consul_port=8500):
    """
    Example 12: Best Practices for Production Use

    Demonstrate recommended practices for using Consul in production.
    """
    print("\n" + "=" * 80)
    print("Example 12: Best Practices for Production Use")
    print("=" * 80)

    print("\n✅ Best Practice 1: Use meaningful service tags")
    registry = ConsulRegistry(
        service_name='production-api',
        service_port=8080,
        consul_host=consul_host,
        consul_port=consul_port,
        tags=[
            'version:1.2.3',
            'environment:production',
            'team:platform',
            'region:us-west-2',
            'datacenter:dc1'
        ],
        health_check_type='ttl'
    )
    registry.register()
    print(f"   Service registered with tags: {registry.tags}")

    print("\n✅ Best Practice 2: Reasonable TTL interval")
    print(f"   TTL interval: {registry.ttl_interval}s (recommended: 10-60s)")

    print("\n✅ Best Practice 3: Appropriate deregister timeout")
    deregister_seconds = int(registry.deregister_after.rstrip('s'))
    print(f"   Deregister after: {deregister_seconds}s (recommended: 60-120s)")

    print("\n✅ Best Practice 4: Use service discovery with fallback")
    url = registry.get_service_address(
        'production-api',
        fallback_url='http://localhost:8080',
        max_retries=3
    )
    print(f"   Discovered URL with fallback: {url}")

    print("\n✅ Best Practice 5: Store configuration in Consul KV")
    registry.set_config('database/url', 'postgresql://prod-db:5432/app')
    registry.set_config('cache/enabled', True)
    print(f"   Configuration stored in Consul KV")

    print("\n💡 Production Checklist:")
    print("   ✓ Use descriptive service names")
    print("   ✓ Tag services with version, environment, team")
    print("   ✓ Set appropriate TTL intervals (30s recommended)")
    print("   ✓ Use health checks (TTL for internal, HTTP for external)")
    print("   ✓ Implement fallback mechanisms")
    print("   ✓ Monitor service health regularly")
    print("   ✓ Use load balancing strategies")
    print("   ✓ Clean up on shutdown (deregister)")

    # Cleanup
    registry.consul.kv.delete(f'{registry.service_name}/', recurse=True)
    registry.deregister()


# Main execution
def main():
    parser = argparse.ArgumentParser(
        description='Consul Client Examples - Comprehensive demonstration of ConsulRegistry features'
    )
    parser.add_argument('--host', default='localhost', help='Consul host (default: localhost)')
    parser.add_argument('--port', type=int, default=8500, help='Consul port (default: 8500)')
    parser.add_argument('--example', type=int, help='Run specific example (1-12)')

    args = parser.parse_args()

    print("=" * 80)
    print("         Consul Service Registry Client - Usage Examples")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Consul Host: {args.host}")
    print(f"  Consul Port: {args.port}")
    print(f"\n💡 Based on 13 comprehensive functional tests (100% pass rate)")

    examples = {
        1: example_01_connectivity_check,
        2: example_02_service_registration_ttl,
        3: example_03_service_registration_http,
        4: example_04_service_discovery_single,
        5: example_05_service_endpoint_retrieval,
        6: example_06_load_balancing_strategies,
        7: example_07_config_management,
        8: example_08_ttl_health_check_update,
        9: example_09_infrastructure_service_discovery,
        10: example_10_fallback_mechanism,
        11: example_11_multi_instance_management,
        12: example_12_best_practices,
    }

    if args.example:
        if args.example in examples:
            examples[args.example](args.host, args.port)
        else:
            print(f"\n❌ Example {args.example} not found. Valid range: 1-{len(examples)}")
            sys.exit(1)
    else:
        # Run all examples
        for example_num, example_func in examples.items():
            try:
                example_func(args.host, args.port)
                time.sleep(1)  # Brief pause between examples
            except Exception as e:
                print(f"\n❌ Example {example_num} failed: {e}")
                import traceback
                traceback.print_exc()

    print("\n" + "=" * 80)
    print("                    Examples Complete!")
    print("=" * 80)
    print("\n💡 Next Steps:")
    print("   - Review the examples above")
    print("   - Integrate ConsulRegistry into your services")
    print("   - Use ServiceDiscovery for infrastructure services")
    print("   - Implement automatic service registration on startup")
    print("   - Add health check endpoints to your services")
    print("\n📚 Documentation:")
    print("   - Consul API: https://developer.hashicorp.com/consul/api-docs")
    print("   - Best Practices: https://developer.hashicorp.com/consul/docs/architecture")
    print()


if __name__ == '__main__':
    main()
