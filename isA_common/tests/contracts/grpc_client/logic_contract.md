# AsyncBaseGRPCClient Logic Contract

**Business Rules and Specifications for gRPC Client Channel Management**

All tests MUST verify these specifications. This is the SINGLE SOURCE OF TRUTH for gRPC client behavior.

---

## Table of Contents

1. [Business Rules](#business-rules)
2. [State Machines](#state-machines)
3. [Channel Health Rules](#channel-health-rules)
4. [Connection Pool Rules](#connection-pool-rules)
5. [Error Handling](#error-handling)
6. [Performance SLAs](#performance-slas)
7. [Edge Cases](#edge-cases)

---

## Business Rules

### BR-001: Lazy Connection Initialization

**Given**: Client created with `lazy_connect=True` (default)
**When**: Client is instantiated
**Then**:
- No channel created at instantiation time
- `self.channel` is `None`
- `self._connected` is `False`
- First operation triggers connection

**When**: First gRPC operation is called
**Then**:
- `_ensure_connected()` creates channel via global pool
- Stub is created with the channel
- `self._connected` set to `True`

---

### BR-002: Channel Health Check on Operations (THE FIX)

**Given**: Client has `_connected=True` and `channel` is not `None`
**When**: Any gRPC operation is called (via `_ensure_connected`)
**Then**:
- **MUST** check actual channel state (not just `_connected` flag)
- If channel state is `IDLE`, `READY`, or `CONNECTING` → proceed with operation
- If channel state is `SHUTDOWN` or `TRANSIENT_FAILURE` → reconnect before operation

**Current Behavior (BUG)**:
```python
# Current (broken) - only checks flags, not channel health
async def _ensure_connected(self):
    if self._connected and self.channel is not None:
        return  # BUG: Doesn't check if channel is actually healthy!
```

**Expected Behavior (FIX)**:
```python
# Fixed - checks actual channel state
async def _ensure_connected(self):
    if self._connected and self.channel is not None:
        state = self.channel.get_state()
        if state in (IDLE, READY, CONNECTING):
            return  # Channel is healthy
        # Channel is unhealthy, need to reconnect
        logger.warning(f"Channel is {state}, reconnecting...")
        await self.reconnect()
        return
    # ... rest of connection logic
```

---

### BR-003: Global Channel Pool Reuse

**Given**: Multiple clients connecting to same address
**When**: Second client calls `_ensure_connected()`
**Then**:
- Reuses existing channel from `AsyncGlobalChannelPool`
- Reference count incremented
- No new channel created
- Both clients share same underlying connection

**Validation Rules**:
- Channel health checked in pool's `get_channel()` method
- Unhealthy channels are closed and recreated
- Healthy states: `IDLE`, `READY`, `CONNECTING`
- Unhealthy states: `SHUTDOWN`, `TRANSIENT_FAILURE`

---

### BR-004: Channel Release (close)

**Given**: Client with active connection
**When**: `client.close()` is called
**Then**:
- Reference count decremented in global pool
- Channel NOT closed (may be shared)
- `self._connected` set to `False`
- `self.stub` set to `None`
- Other clients using same channel unaffected

---

### BR-005: Force Channel Close

**Given**: Client with active connection
**When**: `client.force_close()` is called
**Then**:
- Channel closed in global pool
- ALL clients sharing this channel affected
- `self._connected` set to `False`
- `self.channel` set to `None`
- `self.stub` set to `None`

**Warning**: Use only when sure no other clients need this connection.

---

### BR-006: Reconnect

**Given**: Client with potentially stale connection
**When**: `client.reconnect()` is called
**Then**:
- Force close current channel
- Create new channel via pool
- Create new stub
- `self._connected` set to `True`

---

## State Machines

### Channel Connectivity State Machine (gRPC Standard)

```
┌──────────┐
│   IDLE   │ ← Initial state, no RPC activity
└────┬─────┘
     │ RPC initiated
     ▼
┌────────────┐
│ CONNECTING │ ← Establishing connection
└─────┬──────┘
      │
      ├────────────────┐
      │ Success        │ Failure (transient)
      ▼                ▼
┌─────────┐      ┌───────────────────┐
│  READY  │      │ TRANSIENT_FAILURE │ ← Retrying
└────┬────┘      └─────────┬─────────┘
     │                     │
     │ Connection lost     │ Give up / Close
     └─────────────────────┼───────────────┐
                           │               │
                           ▼               ▼
                    ┌──────────┐     ┌──────────┐
                    │   IDLE   │     │ SHUTDOWN │ ← Channel closed
                    └──────────┘     └──────────┘
```

**Healthy States** (operations can proceed):
- `IDLE` - Channel created but not active
- `READY` - Channel ready for RPCs
- `CONNECTING` - Channel establishing connection

**Unhealthy States** (need reconnection):
- `SHUTDOWN` - Channel has been closed
- `TRANSIENT_FAILURE` - Channel failed, may retry

---

### Client Connection State Machine

```
┌──────────────┐
│ DISCONNECTED │ ← Initial state (_connected=False, channel=None)
└──────┬───────┘
       │ _ensure_connected() called
       ▼
┌──────────────┐
│  CONNECTING  │ ← Getting channel from pool
└──────┬───────┘
       │ Channel obtained, stub created
       ▼
┌──────────────┐
│  CONNECTED   │ ← Ready for operations (_connected=True)
└──────┬───────┘
       │
       ├─────────────────┬─────────────────┐
       │ close()         │ force_close()   │ Channel unhealthy
       ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ DISCONNECTED │  │ DISCONNECTED │  │ RECONNECTING │
└──────────────┘  └──────────────┘  └──────┬───────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │  CONNECTED   │
                                   └──────────────┘
```

---

## Channel Health Rules

### CH-001: Health Check Conditions

| Condition | Action |
|-----------|--------|
| `_connected=False` | Create new connection |
| `_connected=True, channel=None` | Create new connection |
| `_connected=True, channel.state=IDLE` | Proceed (healthy) |
| `_connected=True, channel.state=READY` | Proceed (healthy) |
| `_connected=True, channel.state=CONNECTING` | Proceed (wait for ready) |
| `_connected=True, channel.state=TRANSIENT_FAILURE` | Reconnect |
| `_connected=True, channel.state=SHUTDOWN` | Reconnect |

### CH-002: Automatic Reconnection

**When**: `_ensure_connected()` detects unhealthy channel
**Then**:
1. Log warning with channel state
2. Call `reconnect()` internally
3. Proceed with operation
4. No exception raised to caller

### CH-003: Proactive Health Check Method

**New Method**: `is_channel_healthy() -> bool`
- Returns `True` if channel is in healthy state
- Returns `False` if channel needs reconnection
- Does NOT trigger reconnection (just checks)

---

## Connection Pool Rules

### CP-001: Pool Singleton

- `AsyncGlobalChannelPool` is a singleton
- All clients share same pool instance
- Thread-safe via asyncio locks

### CP-002: Channel Caching

- Channels keyed by address (`{host}:{port}`)
- Channels reused across all clients to same address
- Reference counting tracks usage

### CP-003: Pool Health Check

The pool's `get_channel()` already checks health:
```python
if address in self._channels:
    channel = self._channels[address]
    state = channel.get_state()
    if state in (IDLE, READY, CONNECTING):
        # Reuse healthy channel
    else:
        # Close and recreate unhealthy channel
```

**Issue**: This check only happens when getting a NEW channel reference, not when a client already holds a reference.

---

## Error Handling

### EH-001: Channel Closed Error

**Error**: `grpc.aio.AioRpcError` with `details="Channel is closed"`
**Cause**: Channel state is `SHUTDOWN` but client still using it
**Solution**: Health check in `_ensure_connected()` prevents this

### EH-002: Connection Refused Error

**Error**: `grpc.aio.AioRpcError` with code `UNAVAILABLE`
**Cause**: Target service not reachable
**Solution**: Propagate error to caller (cannot recover)

### EH-003: Deadline Exceeded Error

**Error**: `grpc.aio.AioRpcError` with code `DEADLINE_EXCEEDED`
**Cause**: RPC took too long
**Solution**: Propagate error to caller

---

## Performance SLAs

### Response Time Targets

| Operation | Target | Max Acceptable |
|-----------|--------|----------------|
| `_ensure_connected()` (cached) | < 1ms | < 5ms |
| `_ensure_connected()` (new connection) | < 100ms | < 500ms |
| `reconnect()` | < 200ms | < 1s |
| Health check | < 1ms | < 5ms |

### Throughput Targets

- Concurrent operations per channel: 1000+
- Channel pool size: Unbounded (one per unique address)
- Operations before health check overhead: 0 (check is O(1))

---

## Edge Cases

### EC-001: Channel Closes During Operation

**Scenario**: Channel becomes `SHUTDOWN` while RPC in flight
**Expected**: RPC fails with `Channel is closed` error
**Solution**: Caller should retry with new connection

---

### EC-002: Concurrent Reconnections

**Scenario**: Multiple coroutines detect unhealthy channel simultaneously
**Expected**: Only one reconnection happens
**Solution**: `_connect_lock` ensures single reconnection

---

### EC-003: Keepalive Timeout

**Scenario**: Channel idle for extended period, server closes connection
**Current Settings**:
```python
'grpc.keepalive_time_ms': 60000           # 60s between pings
'grpc.keepalive_timeout_ms': 20000        # 20s timeout
'grpc.keepalive_permit_without_calls': 0  # Don't ping when idle
```
**Issue**: `permit_without_calls=0` means idle channels are NOT kept alive
**Result**: Server may close connection, channel becomes `SHUTDOWN`
**Solution**: Health check on `_ensure_connected()` detects and reconnects

---

### EC-004: Service Restart

**Scenario**: Target gRPC service restarts
**Expected**: Existing channels become `TRANSIENT_FAILURE` or `SHUTDOWN`
**Solution**: Health check detects and reconnects

---

### EC-005: Network Partition

**Scenario**: Network connectivity lost temporarily
**Expected**: Channel becomes `TRANSIENT_FAILURE`
**Solution**: Health check triggers reconnect when network restored

---

## Test Coverage Requirements

All tests MUST cover:

- [ ] BR-002: Channel health check on `_ensure_connected()` (THE FIX)
- [ ] Healthy channel states (IDLE, READY, CONNECTING) → proceed
- [ ] Unhealthy channel states (SHUTDOWN, TRANSIENT_FAILURE) → reconnect
- [ ] Concurrent reconnection safety
- [ ] Channel pool reuse behavior
- [ ] `is_channel_healthy()` method
- [ ] EC-003: Keepalive timeout recovery

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
**Owner**: Infrastructure Team
