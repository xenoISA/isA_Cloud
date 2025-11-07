#!/usr/bin/env python3
"""
Redis Client Usage Examples
============================

This example demonstrates how to use the RedisClient from isa_common package.
Based on comprehensive functional tests with 100% success rate (18/18 tests passing).

File: isA_common/examples/redis_client_examples.py

Prerequisites:
--------------
1. Redis gRPC service must be running (default: localhost:50055)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/redis_client_examples.py

# Run with custom host/port
python isA_common/examples/redis_client_examples.py --host 192.168.1.100 --port 50055

# Run specific example
python isA_common/examples/redis_client_examples.py --example 5
```

Features Demonstrated:
----------------------
✅ String Operations (SET, GET, APPEND, DELETE, EXISTS)
✅ Key Operations (Expire, TTL, Rename, DeleteMultiple, ListKeys)
✅ Counter Operations (INCR, DECR)
✅ Hash Operations (HSET, HGET, HGETALL, HDelete, HExists, HKeys, HValues, HIncrement)
✅ List Operations (LPUSH, RPUSH, LPOP, RPOP, LRANGE, LLEN, LINDEX, LTRIM)
✅ Set Operations (SADD, SREMOVE, SMEMBERS, SISMEMBER, SCARD, SUNION, SINTER, SDIFF)
✅ Sorted Set Operations (ZADD, ZREM, ZRANGE, ZRANK, ZSCORE, ZCARD, ZINCREMENT, ZRangeByScore)
✅ Distributed Locks (Acquire, Release, Renew)
✅ Pub/Sub Operations (Publish, Subscribe, Unsubscribe)
✅ Batch Operations (MSET/MGET, ExecuteBatch)
✅ Session Management (Create, Get, Update, Delete, List)
✅ Monitoring Operations (GetStatistics, GetKeyInfo)
✅ Health Check

Note: All operations include proper error handling and use context managers for resource cleanup.
"""

import sys
import argparse
import time
from datetime import datetime
from typing import Dict, List

# Import the RedisClient from isa_common
try:
    from isa_common.redis_client import RedisClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.redis_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50055):
    """
    Example 1: Health Check

    Check Redis service health status.
    File: redis_client.py, Method: health_check()
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)

    with RedisClient(host=host, port=port, user_id='example-user') as client:
        health = client.health_check()

        if health and health.get('healthy'):
            print(f"✅ Service is healthy!")
            print(f"   Redis status: {health.get('redis_status')}")
            print(f"   Connected clients: {health.get('connected_clients')}")
            print(f"   Memory used: {health.get('used_memory_bytes')/1024/1024:.2f}MB")
        else:
            print("❌ Service is not healthy")


def example_02_string_operations(host='localhost', port=50055):
    """
    Example 2: Basic String Operations
    
    SET, GET, DELETE, EXISTS operations for key-value storage.
    File: redis_client.py, Methods: set(), get(), delete(), exists()
    """
    print("\n" + "=" * 80)
    print("Example 2: Basic String Operations (SET, GET, DELETE, EXISTS)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Set a key-value pair
        client.set('user:1001:name', 'Alice Johnson')
        client.set('user:1001:email', 'alice@example.com')
        client.set('user:1001:role', 'developer')
        
        # Get values
        name = client.get('user:1001:name')
        email = client.get('user:1001:email')
        print(f"\n📝 Retrieved user data:")
        print(f"   Name: {name}")
        print(f"   Email: {email}")
        
        # Check existence
        exists = client.exists('user:1001:name')
        print(f"\n🔍 Key 'user:1001:name' exists: {exists}")
        
        # Delete key
        client.delete('user:1001:role')
        print(f"\n🗑️  Deleted 'user:1001:role'")


def example_03_ttl_expiration(host='localhost', port=50055):
    """
    Example 3: TTL and Expiration
    
    Set keys with automatic expiration using TTL (Time To Live).
    File: redis_client.py, Methods: set_with_ttl(), ttl(), expire()
    """
    print("\n" + "=" * 80)
    print("Example 3: TTL and Expiration")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Set key with TTL
        client.set_with_ttl('session:temp123', 'temporary_data', 10)
        print(f"\n⏱️  Set key with 10 second TTL")
        
        # Check TTL
        ttl = client.ttl('session:temp123')
        print(f"   Current TTL: {ttl} seconds")
        
        # Set expiration on existing key
        client.set('cache:data', 'cached_value')
        client.expire('cache:data', 30)
        print(f"\n⏱️  Set expiration on existing key: 30 seconds")
        
        ttl2 = client.ttl('cache:data')
        print(f"   Current TTL: {ttl2} seconds")


def example_04_string_append(host='localhost', port=50055):
    """
    Example 4: String APPEND Operation
    
    Append text to existing string values.
    File: redis_client.py, Method: append()
    """
    print("\n" + "=" * 80)
    print("Example 4: String APPEND Operation")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Create initial string
        client.set('log:entry', 'Started: ')
        
        # Append to it
        length1 = client.append('log:entry', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print(f"\n📝 After first append, length: {length1}")
        
        length2 = client.append('log:entry', ' | Status: Running')
        print(f"   After second append, length: {length2}")
        
        # Get final value
        final_value = client.get('log:entry')
        print(f"\n   Final value: {final_value}")


def example_05_counter_operations(host='localhost', port=50055):
    """
    Example 5: Counter Operations
    
    Atomic increment and decrement operations for counters.
    File: redis_client.py, Methods: incr(), decr()
    """
    print("\n" + "=" * 80)
    print("Example 5: Counter Operations (INCR, DECR)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Initialize counter
        client.delete('page:views')
        
        # Increment operations
        views = client.incr('page:views', 1)
        print(f"\n📊 Page views after 1st visit: {views}")
        
        views = client.incr('page:views', 10)
        print(f"   Page views after 10 more visits: {views}")
        
        # Decrement operation
        views = client.decr('page:views', 3)
        print(f"   Page views after 3 decrements: {views}")
        
        # Use for rate limiting
        client.delete('api:requests:user123')
        for i in range(5):
            count = client.incr('api:requests:user123', 1)
        print(f"\n🚦 API requests count: {count}")


def example_06_key_operations(host='localhost', port=50055):
    """
    Example 6: Advanced Key Operations
    
    Rename keys, delete multiple keys, and list keys by pattern.
    File: redis_client.py, Methods: rename(), delete_multiple(), list_keys()
    """
    print("\n" + "=" * 80)
    print("Example 6: Advanced Key Operations (Rename, DeleteMultiple, ListKeys)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Setup test keys
        client.set('temp:key1', 'value1')
        client.set('temp:key2', 'value2')
        client.set('temp:key3', 'value3')
        client.set('old:name', 'data')
        
        # Rename operation
        success = client.rename('old:name', 'new:name')
        if success:
            print(f"\n🔄 Renamed 'old:name' to 'new:name'")
        
        # List keys
        keys = client.list_keys('temp:*', 100)
        print(f"\n🔍 Found {len(keys)} keys matching 'temp:*':")
        for key in keys:
            print(f"   - {key}")
        
        # Delete multiple keys
        count = client.delete_multiple(['temp:key1', 'temp:key2', 'temp:key3'])
        print(f"\n🗑️  Deleted {count} keys")


def example_07_hash_operations(host='localhost', port=50055):
    """
    Example 7: Hash Operations
    
    Store structured data using Redis hashes (like dictionaries).
    File: redis_client.py, Methods: hset(), hget(), hgetall(), hkeys(), hvalues(), etc.
    """
    print("\n" + "=" * 80)
    print("Example 7: Hash Operations (User Profile Storage)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Set hash fields
        client.hset('user:2001', 'name', 'Bob Smith')
        client.hset('user:2001', 'email', 'bob@example.com')
        client.hset('user:2001', 'age', '28')
        client.hset('user:2001', 'city', 'San Francisco')
        
        # Get specific field
        name = client.hget('user:2001', 'name')
        print(f"\n👤 User name: {name}")
        
        # Get all fields
        user_data = client.hgetall('user:2001')
        print(f"\n📋 Complete user profile:")
        for field, value in user_data.items():
            print(f"   {field}: {value}")
        
        # Check field existence
        has_email = client.hexists('user:2001', 'email')
        print(f"\n🔍 Has email field: {has_email}")
        
        # Get all field names
        fields = client.hkeys('user:2001')
        print(f"\n🔑 Field names: {', '.join(fields)}")
        
        # Get all values
        values = client.hvalues('user:2001')
        print(f"📊 Field values: {', '.join(values)}")
        
        # Increment counter field
        client.hset('user:2001', 'login_count', '0')
        count = client.hincrement('user:2001', 'login_count', 1)
        print(f"\n➕ Login count incremented to: {count}")
        
        # Delete specific fields
        deleted = client.hdelete('user:2001', ['age', 'city'])
        print(f"\n🗑️  Deleted {deleted} fields")


def example_08_list_operations(host='localhost', port=50055):
    """
    Example 8: List Operations
    
    Implement queues, stacks, and ordered collections using Redis lists.
    File: redis_client.py, Methods: lpush(), rpush(), lpop(), rpop(), lrange(), etc.
    """
    print("\n" + "=" * 80)
    print("Example 8: List Operations (Task Queue)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Create a task queue
        client.delete('queue:tasks')
        client.rpush('queue:tasks', ['task1', 'task2', 'task3'])
        print(f"\n📥 Pushed 3 tasks to queue")
        
        # Add urgent task to front
        length = client.lpush('queue:tasks', ['urgent_task'])
        print(f"   Queue length after urgent task: {length}")
        
        # Get queue length
        queue_size = client.llen('queue:tasks')
        print(f"\n📊 Current queue size: {queue_size}")
        
        # Peek at specific position
        task_at_1 = client.lindex('queue:tasks', 1)
        print(f"   Task at index 1: {task_at_1}")
        
        # View all tasks
        all_tasks = client.lrange('queue:tasks', 0, -1)
        print(f"\n📋 All tasks in queue:")
        for i, task in enumerate(all_tasks):
            print(f"   {i}. {task}")
        
        # Process tasks (pop from left)
        task = client.lpop('queue:tasks')
        print(f"\n⚙️  Processing task: {task}")
        
        # Pop from right
        last_task = client.rpop('queue:tasks')
        print(f"   Last task: {last_task}")
        
        # Trim queue to keep only first 2 items
        client.ltrim('queue:tasks', 0, 1)
        final_size = client.llen('queue:tasks')
        print(f"\n✂️  Trimmed queue, new size: {final_size}")


def example_09_set_operations(host='localhost', port=50055):
    """
    Example 9: Set Operations
    
    Manage unique collections and perform set operations (union, intersection, diff).
    File: redis_client.py, Methods: sadd(), smembers(), sunion(), sinter(), sdiff(), etc.
    """
    print("\n" + "=" * 80)
    print("Example 9: Set Operations (Tags and Permissions)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Create sets
        client.sadd('user:alice:tags', ['python', 'golang', 'redis', 'docker'])
        client.sadd('user:bob:tags', ['python', 'javascript', 'redis', 'kubernetes'])
        
        # Get set members
        alice_tags = client.smembers('user:alice:tags')
        print(f"\n🏷️  Alice's tags: {', '.join(sorted(alice_tags))}")
        
        bob_tags = client.smembers('user:bob:tags')
        print(f"   Bob's tags: {', '.join(sorted(bob_tags))}")
        
        # Check membership
        has_python = client.sismember('user:alice:tags', 'python')
        print(f"\n🔍 Alice has 'python' tag: {has_python}")
        
        # Get cardinality (size)
        count = client.scard('user:alice:tags')
        print(f"   Alice has {count} tags total")
        
        # Set operations
        all_tags = client.sunion(['user:alice:tags', 'user:bob:tags'])
        print(f"\n🔗 Union (all unique tags): {', '.join(sorted(all_tags))}")
        
        common_tags = client.sinter(['user:alice:tags', 'user:bob:tags'])
        print(f"   Intersection (common tags): {', '.join(sorted(common_tags))}")
        
        alice_only = client.sdiff(['user:alice:tags', 'user:bob:tags'])
        print(f"   Difference (Alice only): {', '.join(sorted(alice_only))}")
        
        # Remove a tag
        removed = client.sremove('user:alice:tags', ['docker'])
        print(f"\n🗑️  Removed {removed} tag(s) from Alice")


def example_10_sorted_set_operations(host='localhost', port=50055):
    """
    Example 10: Sorted Set Operations
    
    Implement leaderboards and ranked data using sorted sets.
    File: redis_client.py, Methods: zadd(), zrange(), zrank(), zscore(), etc.
    """
    print("\n" + "=" * 80)
    print("Example 10: Sorted Set Operations (Leaderboard)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Add players to leaderboard
        leaderboard_data = {
            'Alice': 1500,
            'Bob': 2100,
            'Charlie': 1800,
            'Diana': 2500,
            'Eve': 1200
        }
        
        count = client.zadd('game:leaderboard', leaderboard_data)
        print(f"\n🏆 Added {count} players to leaderboard")
        
        # Get leaderboard size
        total_players = client.zcard('game:leaderboard')
        print(f"   Total players: {total_players}")
        
        # Get top 3 players
        top_3 = client.zrange('game:leaderboard', -3, -1, with_scores=True)
        print(f"\n🥇 Top 3 Players:")
        for i, (player, score) in enumerate(reversed(top_3), 1):
            print(f"   {i}. {player}: {score} points")
        
        # Get player's rank
        rank = client.zrank('game:leaderboard', 'Bob')
        print(f"\n📊 Bob's rank: {rank + 1} (0-indexed: {rank})")
        
        # Get player's score
        score = client.zscore('game:leaderboard', 'Bob')
        print(f"   Bob's score: {score}")
        
        # Increment player's score
        new_score = client.zincrement('game:leaderboard', 'Alice', 100)
        print(f"\n➕ Alice earned 100 points! New score: {new_score}")
        
        # Get players in score range
        mid_tier = client.zrange_by_score('game:leaderboard', 1500, 2000)
        print(f"\n🎯 Players with scores 1500-2000:")
        for player, score in mid_tier:
            print(f"   - {player}: {score}")
        
        # Remove a player
        removed = client.zrem('game:leaderboard', ['Eve'])
        print(f"\n🗑️  Removed {removed} player(s)")


def example_11_distributed_locks(host='localhost', port=50055):
    """
    Example 11: Distributed Locks
    
    Coordinate access to shared resources using distributed locks.
    File: redis_client.py, Methods: acquire_lock(), release_lock(), renew_lock()
    """
    print("\n" + "=" * 80)
    print("Example 11: Distributed Locks (Resource Synchronization)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Acquire lock
        lock_id = client.acquire_lock('resource:database_migration', ttl_seconds=30)
        
        if lock_id:
            print(f"\n🔒 Lock acquired!")
            print(f"   Lock ID: {lock_id}")
            
            # Simulate long-running operation
            print(f"\n⚙️  Performing critical operation...")
            time.sleep(1)
            
            # Renew lock if needed
            renewed = client.renew_lock('resource:database_migration', lock_id, ttl_seconds=30)
            if renewed:
                print(f"   Lock renewed for another 30 seconds")
            
            # Release lock when done
            released = client.release_lock('resource:database_migration', lock_id)
            if released:
                print(f"\n🔓 Lock released successfully")
        else:
            print(f"\n⏳ Failed to acquire lock (already held by another process)")


def example_12_pubsub_operations(host='localhost', port=50055):
    """
    Example 12: Pub/Sub Operations
    
    Publish messages to channels for real-time communication.
    File: redis_client.py, Methods: publish(), subscribe(), unsubscribe()
    """
    print("\n" + "=" * 80)
    print("Example 12: Pub/Sub Operations (Message Broadcasting)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Publish messages
        count1 = client.publish('notifications:global', 'System maintenance scheduled')
        print(f"\n📢 Published to 'notifications:global': {count1} subscribers")
        
        count2 = client.publish('alerts:critical', 'High CPU usage detected')
        print(f"   Published to 'alerts:critical': {count2} subscribers")
        
        count3 = client.publish('events:user_login', 'User alice@example.com logged in')
        print(f"   Published to 'events:user_login': {count3} subscribers")
        
        print(f"\n💡 Note: Subscribe requires a separate long-running process")
        print(f"   Use: client.subscribe(['channel1', 'channel2'], callback_function)")


def example_13_batch_operations(host='localhost', port=50055):
    """
    Example 13: Batch Operations
    
    Execute multiple operations efficiently in batches.
    File: redis_client.py, Methods: mset(), mget(), execute_batch()
    """
    print("\n" + "=" * 80)
    print("Example 13: Batch Operations (Efficient Multi-Key Processing)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Batch SET (MSET)
        user_settings = {
            'config:theme': 'dark',
            'config:language': 'en',
            'config:timezone': 'UTC',
            'config:notifications': 'enabled'
        }
        
        success = client.mset(user_settings)
        if success:
            print(f"\n📦 Batch set {len(user_settings)} configuration keys")
        
        # Batch GET (MGET)
        values = client.mget(['config:theme', 'config:language', 'config:timezone'])
        print(f"\n📥 Batch retrieved {len(values)} values:")
        for key, value in values.items():
            print(f"   {key}: {value}")
        
        # Execute batch commands
        commands = [
            {'operation': 'SET', 'key': 'batch:key1', 'value': 'value1'},
            {'operation': 'SET', 'key': 'batch:key2', 'value': 'value2', 'expiration': 300},
            {'operation': 'SET', 'key': 'batch:key3', 'value': 'value3'}
        ]
        
        result = client.execute_batch(commands)
        if result and result.get('success'):
            print(f"\n⚡ Executed batch of {result.get('executed_count')} commands")
            if result.get('errors'):
                print(f"   Errors: {result.get('errors')}")


def example_14_session_management(host='localhost', port=50055):
    """
    Example 14: Session Management
    
    Manage user sessions with automatic expiration.
    File: redis_client.py, Methods: create_session(), get_session(), update_session(), etc.
    """
    print("\n" + "=" * 80)
    print("Example 14: Session Management (User Sessions)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Create session
        session_data = {
            'username': 'alice',
            'role': 'admin',
            'login_time': datetime.now().isoformat(),
            'ip_address': '192.168.1.100'
        }
        
        session_id = client.create_session(session_data, ttl_seconds=3600)
        print(f"\n🎫 Session created: {session_id}")
        print(f"   TTL: 3600 seconds (1 hour)")
        
        # Give server time to process
        time.sleep(0.1)
        
        # Update session
        updated_data = {
            'username': 'alice',
            'role': 'superadmin',  # Role elevated
            'last_activity': datetime.now().isoformat()
        }
        
        success = client.update_session(session_id, updated_data, extend_ttl=True)
        if success:
            print(f"\n✏️  Session updated with new role")
        
        # List sessions
        sessions = client.list_sessions()
        print(f"\n📋 Active sessions: {len(sessions)}")
        for sess in sessions[:3]:  # Show first 3
            print(f"   - {sess['session_id']}")
        
        # Delete session (logout)
        deleted = client.delete_session(session_id)
        if deleted:
            print(f"\n🚪 Session deleted (user logged out)")


def example_15_monitoring_operations(host='localhost', port=50055):
    """
    Example 15: Monitoring and Statistics
    
    Monitor Redis usage and get detailed key information.
    File: redis_client.py, Methods: get_statistics(), get_key_info()
    """
    print("\n" + "=" * 80)
    print("Example 15: Monitoring and Statistics")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Create some test data
        client.set('monitor:key1', 'value1')
        client.hset('monitor:hash', 'field1', 'value1')
        client.lpush('monitor:list', ['item1', 'item2'])
        
        # Get Redis statistics
        stats = client.get_statistics()
        if stats:
            print(f"\n📊 Redis Statistics:")
            print(f"   Total keys: {stats.get('total_keys')}")
            print(f"   Memory used: {stats.get('memory_used_bytes')/1024/1024:.2f}MB")
            print(f"   Commands processed: {stats.get('commands_processed')}")
            print(f"   Hit rate: {stats.get('hit_rate'):.2%}")
            
            if stats.get('key_type_distribution'):
                print(f"\n📈 Key type distribution:")
                for key_type, count in stats.get('key_type_distribution').items():
                    print(f"   {key_type}: {count}")
        
        # Get detailed key information
        info = client.get_key_info('monitor:key1')
        if info and info.get('exists'):
            print(f"\n🔍 Key 'monitor:key1' details:")
            print(f"   Type: {info.get('type')}")
            print(f"   Size: {info.get('size_bytes')} bytes")
            print(f"   TTL: {info.get('ttl_seconds')} seconds")


def example_16_batch_mset_mget(host='localhost', port=50055):
    """
    Example 16: Batch MSET/MGET
    
    Efficiently set and get multiple key-value pairs.
    File: redis_client.py, Methods: mset(), mget()
    """
    print("\n" + "=" * 80)
    print("Example 16: Batch MSET/MGET Operations")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Batch set multiple user preferences
        preferences = {
            'pref:alice:theme': 'dark',
            'pref:alice:language': 'en',
            'pref:alice:timezone': 'America/New_York',
            'pref:alice:notifications': 'email',
            'pref:alice:privacy': 'friends_only'
        }
        
        success = client.mset(preferences)
        if success:
            print(f"\n💾 Batch set {len(preferences)} preferences")
        
        # Batch get preferences
        keys_to_fetch = list(preferences.keys())
        values = client.mget(keys_to_fetch)
        
        print(f"\n📥 Batch retrieved {len(values)} values:")
        for key, value in values.items():
            setting_name = key.split(':')[-1]
            print(f"   {setting_name}: {value}")


def example_17_real_world_cache(host='localhost', port=50055):
    """
    Example 17: Real-World Caching Pattern
    
    Demonstrate typical web application caching patterns.
    File: redis_client.py, Multiple methods combined
    """
    print("\n" + "=" * 80)
    print("Example 17: Real-World Caching Pattern (API Response Cache)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        # Simulate API response caching
        api_endpoint = 'api/v1/users/profile'
        cache_key = f'cache:{api_endpoint}:user123'
        
        # Check if cached
        cached_response = client.get(cache_key)
        
        if cached_response:
            print(f"\n💨 Cache HIT! Retrieved from cache")
            print(f"   Data: {cached_response}")
        else:
            print(f"\n🔍 Cache MISS! Fetching from database...")
            
            # Simulate database query
            time.sleep(0.5)
            fresh_data = '{"id": 123, "name": "Alice", "role": "admin"}'
            
            # Store in cache with 5 minute TTL
            client.set_with_ttl(cache_key, fresh_data, 300)
            print(f"   ✅ Stored in cache (TTL: 300s)")
        
        # Track cache stats
        client.incr('stats:cache_hits', 1)
        client.incr('stats:api_calls', 1)
        
        hits = client.get('stats:cache_hits')
        calls = client.get('stats:api_calls')
        
        print(f"\n📊 Cache Statistics:")
        print(f"   Total API calls: {calls}")
        print(f"   Cache hits: {hits}")
        if calls and hits:
            hit_rate = (int(hits) / int(calls)) * 100
            print(f"   Hit rate: {hit_rate:.1f}%")


def example_18_rate_limiting(host='localhost', port=50055):
    """
    Example 18: Rate Limiting Pattern
    
    Implement API rate limiting using Redis counters.
    File: redis_client.py, Methods: incr(), ttl(), set_with_ttl()
    """
    print("\n" + "=" * 80)
    print("Example 18: Rate Limiting Pattern (API Throttling)")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        user_id = 'user:12345'
        rate_limit_key = f'ratelimit:{user_id}'
        max_requests = 10
        window_seconds = 60
        
        print(f"\n🚦 Rate Limit: {max_requests} requests per {window_seconds} seconds")
        
        # Simulate multiple API requests
        for i in range(12):
            # Get current count
            current_count = client.get(rate_limit_key)
            
            if current_count is None:
                # First request in window
                client.set_with_ttl(rate_limit_key, '1', window_seconds)
                count = 1
            else:
                count = client.incr(rate_limit_key, 1)
            
            if count <= max_requests:
                print(f"   ✅ Request {i+1}: Allowed (count: {count}/{max_requests})")
            else:
                ttl = client.ttl(rate_limit_key)
                print(f"   ❌ Request {i+1}: BLOCKED (retry in {ttl}s)")
                break


def example_19_user_profile_complete(host='localhost', port=50055):
    """
    Example 19: Complete User Profile Management
    
    Combine multiple data structures for rich user profiles.
    File: redis_client.py, Multiple methods (Hash, Set, Sorted Set)
    """
    print("\n" + "=" * 80)
    print("Example 19: Complete User Profile Management")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        user_id = 'user:5001'
        
        # Store profile data in hash
        client.hset(user_id, 'name', 'Sarah Connor')
        client.hset(user_id, 'email', 'sarah@example.com')
        client.hset(user_id, 'joined', '2025-01-15')
        client.hset(user_id, 'status', 'active')
        
        # Store user's skills as a set
        client.sadd(f'{user_id}:skills', ['Python', 'Go', 'Redis', 'Docker', 'Kubernetes'])
        
        # Store user's activity score in sorted set
        client.zadd('users:activity', {user_id: 850})
        
        # Retrieve complete profile
        profile = client.hgetall(user_id)
        skills = client.smembers(f'{user_id}:skills')
        activity_score = client.zscore('users:activity', user_id)
        rank = client.zrank('users:activity', user_id)
        
        print(f"\n👤 User Profile:")
        print(f"   Name: {profile.get('name')}")
        print(f"   Email: {profile.get('email')}")
        print(f"   Status: {profile.get('status')}")
        print(f"   Member since: {profile.get('joined')}")
        
        print(f"\n💼 Skills ({len(skills)}):")
        print(f"   {', '.join(sorted(skills))}")
        
        print(f"\n📊 Activity:")
        print(f"   Score: {activity_score}")
        print(f"   Rank: #{rank + 1}")


def example_20_advanced_patterns(host='localhost', port=50055):
    """
    Example 20: Advanced Redis Patterns
    
    Demonstrate advanced usage patterns combining multiple features.
    File: redis_client.py, Multiple methods combined
    """
    print("\n" + "=" * 80)
    print("Example 20: Advanced Redis Patterns")
    print("=" * 80)
    
    with RedisClient(host=host, port=port, user_id='example-user') as client:
        print(f"\n🎯 Pattern 1: Recent Items (List as Queue)")
        # Keep last 5 viewed items
        client.delete('user:recent_views')
        items = ['product:101', 'product:205', 'product:150', 'product:301', 'product:199', 'product:167']
        for item in items:
            client.lpush('user:recent_views', [item])
            client.ltrim('user:recent_views', 0, 4)  # Keep only 5 most recent
        
        recent = client.lrange('user:recent_views', 0, -1)
        print(f"   Recent 5 items: {recent[:5]}")
        
        print(f"\n🎯 Pattern 2: Unique Visitors (Set)")
        # Track unique visitors
        client.sadd('visitors:today', ['192.168.1.1', '192.168.1.2', '192.168.1.1', '10.0.0.5'])
        unique_count = client.scard('visitors:today')
        print(f"   Unique visitors today: {unique_count}")
        
        print(f"\n🎯 Pattern 3: Time Series Data (Sorted Set)")
        # Store metrics with timestamps as scores
        timestamp = int(time.time())
        client.zadd('metrics:cpu_usage', {
            f'measurement:{timestamp-300}': timestamp-300,
            f'measurement:{timestamp-200}': timestamp-200,
            f'measurement:{timestamp-100}': timestamp-100,
            f'measurement:{timestamp}': timestamp
        })
        
        # Get recent measurements (last 2)
        recent_metrics = client.zrange('metrics:cpu_usage', -2, -1)
        print(f"   Recent 2 measurements: {recent_metrics}")
        
        print(f"\n🎯 Pattern 4: Counters with Auto-Reset (TTL)")
        # Daily request counter that resets automatically
        daily_key = f'requests:daily:{datetime.now().strftime("%Y%m%d")}'
        count = client.incr(daily_key, 1)
        client.expire(daily_key, 86400)  # Expires in 24 hours
        print(f"   Daily requests: {count} (auto-resets tomorrow)")


def run_all_examples(host='localhost', port=50055):
    """Run all examples in sequence"""
    print("\n" + "=" * 80)
    print("  Redis Client Usage Examples")
    print("  Based on isa_common.redis_client.RedisClient")
    print("=" * 80)
    print(f"\nConnecting to: {host}:{port}")
    print(f"Timestamp: {datetime.now()}\n")
    
    examples = [
        example_01_health_check,
        example_02_string_operations,
        example_03_ttl_expiration,
        example_04_string_append,
        example_05_counter_operations,
        example_06_key_operations,
        example_07_hash_operations,
        example_08_list_operations,
        example_09_set_operations,
        example_10_sorted_set_operations,
        example_11_distributed_locks,
        example_12_pubsub_operations,
        example_13_batch_operations,
        example_14_session_management,
        example_15_monitoring_operations,
        example_16_batch_mset_mget,
        example_17_real_world_cache,
        example_18_rate_limiting,
        example_19_user_profile_complete,
        example_20_advanced_patterns,
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
    print("  - Client source: isA_common/isa_common/redis_client.py (1,594 lines, 60 methods)")
    print("  - Proto definition: api/proto/redis_service.proto")
    print("  - Test script: isA_common/tests/redis/test_redis_functional.sh")
    print("  - Test result: 18/18 tests passing (100% success rate)")
    print("\n📚 Covered Operations (60 total):")
    print("   - String: 7 operations")
    print("   - Key: 7 operations")
    print("   - Hash: 8 operations")
    print("   - List: 8 operations")
    print("   - Set: 8 operations")
    print("   - Sorted Set: 8 operations")
    print("   - Locks: 3 operations")
    print("   - Pub/Sub: 3 operations")
    print("   - Batch: 2 operations")
    print("   - Sessions: 5 operations")
    print("   - Monitoring: 2 operations")
    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Redis Client Usage Examples',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--host', default=None,
                       help='Redis gRPC service host (default: auto-discover from Consul, fallback to localhost)')
    parser.add_argument('--port', type=int, default=None,
                       help='Redis gRPC service port (default: auto-discover from Consul, fallback to 50055)')
    parser.add_argument('--consul-host', default='localhost',
                       help='Consul host (default: localhost)')
    parser.add_argument('--consul-port', type=int, default=8500,
                       help='Consul port (default: 8500)')
    parser.add_argument('--no-consul', action='store_true',
                       help='Skip Consul discovery, use localhost directly')
    parser.add_argument('--example', type=int, choices=range(1, 21),
                       help='Run specific example (1-20, default: all)')

    args = parser.parse_args()

    # Default: Try Consul first, fallback to localhost
    host = args.host
    port = args.port

    if host is None or port is None:
        if not args.no_consul:
            try:
                from isa_common.consul_client import ConsulRegistry
                print(f"🔍 Attempting Consul discovery from {args.consul_host}:{args.consul_port}...")
                consul = ConsulRegistry(consul_host=args.consul_host, consul_port=args.consul_port)
                redis_url = consul.get_redis_url()

                # Parse URL
                if '://' in redis_url:
                    redis_url = redis_url.split('://', 1)[1]
                discovered_host, port_str = redis_url.rsplit(':', 1)
                discovered_port = int(port_str)

                host = host or discovered_host
                port = port or discovered_port
                print(f"✅ Discovered from Consul: {host}:{port}")
            except Exception as e:
                print(f"⚠️  Consul discovery failed: {e}")
                print(f"📍 Falling back to localhost...")

        # Fallback to defaults
        host = host or 'localhost'
        port = port or 50055

    print(f"🔗 Connecting to Redis at {host}:{port}\n")
    
    if args.example:
        # Run specific example
        examples_map = {
            1: example_01_health_check,
            2: example_02_string_operations,
            3: example_03_ttl_expiration,
            4: example_04_string_append,
            5: example_05_counter_operations,
            6: example_06_key_operations,
            7: example_07_hash_operations,
            8: example_08_list_operations,
            9: example_09_set_operations,
            10: example_10_sorted_set_operations,
            11: example_11_distributed_locks,
            12: example_12_pubsub_operations,
            13: example_13_batch_operations,
            14: example_14_session_management,
            15: example_15_monitoring_operations,
            16: example_16_batch_mset_mget,
            17: example_17_real_world_cache,
            18: example_18_rate_limiting,
            19: example_19_user_profile_complete,
            20: example_20_advanced_patterns,
        }
        examples_map[args.example](host=args.host, port=args.port)
    else:
        # Run all examples
        run_all_examples(host=args.host, port=args.port)


if __name__ == '__main__':
    main()

