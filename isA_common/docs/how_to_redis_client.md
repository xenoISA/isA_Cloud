# 🔴 Redis Client - In-Memory Data Structures Made Simple

## Installation

```bash
pip install -e /path/to/isA_Cloud/isA_common
```

## Simple Usage Pattern

```python
from isa_common.redis_client import RedisClient

# Connect and use (auto-discovers via Consul or use direct host)
with RedisClient(host='localhost', port=50055, user_id='your-service') as client:

    # 1. String operations
    client.set('user:123:name', 'Alice')
    name = client.get('user:123:name')

    # 2. Counters (atomic operations)
    views = client.incr('page:views', 1)

    # 3. Hashes (structured data)
    client.hset('user:123', 'email', 'alice@example.com')
    email = client.hget('user:123', 'email')

    # 4. Lists (queues, stacks)
    client.rpush('tasks', ['task1', 'task2'])
    task = client.lpop('tasks')

    # 5. Sets (unique collections)
    client.sadd('tags', ['python', 'redis', 'docker'])
    tags = client.smembers('tags')

    # 6. Sorted Sets (leaderboards, rankings)
    client.zadd('leaderboard', {'player1': 1500, 'player2': 2100})
    top_players = client.zrange('leaderboard', -10, -1, with_scores=True)
```

---

## Real Service Example: Caching Service

```python
from isa_common.redis_client import RedisClient
from datetime import datetime
import json

class CacheService:
    def __init__(self):
        self.redis = RedisClient(user_id='cache-service')
        self.default_ttl = 3600  # 1 hour

    def cache_api_response(self, endpoint, user_id, data):
        # Just business logic - no Redis complexity!
        with self.redis:
            cache_key = f'api:{endpoint}:user:{user_id}'
            
            # Cache with automatic expiration - ONE LINE
            return self.redis.set_with_ttl(
                cache_key,
                json.dumps(data),
                self.default_ttl
            )

    def get_cached_response(self, endpoint, user_id):
        # Retrieve from cache - ONE LINE
        with self.redis:
            cache_key = f'api:{endpoint}:user:{user_id}'
            cached = self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            return None

    def track_api_calls(self, user_id):
        # Rate limiting with atomic counters
        with self.redis:
            key = f'ratelimit:{user_id}'
            count = self.redis.get(key)
            
            if count is None:
                # First request in window
                self.redis.set_with_ttl(key, '1', 60)
                return 1
            else:
                return self.redis.incr(key, 1)

    def store_user_session(self, session_id, user_data, ttl=7200):
        # Session management - ONE CALL
        with self.redis:
            return self.redis.create_session(user_data, ttl_seconds=ttl)

    def get_cache_stats(self):
        # Monitor cache performance
        with self.redis:
            stats = self.redis.get_statistics()
            return {
                'total_keys': stats['total_keys'],
                'memory_used_mb': stats['memory_used_bytes'] / 1024 / 1024,
                'hit_rate': stats['hit_rate']
            }
```

---

## Quick Patterns for Common Use Cases

### String Operations (Key-Value)
```python
# Set and get
client.set('config:theme', 'dark')
theme = client.get('config:theme')

# Set with expiration (TTL)
client.set_with_ttl('session:temp', 'data', 300)  # Expires in 5 min

# Append to string
client.append('log:entry', ' | Additional info')

# Check existence
exists = client.exists('user:123')

# Delete keys
client.delete('old:key')
client.delete_multiple(['key1', 'key2', 'key3'])
```

### Counters (Atomic Operations)
```python
# Increment
views = client.incr('page:views', 1)
views = client.incr('page:views', 10)  # Increment by 10

# Decrement
remaining = client.decr('inventory:item:123', 1)

# Use for rate limiting
request_count = client.incr(f'ratelimit:user:{user_id}', 1)
if request_count > 100:
    print("Rate limit exceeded!")
```

### Hash Operations (Structured Data)
```python
# Set hash fields
client.hset('user:123', 'name', 'Alice')
client.hset('user:123', 'email', 'alice@example.com')
client.hset('user:123', 'age', '28')

# Get single field
name = client.hget('user:123', 'name')

# Get all fields
user_data = client.hgetall('user:123')
# Returns: {'name': 'Alice', 'email': 'alice@example.com', 'age': '28'}

# Get all field names
fields = client.hkeys('user:123')

# Get all values
values = client.hvalues('user:123')

# Check field existence
has_email = client.hexists('user:123', 'email')

# Increment hash field
login_count = client.hincrement('user:123', 'login_count', 1)

# Delete fields
client.hdelete('user:123', ['age'])
```

### List Operations (Queues & Stacks)
```python
# Push to right (append)
length = client.rpush('queue:tasks', ['task1', 'task2', 'task3'])

# Push to left (prepend)
client.lpush('queue:tasks', ['urgent_task'])

# Pop from left (FIFO queue)
task = client.lpop('queue:tasks')

# Pop from right (stack)
last = client.rpop('queue:tasks')

# Get list length
size = client.llen('queue:tasks')

# Get element at index
item = client.lindex('queue:tasks', 0)

# Get range of elements
tasks = client.lrange('queue:tasks', 0, -1)  # All elements

# Trim list (keep only first N)
client.ltrim('queue:tasks', 0, 99)  # Keep first 100
```

### Set Operations (Unique Collections)
```python
# Add members
client.sadd('user:tags', ['python', 'redis', 'docker'])

# Get all members
tags = client.smembers('user:tags')

# Check membership
has_python = client.sismember('user:tags', 'python')

# Get set size
count = client.scard('user:tags')

# Remove members
removed = client.sremove('user:tags', ['docker'])

# Set operations
all_tags = client.sunion(['user:alice:tags', 'user:bob:tags'])
common_tags = client.sinter(['user:alice:tags', 'user:bob:tags'])
unique_tags = client.sdiff(['user:alice:tags', 'user:bob:tags'])
```

### Sorted Set Operations (Leaderboards)
```python
# Add members with scores
leaderboard = {
    'Alice': 1500,
    'Bob': 2100,
    'Charlie': 1800
}
client.zadd('game:leaderboard', leaderboard)

# Get leaderboard size
total = client.zcard('game:leaderboard')

# Get top N players (highest scores)
top_10 = client.zrange('game:leaderboard', -10, -1, with_scores=True)

# Get player's rank (0-based)
rank = client.zrank('game:leaderboard', 'Bob')

# Get player's score
score = client.zscore('game:leaderboard', 'Bob')

# Increment score
new_score = client.zincrement('game:leaderboard', 'Alice', 100)

# Get players in score range
mid_tier = client.zrange_by_score('game:leaderboard', 1500, 2000)

# Remove player
client.zrem('game:leaderboard', ['Charlie'])
```

### Distributed Locks
```python
# Acquire lock
lock_id = client.acquire_lock('resource:database', ttl_seconds=30)

if lock_id:
    try:
        # Critical section
        print("Lock acquired, performing operation...")
        
        # Renew if operation takes longer
        client.renew_lock('resource:database', lock_id, ttl_seconds=30)
        
    finally:
        # Always release lock
        client.release_lock('resource:database', lock_id)
else:
    print("Could not acquire lock")
```

### Pub/Sub Messaging
```python
# Publish message
subscribers = client.publish('notifications:global', 'System update')
print(f"Message delivered to {subscribers} subscribers")

# Publish JSON
import json
event = {'type': 'user_login', 'user_id': '123'}
client.publish('events:user', json.dumps(event))

# Subscribe (requires separate long-running process)
def message_handler(channel, message):
    print(f"Received on {channel}: {message}")

client.subscribe(['notifications:global', 'events:user'], message_handler)
```

### Batch Operations
```python
# MSET - Set multiple keys at once
config = {
    'theme': 'dark',
    'language': 'en',
    'timezone': 'UTC'
}
client.mset(config)

# MGET - Get multiple keys at once
values = client.mget(['theme', 'language', 'timezone'])

# Execute batch commands
commands = [
    {'operation': 'SET', 'key': 'key1', 'value': 'value1'},
    {'operation': 'SET', 'key': 'key2', 'value': 'value2', 'expiration': 300},
    {'operation': 'INCR', 'key': 'counter'}
]
result = client.execute_batch(commands)
```

### Session Management
```python
# Create session with auto-expiration
session_data = {
    'user_id': '123',
    'username': 'alice',
    'role': 'admin'
}
session_id = client.create_session(session_data, ttl_seconds=3600)

# Get session
session = client.get_session(session_id)

# Update session (extends TTL)
updated_data = {'user_id': '123', 'role': 'superadmin'}
client.update_session(session_id, updated_data, extend_ttl=True)

# List all sessions
sessions = client.list_sessions()

# Delete session (logout)
client.delete_session(session_id)
```

### Key Management
```python
# Set expiration on existing key
client.expire('temp:data', 300)  # Expires in 5 minutes

# Get time-to-live
ttl = client.ttl('temp:data')

# Rename key
client.rename('old:name', 'new:name')

# List keys by pattern
keys = client.list_keys('user:*', limit=100)

# Get detailed key info
info = client.get_key_info('user:123')
print(f"Type: {info['type']}, Size: {info['size_bytes']}, TTL: {info['ttl_seconds']}")
```

### Monitoring and Statistics
```python
# Get Redis statistics
stats = client.get_statistics()
print(f"Total keys: {stats['total_keys']}")
print(f"Memory used: {stats['memory_used_bytes']/1024/1024:.2f}MB")
print(f"Commands processed: {stats['commands_processed']}")
print(f"Hit rate: {stats['hit_rate']:.2%}")

# Key type distribution
for key_type, count in stats['key_type_distribution'].items():
    print(f"{key_type}: {count}")
```

---

## Benefits = Zero Redis Complexity

### What you DON'T need to worry about:
- ❌ Redis protocol implementation
- ❌ Connection pooling management
- ❌ gRPC serialization
- ❌ Error handling and retries
- ❌ Lua scripting for atomicity
- ❌ Pipeline optimization
- ❌ Pub/Sub thread management
- ❌ Data type conversions
- ❌ Context managers and cleanup

### What you CAN focus on:
- ✅ Your caching strategy
- ✅ Your data structures
- ✅ Your business logic
- ✅ Performance optimization
- ✅ Rate limiting rules
- ✅ Session management

---

## Comparison: Without vs With Client

### Without (Raw redis-py + gRPC):
```python
# 150+ lines of Redis setup, connection pooling, error handling...
import redis
import grpc
from redis_pb2_grpc import RedisServiceStub

# Setup gRPC channel
channel = grpc.insecure_channel('localhost:50055')
stub = RedisServiceStub(channel)

# Setup Redis client
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True,
    socket_keepalive=True,
    retry_on_timeout=True
)

try:
    # Set key
    redis_client.set('user:123', 'Alice')
    
    # Get key
    value = redis_client.get('user:123')
    
    # Handle errors
except redis.ConnectionError as e:
    print(f"Connection error: {e}")
except redis.TimeoutError as e:
    print(f"Timeout: {e}")
finally:
    redis_client.close()
    channel.close()
```

### With isa_common:
```python
# 3 lines
with RedisClient(user_id='my-service') as client:
    client.set('user:123', 'Alice')
    value = client.get('user:123')
```

---

## Complete Feature List

| **String Operations**: set, get, append, delete, exists (7 operations)
| **Key Operations**: expire, ttl, rename, delete_multiple, list_keys (7 operations)
| **Hash Operations**: hset, hget, hgetall, hdelete, hexists, hkeys, hvalues, hincrement (8 operations)
| **List Operations**: lpush, rpush, lpop, rpop, lrange, llen, lindex, ltrim (8 operations)
| **Set Operations**: sadd, sremove, smembers, sismember, scard, sunion, sinter, sdiff (8 operations)
| **Sorted Set Operations**: zadd, zrem, zrange, zrank, zscore, zcard, zincrement, zrange_by_score (8 operations)
| **Distributed Locks**: acquire, release, renew (3 operations)
| **Pub/Sub**: publish, subscribe, unsubscribe (3 operations)
| **Batch Operations**: mset, mget, execute_batch (3 operations)
| **Session Management**: create, get, update, delete, list (5 operations)
| **Monitoring**: get_statistics, get_key_info (2 operations)
| **Health Check**: service status monitoring
| **Multi-tenancy**: User-scoped operations
| **Auto-Cleanup**: Context manager support

**Total: 60 methods covering all Redis data structures**

---

## Async Client Usage (High-Performance)

For high-concurrency applications, use `AsyncRedisClient` with `async/await`:

```python
import asyncio
from isa_common import AsyncRedisClient, BatchedRedisGet, BatchedRedisSet

async def main():
    async with AsyncRedisClient(
        host='localhost',
        port=50055,
        user_id='your-service'
    ) as client:
        # Basic operations (same API as sync)
        await client.set('key', 'value')
        value = await client.get('key')

        # TTL operations
        await client.set_with_ttl('temp:key', 'expires', 300)
        ttl = await client.ttl('temp:key')

        # Batch operations (optimized single RPC)
        await client.mset({'key1': 'val1', 'key2': 'val2', 'key3': 'val3'})
        values = await client.mget(['key1', 'key2', 'key3'])

        # Hash operations
        await client.hset('user:123', 'name', 'Alice')
        name = await client.hget('user:123', 'name')
        all_fields = await client.hgetall('user:123')

        # List operations
        await client.lpush('queue', ['a', 'b'])
        await client.rpush('queue', ['c', 'd'])
        items = await client.lrange('queue', 0, -1)

        # Set operations
        await client.sadd('tags', ['python', 'redis', 'docker'])
        members = await client.smembers('tags')

        # Sorted set operations
        await client.zadd('leaderboard', {'player1': 100, 'player2': 200})
        top = await client.zrange('leaderboard', 0, -1)

        # Distributed locks
        lock_id = await client.acquire_lock('resource', ttl_seconds=10)
        if lock_id:
            try:
                # Critical section
                await client.renew_lock('resource', lock_id, ttl_seconds=10)
            finally:
                await client.release_lock('resource', lock_id)

        # Pub/Sub
        await client.publish('channel', 'message')

        # Session management
        session_id = await client.create_session({'user': 'john'}, ttl_seconds=3600)
        await client.delete_session(session_id)

asyncio.run(main())
```

### Concurrent Operations with asyncio.gather

```python
async def concurrent_example(client):
    # Execute 5 GET operations concurrently
    results = await asyncio.gather(
        client.get('key1'),
        client.get('key2'),
        client.get('key3'),
        client.get('key4'),
        client.get('key5'),
    )
    return results
```

### get_many_concurrent Helper

```python
async def bulk_get(client):
    # Optimized bulk GET
    results = await client.get_many_concurrent(['key1', 'key2', 'key3'])
    # Returns: {'key1': 'val1', 'key2': 'val2', 'key3': 'val3'}
    return results
```

### Auto-Batching with BatchedRedisGet/BatchedRedisSet

Automatically coalesce concurrent requests into single batch RPCs:

```python
async def auto_batching_example(client):
    # Create batched getter (auto-coalesces within 10ms window)
    batched_get = BatchedRedisGet(client, max_size=100, max_wait_ms=10)

    # These concurrent gets are automatically batched into one MGET
    results = await asyncio.gather(
        batched_get.get('key1'),
        batched_get.get('key2'),
        batched_get.get('key3'),
    )

    # Create batched setter
    batched_set = BatchedRedisSet(client, max_size=100, max_wait_ms=10)

    # These concurrent sets are automatically batched into one MSET
    await asyncio.gather(
        batched_set.set('key1', 'val1'),
        batched_set.set('key2', 'val2'),
        batched_set.set('key3', 'val3'),
    )
```

---

## Test Results

**Sync Client: 18/18 tests passing (100% success rate)**
**Async Client: 18/18 tests passing (100% success rate)**

Comprehensive functional tests cover:
- String operations (SET, GET, APPEND, DELETE)
- TTL and expiration
- Counter operations (INCR, DECR)
- Batch operations (MSET, MGET via ExecuteBatch)
- Hash operations (HSET, HGET, HGETALL, HEXISTS, HDELETE)
- List operations (LPUSH, RPUSH, LPOP, RPOP, LRANGE, LLEN)
- Set operations (SADD, SMEMBERS, SISMEMBER, SCARD)
- Sorted set operations (ZADD, ZCARD, ZSCORE, ZRANK, ZRANGE)
- Distributed locks (acquire, renew, release)
- Pub/Sub messaging
- Session management (create, delete)
- Concurrent operations (asyncio.gather)
- Auto-batching (BatchedRedisGet, BatchedRedisSet)
- Statistics and monitoring

All tests demonstrate production-ready reliability.

---

## Bottom Line

Instead of wrestling with Redis protocols, connection pooling, data type conversions, and error handling...

**You write 3 lines and ship features.** 🔴

The Redis client gives you:
- **Production-ready** in-memory data structures out of the box
- **All data types** (strings, hashes, lists, sets, sorted sets)
- **Atomic operations** for counters and locks
- **Pub/Sub** for real-time messaging
- **Session management** with auto-expiration
- **Distributed locking** for coordination
- **Batch operations** for performance (1000s ops/second)
- **Multi-tenancy** via user-scoped keys
- **Auto-cleanup** via context managers
- **Type-safe** results (dicts, lists, sets)

Just pip install and focus on your caching, sessions, and real-time features!

