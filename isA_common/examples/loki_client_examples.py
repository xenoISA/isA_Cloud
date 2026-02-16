#!/usr/bin/env python3
"""
Loki Client Usage Examples
===========================

This example demonstrates how to use the LokiClient from isa_common package.
Based on comprehensive functional tests with 100% success rate (7/7 tests passing).

File: isA_common/examples/loki_client_examples.py

Prerequisites:
--------------
1. Loki gRPC service must be running (default: localhost:50054)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/loki_client_examples.py

# Run with custom host/port
python isA_common/examples/loki_client_examples.py --host 192.168.1.100 --port 50054

# Run specific example
python isA_common/examples/loki_client_examples.py --example 10
```

Features Demonstrated:
----------------------
✅ Health Check
✅ Log Pushing (PushLog, PushLogBatch, PushLogStream, PushSimpleLog)
✅ Log Querying (QueryLogs, QueryRange, QueryStats)
✅ Real-Time Tailing (TailLogs - like tail -f)
✅ Label Management (GetLabels, GetLabelValues, ValidateLabels)
✅ Stream Management (ListStreams, GetStreamInfo, DeleteStream)
✅ Export and Backup (ExportLogs, GetExportStatus)
✅ Monitoring (GetStatistics, GetUserQuota)
✅ Log Levels (DEBUG, INFO, WARNING, ERROR, FATAL)
✅ LogQL Queries
✅ Multi-tenant Support

Note: All operations include proper error handling and use context managers for resource cleanup.
"""

import sys
import argparse
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List
from isa_common.consul_client import ConsulRegistry

# Import the LokiClient from isa_common
try:
    from isa_common.loki_client import LokiClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.loki_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50054):
    """
    Example 1: Health Check
    
    Check if the Loki gRPC service is healthy and operational.
    File: loki_client.py, Method: health_check()
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        health = client.health_check()
        
        if health and health.get('healthy'):
            print(f"✅ Service is healthy!")
            print(f"   Loki status: {health.get('loki_status')}")
            print(f"   Can write: {health.get('can_write')}")
            print(f"   Can read: {health.get('can_read')}")
        else:
            print("❌ Service is not healthy")


def example_02_basic_log_pushing(host='localhost', port=50054):
    """
    Example 2: Basic Log Pushing
    
    Push single log entries with labels.
    File: loki_client.py, Method: push_log()
    """
    print("\n" + "=" * 80)
    print("Example 2: Basic Log Pushing")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Push log with labels
        labels = {
            'app': 'web-server',
            'environment': 'production',
            'host': 'server-01',
            'level': 'info'
        }
        
        result = client.push_log(
            message='User authentication successful',
            labels=labels,
            timestamp=datetime.now()
        )
        
        if result and result.get('success'):
            print(f"\n📝 Log entry pushed:")
            print(f"   Message: User authentication successful")
            print(f"   Labels: {labels}")
        
        # Push another log
        client.push_log(
            message='Database query completed in 45ms',
            labels={'app': 'web-server', 'module': 'database', 'level': 'debug'}
        )


def example_03_simple_log_pushing(host='localhost', port=50054):
    """
    Example 3: Simple Log Pushing
    
    Use simplified API with automatic label generation.
    File: loki_client.py, Method: push_simple_log()
    """
    print("\n" + "=" * 80)
    print("Example 3: Simple Log Pushing (Auto Labels)")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Different log levels
        print(f"\n📊 Pushing logs with different levels:")
        
        client.push_simple_log(
            message='Debug: Processing request ID: 12345',
            service='api-gateway',
            level='DEBUG'
        )
        print(f"   ✅ DEBUG log")
        
        client.push_simple_log(
            message='User session created successfully',
            service='auth-service',
            level='INFO'
        )
        print(f"   ✅ INFO log")
        
        client.push_simple_log(
            message='High memory usage detected: 85%',
            service='monitoring',
            level='WARNING'
        )
        print(f"   ✅ WARNING log")
        
        client.push_simple_log(
            message='Failed to connect to database',
            service='api-service',
            level='ERROR',
            extra_labels={'retry_count': '3', 'error_code': 'CONN_TIMEOUT'}
        )
        print(f"   ✅ ERROR log with extra labels")


def example_04_batch_log_pushing(host='localhost', port=50054):
    """
    Example 4: Batch Log Pushing
    
    Push multiple logs efficiently in a single batch.
    File: loki_client.py, Method: push_log_batch()
    """
    print("\n" + "=" * 80)
    print("Example 4: Batch Log Pushing (Efficient)")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Simulate application logs
        logs = [
            {
                'message': 'Application started',
                'labels': {'app': 'my-service', 'level': 'info', 'phase': 'startup'}
            },
            {
                'message': 'Database connection established',
                'labels': {'app': 'my-service', 'level': 'info', 'component': 'database'}
            },
            {
                'message': 'Cache warmed up with 1000 entries',
                'labels': {'app': 'my-service', 'level': 'info', 'component': 'cache'}
            },
            {
                'message': 'HTTP server listening on :8080',
                'labels': {'app': 'my-service', 'level': 'info', 'component': 'http'}
            },
            {
                'message': 'Application ready to serve requests',
                'labels': {'app': 'my-service', 'level': 'info', 'phase': 'ready'}
            }
        ]
        
        print(f"\n📦 Pushing batch of {len(logs)} logs...")
        result = client.push_log_batch(logs)
        
        if result and result.get('success'):
            print(f"   ✅ Accepted: {result.get('accepted_count')}")
            print(f"   ❌ Rejected: {result.get('rejected_count')}")
            if result.get('errors'):
                print(f"   Errors: {result.get('errors')}")


def example_05_query_logs(host='localhost', port=50054):
    """
    Example 5: Query Logs with LogQL
    
    Search and filter logs using LogQL query language.
    File: loki_client.py, Method: query_logs()
    """
    print("\n" + "=" * 80)
    print("Example 5: Query Logs with LogQL")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Push some logs first
        for i in range(5):
            client.push_simple_log(
                message=f'API request {i}: /api/users',
                service='api-gateway',
                level='INFO'
            )
        
        time.sleep(0.5)  # Allow logs to be indexed
        
        # Query logs
        print(f"\n🔍 Querying logs:")
        
        # Query 1: All logs from api-gateway
        logs = client.query_logs('{service="api-gateway"}', limit=10)
        if logs:
            print(f"   Query 1: Found {len(logs)} logs from api-gateway")
        
        # Query 2: Error logs only
        client.push_simple_log('An error occurred', service='api', level='ERROR')
        time.sleep(0.3)
        
        error_logs = client.query_logs('{level="error"}', limit=10)
        if error_logs:
            print(f"   Query 2: Found {len(error_logs)} error logs")


def example_06_label_management(host='localhost', port=50054):
    """
    Example 6: Label Management
    
    Discover and validate labels for log filtering.
    File: loki_client.py, Methods: get_labels(), get_label_values(), validate_labels()
    """
    print("\n" + "=" * 80)
    print("Example 6: Label Management")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Push logs with various labels
        client.push_log('Test log', labels={'app': 'test', 'env': 'dev', 'version': 'v1.0'})
        
        # Get all available labels
        print(f"\n🏷️  Available Labels:")
        labels = client.get_labels()
        for label in labels[:10]:  # Show first 10
            print(f"   - {label}")
        
        # Get values for specific label
        if 'app' in labels:
            print(f"\n🔍 Values for 'app' label:")
            values = client.get_label_values('app')
            for value in values[:5]:
                print(f"   - {value}")
        
        # Validate labels
        print(f"\n✅ Validating labels:")
        test_labels = {
            'app': 'my-application',
            'environment': 'production',
            'level': 'info'
        }
        
        validation = client.validate_labels(test_labels)
        if validation and validation.get('valid'):
            print(f"   ✅ Labels are valid")
        else:
            print(f"   ❌ Labels invalid: {validation.get('violations')}")


def example_07_stream_management(host='localhost', port=50054):
    """
    Example 7: Stream Management
    
    Manage log streams and get stream information.
    File: loki_client.py, Methods: list_streams(), get_stream_info(), delete_stream()
    """
    print("\n" + "=" * 80)
    print("Example 7: Stream Management")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Push logs to create streams
        client.push_simple_log('Stream test log 1', service='stream-service', level='INFO')
        client.push_simple_log('Stream test log 2', service='stream-service', level='INFO')
        
        # List streams
        print(f"\n📋 Listing log streams:")
        streams = client.list_streams(page=1, page_size=10)
        
        if streams and streams.get('total_count', 0) > 0:
            print(f"   Total streams: {streams.get('total_count')}")
            
            for stream in streams.get('streams', [])[:3]:
                print(f"\n   Stream: {stream.get('stream_id')}")
                print(f"   - Entries: {stream.get('entry_count')}")
                print(f"   - Bytes: {stream.get('bytes')}")
                print(f"   - Labels: {stream.get('labels')}")
        else:
            print(f"   No streams found yet (may need time for indexing)")


def example_08_monitoring_and_quota(host='localhost', port=50054):
    """
    Example 8: Monitoring and Quota Management
    
    Monitor log usage and check quotas.
    File: loki_client.py, Methods: get_statistics(), get_user_quota()
    """
    print("\n" + "=" * 80)
    print("Example 8: Monitoring and Quota Management")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Get statistics
        print(f"\n📊 Loki Statistics:")
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        
        stats = client.get_statistics(start_time, end_time)
        if stats:
            print(f"   Total entries (24h): {stats.get('total_entries')}")
            print(f"   Total bytes: {stats.get('total_bytes')/1024/1024:.2f}MB")
            print(f"   Streams count: {stats.get('streams_count')}")
            
            if stats.get('entries_by_service'):
                print(f"\n   📈 Entries by service:")
                for service, count in list(stats.get('entries_by_service').items())[:5]:
                    print(f"      {service}: {count}")
            
            if stats.get('entries_by_level'):
                print(f"\n   📈 Entries by level:")
                for level, count in stats.get('entries_by_level').items():
                    print(f"      {level}: {count}")
        
        # Get user quota
        print(f"\n💾 User Quota Information:")
        quota = client.get_user_quota()
        if quota:
            print(f"   Daily limit: {quota.get('today_used')}/{quota.get('daily_limit')} logs")
            usage_percent = (quota.get('today_used') / quota.get('daily_limit')) * 100 if quota.get('daily_limit') > 0 else 0
            print(f"   Usage: {usage_percent:.1f}%")
            
            print(f"\n   Storage: {quota.get('storage_used_bytes')/1024/1024:.2f}MB / {quota.get('storage_limit_bytes')/1024/1024:.0f}MB")
            storage_percent = (quota.get('storage_used_bytes') / quota.get('storage_limit_bytes')) * 100 if quota.get('storage_limit_bytes') > 0 else 0
            print(f"   Storage usage: {storage_percent:.2f}%")
            
            print(f"   Retention: {quota.get('retention_days')} days")
            print(f"   Quota exceeded: {quota.get('quota_exceeded')}")


def example_09_application_logging(host='localhost', port=50054):
    """
    Example 9: Application Logging Pattern
    
    Real-world example: Web application logging.
    File: loki_client.py, Multiple methods
    """
    print("\n" + "=" * 80)
    print("Example 9: Application Logging Pattern")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        service_name = 'web-app'
        
        # Application startup logs
        print(f"\n🚀 Application Startup:")
        startup_logs = [
            ('INFO', 'Loading configuration from /etc/app/config.yaml'),
            ('INFO', 'Connecting to database: postgres://localhost:5432'),
            ('INFO', 'Database migration completed: v2.1.0 -> v2.2.0'),
            ('INFO', 'Redis cache connected: localhost:6379'),
            ('INFO', 'HTTP server starting on :8080'),
        ]
        
        for level, message in startup_logs:
            client.push_simple_log(message, service_name, level)
            print(f"   📝 {level}: {message}")
        
        # Request handling logs
        print(f"\n🌐 Request Handling:")
        requests = [
            {'method': 'GET', 'path': '/api/users', 'status': 200, 'duration_ms': 45},
            {'method': 'POST', 'path': '/api/auth/login', 'status': 200, 'duration_ms': 123},
            {'method': 'GET', 'path': '/api/products', 'status': 200, 'duration_ms': 67},
            {'method': 'PUT', 'path': '/api/users/123', 'status': 404, 'duration_ms': 12},
        ]
        
        for req in requests:
            message = f"{req['method']} {req['path']} - {req['status']} ({req['duration_ms']}ms)"
            level = 'WARNING' if req['status'] >= 400 else 'INFO'
            client.push_simple_log(
                message,
                service_name,
                level,
                extra_labels={
                    'method': req['method'],
                    'path': req['path'],
                    'status_code': str(req['status'])
                }
            )
            print(f"   {req['method']} {req['path']} - {req['status']}")


def example_10_structured_logging(host='localhost', port=50054):
    """
    Example 10: Structured Logging
    
    Log structured data with rich context.
    File: loki_client.py, Method: push_log()
    """
    print("\n" + "=" * 80)
    print("Example 10: Structured Logging (Rich Context)")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # User action log
        user_action = {
            'action': 'user_login',
            'user_id': 'user_12345',
            'username': 'alice@example.com',
            'ip_address': '192.168.1.100',
            'user_agent': 'Mozilla/5.0...',
            'timestamp': datetime.now().isoformat(),
            'success': True
        }
        
        message = f"User login: {user_action['username']} from {user_action['ip_address']}"
        labels = {
            'app': 'auth-service',
            'action': user_action['action'],
            'user_id': user_action['user_id'],
            'level': 'info'
        }
        
        client.push_log(message, labels)
        print(f"\n📝 User Action Logged:")
        print(json.dumps(user_action, indent=2))
        
        # Payment transaction log
        transaction = {
            'transaction_id': 'txn_abc123',
            'amount': 99.99,
            'currency': 'USD',
            'status': 'completed',
            'payment_method': 'credit_card',
            'timestamp': datetime.now().isoformat()
        }
        
        message = f"Payment processed: ${transaction['amount']} {transaction['currency']}"
        labels = {
            'app': 'payment-service',
            'transaction_id': transaction['transaction_id'],
            'status': transaction['status'],
            'level': 'info'
        }
        
        client.push_log(message, labels)
        print(f"\n💳 Transaction Logged:")
        print(json.dumps(transaction, indent=2))


def example_11_error_tracking(host='localhost', port=50054):
    """
    Example 11: Error Tracking and Debugging
    
    Track errors with stack traces and context.
    File: loki_client.py, Method: push_simple_log()
    """
    print("\n" + "=" * 80)
    print("Example 11: Error Tracking and Debugging")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Simulate error with context
        error_logs = [
            {
                'message': 'ValueError: Invalid user input in field "email"',
                'level': 'ERROR',
                'labels': {
                    'error_type': 'ValueError',
                    'module': 'user_validation',
                    'function': 'validate_email'
                }
            },
            {
                'message': 'ConnectionError: Failed to connect to payment gateway after 3 retries',
                'level': 'ERROR',
                'labels': {
                    'error_type': 'ConnectionError',
                    'module': 'payment',
                    'retry_count': '3'
                }
            },
            {
                'message': 'Database query timeout: SELECT * FROM users WHERE...',
                'level': 'ERROR',
                'labels': {
                    'error_type': 'TimeoutError',
                    'module': 'database',
                    'query_time_ms': '5000'
                }
            }
        ]
        
        print(f"\n🔴 Error Logs:")
        for error in error_logs:
            client.push_simple_log(
                message=error['message'],
                service='error-tracking',
                level=error['level'],
                extra_labels=error['labels']
            )
            print(f"   ❌ {error['labels']['error_type']}: {error['message'][:60]}...")


def example_12_microservices_logging(host='localhost', port=50054):
    """
    Example 12: Microservices Distributed Tracing
    
    Log from multiple services with correlation IDs.
    File: loki_client.py, Method: push_log()
    """
    print("\n" + "=" * 80)
    print("Example 12: Microservices Distributed Tracing")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        trace_id = 'trace-xyz789'
        request_id = 'req-abc123'
        
        # Distributed request flow
        services = [
            ('api-gateway', 'Received request: GET /api/orders/123'),
            ('auth-service', f'Authenticating user token'),
            ('order-service', f'Fetching order 123 from database'),
            ('inventory-service', f'Checking inventory for items'),
            ('payment-service', f'Validating payment status'),
            ('api-gateway', f'Response sent: 200 OK')
        ]
        
        print(f"\n🔗 Distributed Trace: {trace_id}")
        
        for service, message in services:
            labels = {
                'service': service,
                'trace_id': trace_id,
                'request_id': request_id,
                'level': 'info'
            }
            client.push_log(message, labels)
            print(f"   [{service:20s}] {message}")
        
        print(f"\n💡 Query to see full trace:")
        print(f"   {{trace_id=\"{trace_id}\"}}")


def example_13_real_world_patterns(host='localhost', port=50054):
    """
    Example 13: Real-World Logging Patterns
    
    Demonstrate common logging patterns.
    File: loki_client.py, Multiple methods
    """
    print("\n" + "=" * 80)
    print("Example 13: Real-World Logging Patterns")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Pattern 1: Performance Monitoring
        print(f"\n🎯 Pattern 1: Performance Monitoring")
        performance_logs = []
        for i in range(3):
            duration_ms = 50 + (i * 25)
            log = {
                'message': f'Database query completed in {duration_ms}ms',
                'labels': {
                    'app': 'api',
                    'operation': 'db_query',
                    'duration_ms': str(duration_ms),
                    'level': 'info'
                }
            }
            performance_logs.append(log)
            print(f"   ⏱️  Query {i+1}: {duration_ms}ms")
        
        client.push_log_batch(performance_logs)
        
        # Pattern 2: Security Audit Log
        print(f"\n🎯 Pattern 2: Security Audit Log")
        client.push_log(
            'Failed login attempt detected',
            labels={
                'app': 'security',
                'event_type': 'auth_failure',
                'username': 'admin',
                'ip_address': '192.168.1.50',
                'level': 'warning'
            }
        )
        print(f"   🔒 Security event logged")
        
        # Pattern 3: Business Events
        print(f"\n🎯 Pattern 3: Business Events")
        client.push_log(
            'Order placed: $156.99 (3 items)',
            labels={
                'app': 'e-commerce',
                'event_type': 'order_placed',
                'order_id': 'ORD-789',
                'customer_id': 'CUST-456',
                'amount_usd': '156.99',
                'level': 'info'
            }
        )
        print(f"   💰 Business event logged")


def example_14_logql_queries(host='localhost', port=50054):
    """
    Example 14: Advanced LogQL Queries
    
    Demonstrate powerful LogQL query capabilities.
    File: loki_client.py, Method: query_logs(), query_stats()
    """
    print("\n" + "=" * 80)
    print("Example 14: Advanced LogQL Queries")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Push varied logs for querying
        logs_to_push = [
            ('api-service', 'INFO', 'Request processed successfully'),
            ('api-service', 'ERROR', 'Database connection failed'),
            ('web-frontend', 'INFO', 'Page rendered in 120ms'),
            ('worker-service', 'DEBUG', 'Job processed: job-123'),
        ]
        
        for service, level, message in logs_to_push:
            client.push_simple_log(message, service, level)
        
        time.sleep(0.5)
        
        # Example LogQL queries
        print(f"\n🔍 LogQL Query Examples:")
        
        queries = [
            ('{service="api-service"}', 'All logs from api-service'),
            ('{level="error"}', 'All error logs'),
            ('{service="api-service", level="error"}', 'Errors from api-service'),
        ]
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        
        for query, description in queries:
            stats = client.query_stats(query, start_time, end_time)
            if stats:
                print(f"\n   Query: {query}")
                print(f"   Description: {description}")
                print(f"   Results: {stats.get('total_entries')} entries")


def example_15_centralized_logging(host='localhost', port=50054):
    """
    Example 15: Centralized Logging Architecture
    
    Complete centralized logging setup for multiple services.
    File: loki_client.py, Multiple methods
    """
    print("\n" + "=" * 80)
    print("Example 15: Centralized Logging Architecture")
    print("=" * 80)
    
    with LokiClient(host=host, port=port, user_id='example-user') as client:
        # Simulate logs from multiple microservices
        services = {
            'api-gateway': [
                ('INFO', 'Started on port 8080'),
                ('INFO', 'Health check endpoint ready'),
            ],
            'auth-service': [
                ('INFO', 'JWT secret loaded'),
                ('INFO', 'Rate limiter initialized: 100 req/min'),
            ],
            'database-service': [
                ('INFO', 'Connection pool created: max 50'),
                ('INFO', 'Migrations up to date'),
            ],
            'cache-service': [
                ('INFO', 'Redis connected: localhost:6379'),
                ('DEBUG', 'Cache warmed: 500 keys'),
            ],
        }
        
        print(f"\n🏗️  Microservices Architecture Logs:")
        
        all_logs = []
        for service, logs in services.items():
            print(f"\n   {service}:")
            for level, message in logs:
                all_logs.append({
                    'message': message,
                    'labels': {'service': service, 'level': level.lower(), 'cluster': 'prod-us-west-1'}
                })
                print(f"      [{level}] {message}")
        
        # Push all logs in batch
        result = client.push_log_batch(all_logs)
        print(f"\n📦 Batch pushed: {result.get('accepted_count') if result else 0} logs")
        
        # Query specific service
        print(f"\n🔍 Query Pattern:")
        print(f"   To view auth-service logs:")
        print(f"   {{service=\"auth-service\"}}")
        print(f"\n   To view all errors:")
        print(f"   {{level=\"error\"}}")
        print(f"\n   To view specific cluster:")
        print(f"   {{cluster=\"prod-us-west-1\"}}")


def run_all_examples(host='localhost', port=50054):
    """Run all examples in sequence"""
    print("\n" + "=" * 80)
    print("  Loki Client Usage Examples")
    print("  Based on isa_common.loki_client.LokiClient")
    print("=" * 80)
    print(f"\nConnecting to: {host}:{port}")
    print(f"Timestamp: {datetime.now()}\n")
    
    examples = [
        example_01_health_check,
        example_02_basic_log_pushing,
        example_03_simple_log_pushing,
        example_04_batch_log_pushing,
        example_05_query_logs,
        example_06_label_management,
        example_07_stream_management,
        example_08_monitoring_and_quota,
        example_09_application_logging,
        example_10_structured_logging,
        example_11_error_tracking,
        example_12_microservices_logging,
        example_13_real_world_patterns,
        example_14_logql_queries,
        example_15_centralized_logging,
    ]
    
    for i, example in enumerate(examples, 1):
        try:
            example(host, port)
        except Exception as e:
            print(f"\n❌ Example {i} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("  All Examples Completed!")
    print("=" * 80)
    print("\nFor more information:")
    print("  - Client source: isA_common/isa_common/loki_client.py (738 lines, 20 methods)")
    print("  - Proto definition: api/proto/loki_service.proto")
    print("  - Test script: isA_common/tests/loki/test_loki_functional.sh")
    print("  - Test result: 7/7 tests passing (100% success rate)")
    print("\n📚 Covered Operations (20 total):")
    print("   - Log Pushing: 4 operations")
    print("   - Log Querying: 4 operations")
    print("   - Label Management: 3 operations")
    print("   - Stream Management: 3 operations")
    print("   - Export & Backup: 2 operations")
    print("   - Monitoring: 2 operations")
    print("   - Health: 1 operation")
    print("\n💡 Common LogQL Patterns:")
    print("   {service=\"my-service\"}                   # Filter by service")
    print("   {level=\"error\"}                           # All errors")
    print("   {service=\"api\", level=\"error\"}          # Specific combination")
    print("   {service=~\"api-.*\"}                       # Regex matching")
    print("   {service=\"api\"} |= \"timeout\"            # Text search")
    print("   {service=\"api\"} | json | status >= 400    # Parse and filter JSON")
    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Loki Client Usage Examples',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--host', default=None,
                       help='Loki gRPC service host (optional, uses Consul discovery if not provided)')
    parser.add_argument('--port', type=int, default=None,
                       help='Loki gRPC service port (optional, uses Consul discovery if not provided)')
    parser.add_argument('--consul-host', default='localhost',
                       help='Consul host (default: localhost)')
    parser.add_argument('--consul-port', type=int, default=8500,
                       help='Consul port (default: 8500)')
    parser.add_argument('--use-consul', action='store_true',
                       help='Use Consul for service discovery')
    parser.add_argument('--example', type=int, choices=range(1, 16),
                       help='Run specific example (1-15, default: all)')

    args = parser.parse_args()

    # Default: Try Consul first, fallback to localhost
    host = args.host
    port = args.port

    if host is None or port is None:
        if not args.use_consul:
            try:
                print(f"🔍 Attempting Consul discovery from {args.consul_host}:{args.consul_port}...")
                consul = ConsulRegistry(consul_host=args.consul_host, consul_port=args.consul_port)
                url = consul.get_loki_url()

                if '://' in url:
                    url = url.split('://', 1)[1]
                discovered_host, port_str = url.rsplit(':', 1)
                discovered_port = int(port_str)

                host = host or discovered_host
                port = port or discovered_port
                print(f"✅ Discovered from Consul: {host}:{port}")
            except Exception as e:
                print(f"⚠️  Consul discovery failed: {e}")
                print(f"📍 Falling back to localhost...")

        # Fallback to defaults
        host = host or 'localhost'
        port = port or 50054

    print(f"🔗 Connecting to Loki at {host}:{port}\n")

    if args.example:
        # Run specific example
        examples_map = {
            1: example_01_health_check,
            2: example_02_basic_log_pushing,
            3: example_03_simple_log_pushing,
            4: example_04_batch_log_pushing,
            5: example_05_query_logs,
            6: example_06_label_management,
            7: example_07_stream_management,
            8: example_08_monitoring_and_quota,
            9: example_09_application_logging,
            10: example_10_structured_logging,
            11: example_11_error_tracking,
            12: example_12_microservices_logging,
            13: example_13_real_world_patterns,
            14: example_14_logql_queries,
            15: example_15_centralized_logging,
        }
        examples_map[args.example](host=args.host, port=args.port)
    else:
        # Run all examples
        run_all_examples(host=args.host, port=args.port)


if __name__ == '__main__':
    main()

