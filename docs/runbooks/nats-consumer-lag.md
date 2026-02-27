# Runbook: NATS Consumer Lag / Billing Event Delays

## Symptoms

- Billing records not appearing after model invocations
- Growing gap between usage events published and billing records created
- Logs show repeated `NATS pull messages failed` or `connection closed` errors
- Health check shows `consecutive_errors > 0` or high `reconnect_count`

## Quick Health Check

```bash
# Check billing consumer health (from billing_service)
curl -s http://localhost:8225/health | jq '.nats'

# Check NATS server health
nats server check connection --server nats://localhost:4222

# Check stream info and consumer lag
nats stream info USAGE_EVENTS --server nats://localhost:4222
nats consumer info USAGE_EVENTS billing-consumer --server nats://localhost:4222
```

Key metrics to check:
- **Unprocessed Messages**: `num_pending` in consumer info (should be near 0)
- **Redeliveries**: `num_redelivered` (high value = processing failures)
- **Ack Floor**: `ack_floor` vs stream's last sequence (gap = lag)

## Common Failure Modes

### 1. Consumer disconnected / reconnect loop

**Symptoms**: Logs show `NATS disconnected` followed by `NATS reconnected` repeatedly.

**Diagnosis**:
```bash
# Check health endpoint for reconnect stats
curl -s http://localhost:8225/health | jq '{
  reconnect_count: .nats.reconnect_count,
  consecutive_errors: .nats.consecutive_errors,
  total_messages_pulled: .nats.total_messages_pulled
}'
```

**Resolution**:
1. Check NATS server is healthy: `nats server check connection`
2. Check network between consumer pod and NATS: `nats rtt`
3. If NATS server restarted, consumer should auto-recover (exponential backoff in consumer loop)
4. If stuck, restart billing_service pod

### 2. Messages published but not consumed

**Symptoms**: Stream message count grows, consumer `num_pending` grows.

**Diagnosis**:
```bash
# Compare stream last seq vs consumer ack floor
nats stream info USAGE_EVENTS -j | jq '.state.last_seq'
nats consumer info USAGE_EVENTS billing-consumer -j | jq '.ack_floor.stream_seq'
```

**Resolution**:
1. Check consumer is running: look for `Starting consumer` log in billing_service
2. Check for handler errors: `grep "Error processing message" billing_service.log`
3. If consumer is stuck on a poison message, check `num_redelivered` count
4. Last resort: delete and recreate consumer (messages will replay from stream)

### 3. Ack failures

**Symptoms**: `total_ack_failures` incrementing in health check, messages redelivered.

**Diagnosis**: Ack failures usually mean the NATS connection dropped between fetch and ack.

**Resolution**:
1. Messages are auto-acked after fetch; handlers are idempotent
2. Redelivered messages will be processed again (at-least-once delivery)
3. If ack failures are sustained, check NATS server stability

### 4. High latency between publish and consume

**Symptoms**: Billing records created with delay, but eventually consistent.

**Diagnosis**:
```bash
# Check consumer loop timing
grep "total_processed=" billing_service.log | tail -5
```

**Resolution**:
1. Check consumer batch size (default 10) and poll interval
2. If consumer loop is in backoff (error recovery), wait for it to reset
3. Scale billing consumers horizontally if throughput is the bottleneck

## Preventive Monitoring

### Alerts to set up
- `num_pending > 1000` for more than 5 minutes
- `consecutive_errors > 10` in health check
- `reconnect_count` increasing faster than 1/minute

### Periodic checks
- Weekly: review `total_ack_failures` trend
- After deployments: verify consumer reconnects and catches up within 60s

## Recovery Procedure

If billing consumer is completely stuck:

1. **Check NATS server**: `nats server check connection`
2. **Check stream exists**: `nats stream ls`
3. **Check consumer exists**: `nats consumer ls USAGE_EVENTS`
4. **Restart billing_service**: Consumer will reconnect and resume from last ack position
5. **If consumer state is corrupted**: Delete consumer (`nats consumer rm USAGE_EVENTS billing-consumer`) and restart — it will be recreated and replay from stream
