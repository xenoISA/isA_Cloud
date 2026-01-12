# MQTT Service - Logic Contract

> Business Rules and Edge Cases for MQTT gRPC Service (IoT Messaging)

---

## Overview

This document defines the business rules for the MQTT gRPC service, covering topic-based publish/subscribe for IoT and device messaging.

---

## Business Rules

### BR-001: Multi-Tenant Topic Isolation

**Description**: Topics are isolated by organization through prefix.

**Given**: A user publishes/subscribes to a topic
**When**: Topic operation is performed
**Then**:
- Topic prefixed with `{org_id}/`
- Cannot subscribe to other org's topics
- Audit log records isolated topic

**Examples**:

| Input Topic | Org ID | Isolated Topic |
|-------------|--------|----------------|
| `devices/temp` | `org-001` | `org-001/devices/temp` |
| `sensors/#` | `org-002` | `org-002/sensors/#` |

**Test Cases**:
- `TestPublish_BR001_TopicPrefixedWithOrgId`
- `TestSubscribe_BR001_CannotAccessOtherOrgTopics`

---

### BR-002: Topic Wildcards

**Description**: MQTT supports single-level (+) and multi-level (#) wildcards.

**Given**: A subscription with wildcards
**When**: Messages are published
**Then**:
- `+` matches exactly one level
- `#` matches zero or more levels (must be last)
- Wildcards only in subscriptions, not publish

**Wildcard Examples**:

| Subscription | Matches | Does Not Match |
|--------------|---------|----------------|
| `devices/+/temp` | `devices/001/temp` | `devices/001/002/temp` |
| `devices/#` | `devices/001/temp`, `devices` | `sensors/temp` |
| `+/+/temp` | `a/b/temp` | `a/temp`, `a/b/c/temp` |

**Test Cases**:
- `TestSubscribe_BR002_SingleLevelWildcardMatches`
- `TestSubscribe_BR002_MultiLevelWildcardMatches`
- `TestPublish_BR002_WildcardsNotAllowedInPublish`

---

### BR-003: Quality of Service (QoS)

**Description**: Three QoS levels for delivery guarantees.

**Given**: A message is published with QoS level
**When**: Delivery occurs
**Then**:
- QoS 0: At most once (fire and forget)
- QoS 1: At least once (may duplicate)
- QoS 2: Exactly once (guaranteed)

**QoS Comparison**:

| QoS | Guarantee | Use Case |
|-----|-----------|----------|
| 0 | Best effort | Telemetry, non-critical |
| 1 | Delivered | Commands, alerts |
| 2 | Exactly once | Financial, critical |

**Test Cases**:
- `TestPublish_BR003_QoS0FireAndForget`
- `TestPublish_BR003_QoS1AtLeastOnce`
- `TestPublish_BR003_QoS2ExactlyOnce`

---

### BR-004: Retained Messages

**Description**: Retained messages are stored and delivered to new subscribers.

**Given**: A message is published with retain flag
**When**: New subscriber connects
**Then**:
- Subscriber receives last retained message immediately
- Only one retained message per topic
- Empty payload clears retained message

**Test Cases**:
- `TestPublish_BR004_RetainedMessageStoredForTopic`
- `TestSubscribe_BR004_NewSubscriberReceivesRetained`
- `TestPublish_BR004_EmptyPayloadClearsRetained`

---

### BR-005: Last Will and Testament (LWT)

**Description**: Configured message published when client disconnects unexpectedly.

**Given**: A client connects with LWT configured
**When**: Client disconnects unexpectedly
**Then**:
- LWT message published to specified topic
- LWT respects QoS and retain settings
- Clean disconnect does NOT trigger LWT

**Test Cases**:
- `TestConnect_BR005_LWTPublishedOnUnexpectedDisconnect`
- `TestDisconnect_BR005_CleanDisconnectNoLWT`

---

### BR-006: Message Payload

**Description**: Messages can contain binary or text payload.

**Given**: A message payload
**When**: Publish is called
**Then**:
- Payload treated as binary (bytes)
- No size limit enforced by gRPC service
- Underlying broker may have limits

**Test Cases**:
- `TestPublish_BR006_BinaryPayloadSupported`
- `TestPublish_BR006_JSONPayloadSupported`

---

### BR-007: Audit Logging

**Description**: All operations logged for audit trail.

**Given**: Any operation is performed
**When**: Operation completes
**Then**:
- Audit log sent to Loki
- Includes: timestamp, user_id, org_id, operation, topic
- Payload NOT logged (may contain sensitive data)

**Test Cases**:
- `TestPublish_BR007_AuditLogRecorded`
- `TestSubscribe_BR007_AuditLogRecorded`

---

## Edge Cases

### EC-001: Empty Topic

**Given**: User provides empty topic string
**When**: Publish/Subscribe is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC001_EmptyTopicReturnsError`

---

### EC-002: Invalid Topic Characters

**Given**: Topic contains null character or invalid UTF-8
**When**: Publish is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC002_InvalidTopicReturnsError`

---

### EC-003: Topic Too Long

**Given**: Topic exceeds maximum length (65535 bytes)
**When**: Publish is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC003_TopicTooLongReturnsError`

---

### EC-004: Invalid QoS Level

**Given**: QoS not 0, 1, or 2
**When**: Publish is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC004_InvalidQoSReturnsError`

---

### EC-005: Wildcard in Publish Topic

**Given**: Publish topic contains + or #
**When**: Publish is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC005_WildcardInPublishReturnsError`

---

### EC-006: Broker Unavailable

**Given**: MQTT broker is down
**When**: Any operation is called
**Then**: Returns Unavailable error

**Test Cases**:
- `TestPublish_EC006_BrokerUnavailableReturnsError`

---

### EC-007: Connection Timeout

**Given**: Broker does not respond
**When**: Connect/Publish times out
**Then**: Returns DeadlineExceeded error

**Test Cases**:
- `TestPublish_EC007_TimeoutReturnsDeadlineExceeded`

---

## Error Handling Rules

### ER-001: Error Response Mapping

| MQTT Error | gRPC Code | Message |
|------------|-----------|---------|
| Invalid topic | `InvalidArgument` | "invalid topic" |
| Invalid QoS | `InvalidArgument` | "invalid QoS level" |
| Not connected | `FailedPrecondition` | "not connected" |
| Connection refused | `PermissionDenied` | "connection refused" |
| Broker unavailable | `Unavailable` | "broker unavailable" |
| Timeout | `DeadlineExceeded` | "operation timeout" |

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| Publish QoS 0 | < 5ms | No ack required |
| Publish QoS 1 | < 20ms | Wait for PUBACK |
| Publish QoS 2 | < 50ms | Full handshake |
| Subscribe | < 20ms | |
| Unsubscribe | < 20ms | |
| Message delivery | < 10ms | After publish |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
