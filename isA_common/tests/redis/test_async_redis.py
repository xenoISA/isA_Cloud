#!/usr/bin/env python3
"""
Async Redis Client - Comprehensive Functional Tests

Tests all async Redis operations including:
- String operations (SET, GET, DELETE, APPEND)
- Batch operations (MSET, MGET) - using optimized ExecuteBatch
- Counter operations (INCR, DECR)
- Hash operations
- List operations
- Set operations
- Sorted Set operations
- Distributed Locks
- Pub/Sub
- Session Management
- Concurrent operations (asyncio.gather)
- Auto-batching (BatchedRedisGet, BatchedRedisSet)

Usage:
    python test_async_redis.py
    HOST=redis-service PORT=50055 python test_async_redis.py
"""

import os
import sys
import asyncio
import time
from typing import Dict, List, Optional

# Add parent path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from isa_common import AsyncRedisClient, BatchedRedisGet, BatchedRedisSet

# Configuration
HOST = os.environ.get('HOST', 'localhost')
PORT = int(os.environ.get('PORT', '6379'))
USER_ID = os.environ.get('USER_ID', 'test_user')

# Test results
PASSED = 0
FAILED = 0
TOTAL = 0


def test_result(success: bool, test_name: str):
    """Record test result."""
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    if success:
        PASSED += 1
        print(f"  ✓ PASSED: {test_name}")
    else:
        FAILED += 1
        print(f"  ✗ FAILED: {test_name}")


async def test_health_check(client: AsyncRedisClient) -> bool:
    """Test 1: Service Health Check"""
    try:
        health = await client.health_check()
        success = health is not None and health.get('healthy', False)
        test_result(success, "Health check")
        return success
    except Exception as e:
        test_result(False, f"Health check - {e}")
        return False


async def test_string_operations(client: AsyncRedisClient):
    """Test 2: String SET/GET/DELETE Operations"""
    try:
        # SET
        success = await client.set('async:test:key1', 'value1')
        if not success:
            test_result(False, "String SET")
            return

        # GET
        val = await client.get('async:test:key1')
        if val != 'value1':
            test_result(False, f"String GET - got {val}")
            return

        # EXISTS
        exists = await client.exists('async:test:key1')
        if not exists:
            test_result(False, "String EXISTS")
            return

        # DELETE
        deleted = await client.delete('async:test:key1')
        if not deleted:
            test_result(False, "String DELETE")
            return

        # Verify deleted
        exists = await client.exists('async:test:key1')
        if exists:
            test_result(False, "String DELETE verification")
            return

        test_result(True, "String operations (SET/GET/EXISTS/DELETE)")
    except Exception as e:
        test_result(False, f"String operations - {e}")


async def test_ttl_expiration(client: AsyncRedisClient):
    """Test 3: TTL and Expiration"""
    try:
        # Set with TTL
        await client.set_with_ttl('async:test:expire', 'temp_value', 2)

        # Check TTL
        ttl = await client.ttl('async:test:expire')
        if ttl is None or ttl <= 0 or ttl > 2:
            test_result(False, f"TTL check - got {ttl}")
            return

        # Wait for expiration
        await asyncio.sleep(3)

        # Verify expired
        exists = await client.exists('async:test:expire')
        if exists:
            test_result(False, "Key not expired")
            return

        test_result(True, "TTL and expiration")
    except Exception as e:
        test_result(False, f"TTL and expiration - {e}")


async def test_batch_operations(client: AsyncRedisClient):
    """Test 4: Batch MSET/MGET Operations (using ExecuteBatch)"""
    try:
        # MSET - now uses single ExecuteBatch RPC
        data = {
            'async:test:batch1': 'val1',
            'async:test:batch2': 'val2',
            'async:test:batch3': 'val3'
        }
        success = await client.mset(data)
        if not success:
            test_result(False, "Batch MSET")
            return

        # MGET
        vals = await client.mget(['async:test:batch1', 'async:test:batch2', 'async:test:batch3'])
        if len(vals) != 3:
            test_result(False, f"Batch MGET - got {len(vals)} values")
            return

        test_result(True, "Batch operations (MSET/MGET)")
    except Exception as e:
        test_result(False, f"Batch operations - {e}")


async def test_counter_operations(client: AsyncRedisClient):
    """Test 5: INCR/DECR Counter Operations"""
    try:
        # Clean up first
        await client.delete('async:test:counter')

        # INCR
        val = await client.incr('async:test:counter', 1)
        if val != 1:
            test_result(False, f"INCR - got {val}")
            return

        # INCR by 5
        val = await client.incr('async:test:counter', 5)
        if val != 6:
            test_result(False, f"INCR+5 - got {val}")
            return

        # DECR
        val = await client.decr('async:test:counter', 2)
        if val != 4:
            test_result(False, f"DECR - got {val}")
            return

        test_result(True, "Counter operations (INCR/DECR)")
    except Exception as e:
        test_result(False, f"Counter operations - {e}")


async def test_hash_operations(client: AsyncRedisClient):
    """Test 6: Hash Operations"""
    try:
        # HSET
        success = await client.hset('async:test:hash', 'field1', 'value1')
        if not success:
            test_result(False, "HSET")
            return

        await client.hset('async:test:hash', 'field2', 'value2')

        # HGET
        val = await client.hget('async:test:hash', 'field1')
        if val != 'value1':
            test_result(False, f"HGET - got {val}")
            return

        # HGETALL
        all_fields = await client.hgetall('async:test:hash')
        if len(all_fields) < 2:
            test_result(False, f"HGETALL - got {len(all_fields)} fields")
            return

        # HEXISTS
        exists = await client.hexists('async:test:hash', 'field1')
        if not exists:
            test_result(False, "HEXISTS")
            return

        # HDELETE
        count = await client.hdelete('async:test:hash', ['field1'])
        if count != 1:
            test_result(False, f"HDELETE - deleted {count}")
            return

        test_result(True, "Hash operations (HSET/HGET/HGETALL/HEXISTS/HDELETE)")
    except Exception as e:
        test_result(False, f"Hash operations - {e}")


async def test_list_operations(client: AsyncRedisClient):
    """Test 7: List Operations"""
    try:
        # Clean up
        await client.delete('async:test:list')

        # LPUSH
        length = await client.lpush('async:test:list', ['a', 'b'])
        if length < 2:
            test_result(False, f"LPUSH - length {length}")
            return

        # RPUSH
        length = await client.rpush('async:test:list', ['c', 'd'])
        if length < 4:
            test_result(False, f"RPUSH - length {length}")
            return

        # LRANGE
        items = await client.lrange('async:test:list', 0, -1)
        if len(items) != 4:
            test_result(False, f"LRANGE - got {len(items)} items")
            return

        # LLEN
        length = await client.llen('async:test:list')
        if length != 4:
            test_result(False, f"LLEN - got {length}")
            return

        # LPOP
        val = await client.lpop('async:test:list')
        if val is None:
            test_result(False, "LPOP")
            return

        # RPOP
        val = await client.rpop('async:test:list')
        if val is None:
            test_result(False, "RPOP")
            return

        test_result(True, "List operations (LPUSH/RPUSH/LRANGE/LLEN/LPOP/RPOP)")
    except Exception as e:
        test_result(False, f"List operations - {e}")


async def test_set_operations(client: AsyncRedisClient):
    """Test 8: Set Operations"""
    try:
        # Clean up
        await client.delete('async:test:set1')
        await client.delete('async:test:set2')

        # SADD
        count = await client.sadd('async:test:set1', ['a', 'b', 'c'])
        if count != 3:
            test_result(False, f"SADD - added {count}")
            return

        await client.sadd('async:test:set2', ['b', 'c', 'd'])

        # SISMEMBER
        is_member = await client.sismember('async:test:set1', 'a')
        if not is_member:
            test_result(False, "SISMEMBER")
            return

        # SCARD
        count = await client.scard('async:test:set1')
        if count != 3:
            test_result(False, f"SCARD - got {count}")
            return

        # SMEMBERS
        members = await client.smembers('async:test:set1')
        if len(members) != 3:
            test_result(False, f"SMEMBERS - got {len(members)}")
            return

        test_result(True, "Set operations (SADD/SISMEMBER/SCARD/SMEMBERS)")
    except Exception as e:
        test_result(False, f"Set operations - {e}")


async def test_sorted_set_operations(client: AsyncRedisClient):
    """Test 9: Sorted Set Operations"""
    try:
        # Clean up
        await client.delete('async:test:zset')

        # ZADD
        count = await client.zadd('async:test:zset', {'player1': 100, 'player2': 200, 'player3': 150})
        if count != 3:
            test_result(False, f"ZADD - added {count}")
            return

        # ZCARD
        count = await client.zcard('async:test:zset')
        if count != 3:
            test_result(False, f"ZCARD - got {count}")
            return

        # ZSCORE
        score = await client.zscore('async:test:zset', 'player2')
        if score != 200:
            test_result(False, f"ZSCORE - got {score}")
            return

        # ZRANK
        rank = await client.zrank('async:test:zset', 'player2')
        if rank is None:
            test_result(False, "ZRANK")
            return

        # ZRANGE
        members = await client.zrange('async:test:zset', 0, -1)
        if len(members) != 3:
            test_result(False, f"ZRANGE - got {len(members)}")
            return

        test_result(True, "Sorted set operations (ZADD/ZCARD/ZSCORE/ZRANK/ZRANGE)")
    except Exception as e:
        test_result(False, f"Sorted set operations - {e}")


async def test_lock_operations(client: AsyncRedisClient):
    """Test 10: Distributed Lock Operations"""
    try:
        # Acquire lock
        lock_id = await client.acquire_lock('async:test:lock', ttl_seconds=10)
        if not lock_id:
            test_result(False, "Acquire lock")
            return

        # Renew lock
        renewed = await client.renew_lock('async:test:lock', lock_id, ttl_seconds=10)
        if not renewed:
            test_result(False, "Renew lock")
            return

        # Release lock
        released = await client.release_lock('async:test:lock', lock_id)
        if not released:
            test_result(False, "Release lock")
            return

        # Verify release by re-acquiring
        lock_id2 = await client.acquire_lock('async:test:lock', ttl_seconds=5)
        if not lock_id2:
            test_result(False, "Re-acquire lock after release")
            return

        await client.release_lock('async:test:lock', lock_id2)
        test_result(True, "Distributed lock operations (ACQUIRE/RENEW/RELEASE)")
    except Exception as e:
        test_result(False, f"Lock operations - {e}")


async def test_pubsub_publish(client: AsyncRedisClient):
    """Test 11: Pub/Sub Publish"""
    try:
        # Publish (subscribers count may be 0)
        count = await client.publish('async:test:channel', 'Hello World')
        if count is None:
            test_result(False, "Publish returned None")
            return

        test_result(True, "Pub/Sub publish")
    except Exception as e:
        test_result(False, f"Pub/Sub publish - {e}")


async def test_session_management(client: AsyncRedisClient):
    """Test 12: Session Management"""
    try:
        # Create session
        session_id = await client.create_session({'user': 'john', 'role': 'admin'}, ttl_seconds=3600)
        if not session_id:
            test_result(False, "Create session")
            return

        await asyncio.sleep(0.2)  # Give server time

        # Delete session
        deleted = await client.delete_session(session_id)

        test_result(True, "Session management (CREATE/DELETE)")
    except Exception as e:
        test_result(False, f"Session management - {e}")


async def test_concurrent_operations(client: AsyncRedisClient):
    """Test 13: Concurrent Operations with asyncio.gather"""
    try:
        # Setup keys
        await client.mset({
            'async:test:concurrent1': 'val1',
            'async:test:concurrent2': 'val2',
            'async:test:concurrent3': 'val3'
        })

        # Concurrent GET using asyncio.gather
        start = time.time()
        results = await asyncio.gather(
            client.get('async:test:concurrent1'),
            client.get('async:test:concurrent2'),
            client.get('async:test:concurrent3'),
            client.get('async:test:concurrent1'),
            client.get('async:test:concurrent2'),
        )
        elapsed = time.time() - start

        if len(results) != 5:
            test_result(False, f"Concurrent GET - got {len(results)} results")
            return

        if results[0] != 'val1' or results[1] != 'val2':
            test_result(False, "Concurrent GET - values mismatch")
            return

        test_result(True, f"Concurrent operations (5 GETs in {elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent operations - {e}")


async def test_get_many_concurrent(client: AsyncRedisClient):
    """Test 14: get_many_concurrent helper"""
    try:
        # Setup keys
        await client.mset({
            'async:test:many1': 'val1',
            'async:test:many2': 'val2',
            'async:test:many3': 'val3'
        })

        # Use helper method
        results = await client.get_many_concurrent([
            'async:test:many1',
            'async:test:many2',
            'async:test:many3'
        ])

        if len(results) != 3:
            test_result(False, f"get_many_concurrent - got {len(results)} results")
            return

        if results.get('async:test:many1') != 'val1':
            test_result(False, "get_many_concurrent - value mismatch")
            return

        test_result(True, "get_many_concurrent helper")
    except Exception as e:
        test_result(False, f"get_many_concurrent - {e}")


async def test_auto_batching_get(client: AsyncRedisClient):
    """Test 15: Auto-batching with BatchedRedisGet"""
    try:
        # Setup keys
        await client.mset({
            'async:test:auto1': 'val1',
            'async:test:auto2': 'val2',
            'async:test:auto3': 'val3'
        })

        # Create batched getter
        batched_get = BatchedRedisGet(client, max_size=100, max_wait_ms=10)

        # These concurrent gets should be automatically batched
        start = time.time()
        results = await asyncio.gather(
            batched_get.get('async:test:auto1'),
            batched_get.get('async:test:auto2'),
            batched_get.get('async:test:auto3'),
        )
        elapsed = time.time() - start

        if len(results) != 3:
            test_result(False, f"Auto-batch GET - got {len(results)} results")
            return

        if results[0] != 'val1':
            test_result(False, f"Auto-batch GET - value mismatch: {results[0]}")
            return

        test_result(True, f"Auto-batching GET (3 keys batched, {elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"Auto-batching GET - {e}")


async def test_auto_batching_set(client: AsyncRedisClient):
    """Test 16: Auto-batching with BatchedRedisSet"""
    try:
        # Create batched setter
        batched_set = BatchedRedisSet(client, max_size=100, max_wait_ms=10)

        # These concurrent sets should be automatically batched
        start = time.time()
        results = await asyncio.gather(
            batched_set.set('async:test:autoset1', 'val1'),
            batched_set.set('async:test:autoset2', 'val2'),
            batched_set.set('async:test:autoset3', 'val3'),
        )
        elapsed = time.time() - start

        # Verify values were set
        vals = await client.mget(['async:test:autoset1', 'async:test:autoset2', 'async:test:autoset3'])
        if len(vals) != 3:
            test_result(False, f"Auto-batch SET verification - got {len(vals)}")
            return

        test_result(True, f"Auto-batching SET (3 keys batched, {elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"Auto-batching SET - {e}")


async def test_execute_batch(client: AsyncRedisClient):
    """Test 17: Execute Batch Commands"""
    try:
        commands = [
            {'operation': 'SET', 'key': 'async:test:batch_exec1', 'value': 'val1'},
            {'operation': 'SET', 'key': 'async:test:batch_exec2', 'value': 'val2', 'expiration': 300},
        ]
        result = await client.execute_batch(commands)

        if not result or not result.get('success'):
            test_result(False, "Execute batch")
            return

        # Verify
        val = await client.get('async:test:batch_exec1')
        if val != 'val1':
            test_result(False, f"Execute batch verification - got {val}")
            return

        test_result(True, "Execute batch commands")
    except Exception as e:
        test_result(False, f"Execute batch - {e}")


async def test_statistics(client: AsyncRedisClient):
    """Test 18: Get Statistics"""
    try:
        stats = await client.get_statistics()
        if not stats or 'total_keys' not in stats:
            test_result(False, "Get statistics")
            return

        test_result(True, "Get statistics")
    except Exception as e:
        test_result(False, f"Get statistics - {e}")


async def cleanup(client: AsyncRedisClient):
    """Cleanup test keys."""
    print("\nCleaning up test keys...")
    keys = await client.list_keys('async:test:*', 1000)
    if keys:
        await client.delete_multiple(keys)


async def main():
    """Run all async tests."""
    print("=" * 70)
    print("     ASYNC REDIS CLIENT - COMPREHENSIVE FUNCTIONAL TESTS")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER_ID}")
    print()

    async with AsyncRedisClient(
        host=HOST,
        port=PORT,
        user_id=USER_ID,
        organization_id='test-org'
    ) as client:
        # Initial cleanup
        await cleanup(client)

        # Health check (required)
        print("\n--- Health Check ---")
        healthy = await test_health_check(client)
        if not healthy:
            print("\n✗ Cannot proceed without healthy service")
            return 1

        # Core operations
        print("\n--- String Operations ---")
        await test_string_operations(client)
        await test_ttl_expiration(client)

        print("\n--- Batch Operations ---")
        await test_batch_operations(client)

        print("\n--- Counter Operations ---")
        await test_counter_operations(client)

        print("\n--- Hash Operations ---")
        await test_hash_operations(client)

        print("\n--- List Operations ---")
        await test_list_operations(client)

        print("\n--- Set Operations ---")
        await test_set_operations(client)

        print("\n--- Sorted Set Operations ---")
        await test_sorted_set_operations(client)

        print("\n--- Distributed Lock Operations ---")
        await test_lock_operations(client)

        print("\n--- Pub/Sub Operations ---")
        await test_pubsub_publish(client)

        print("\n--- Session Management ---")
        await test_session_management(client)

        print("\n--- Concurrent Operations ---")
        await test_concurrent_operations(client)
        await test_get_many_concurrent(client)

        print("\n--- Auto-Batching Operations ---")
        await test_auto_batching_get(client)
        await test_auto_batching_set(client)

        print("\n--- Batch Execute ---")
        await test_execute_batch(client)

        print("\n--- Statistics ---")
        await test_statistics(client)

        # Cleanup
        await cleanup(client)

    # Summary
    print("\n" + "=" * 70)
    print("                         TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {TOTAL}")
    print(f"Passed: {PASSED}")
    print(f"Failed: {FAILED}")
    if TOTAL > 0:
        print(f"Success Rate: {PASSED/TOTAL*100:.1f}%")
    print()

    if FAILED == 0:
        print(f"✓ ALL TESTS PASSED! ({PASSED}/{TOTAL})")
        return 0
    else:
        print(f"✗ SOME TESTS FAILED ({PASSED}/{TOTAL})")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
