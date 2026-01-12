# NATS Service - Logic Contract

> Business Rules and Edge Cases for NATS gRPC Service

---

## Overview

This document defines the business rules for the NATS gRPC service, covering Pub/Sub, JetStream, and Key-Value store operations.

---

## Business Rules

### BR-001: Subject-Based Publish/Subscribe

**Description**: Messages are routed based on subject patterns.

**Given**: A publisher sends a message to a subject
**When**: Publish is called
**Then**:
- Message delivered to all matching subscribers
- Wildcards supported (`*` single token, `>` multiple tokens)
- No persistence (fire-and-forget for core NATS)

**Subject Patterns**:

| Subject | Matches | Does Not Match |
|---------|---------|----------------|
| `orders.created` | Exact match | `orders.updated` |
| `orders.*` | `orders.created`, `orders.updated` | `orders.us.created` |
| `orders.>` | `orders.created`, `orders.us.east.created` | `inventory.updated` |

**Test Cases**:
- `TestPublish_BR001_MessageDeliveredToSubscribers`
- `TestPublish_BR001_WildcardSingleTokenMatches`
- `TestPublish_BR001_WildcardMultiTokenMatches`

---

### BR-002: Multi-Tenant Subject Isolation

**Description**: Subjects are prefixed with organization ID for isolation.

**Given**: A user publishes/subscribes
**When**: Subject is used
**Then**:
- Subject prefixed with `{org_id}.`
- Cannot subscribe to other org's subjects
- Audit log records isolated subject

**Examples**:

| Input Subject | Org ID | Isolated Subject |
|---------------|--------|------------------|
| `orders.created` | `org-001` | `org-001.orders.created` |
| `events.>` | `org-002` | `org-002.events.>` |

**Test Cases**:
- `TestPublish_BR002_SubjectPrefixedWithOrgId`
- `TestSubscribe_BR002_CannotAccessOtherOrgSubjects`

---

### BR-003: JetStream Persistence

**Description**: JetStream provides persistent message storage with delivery guarantees.

**Given**: A stream is configured
**When**: Messages are published
**Then**:
- Messages persisted to stream
- Consumers can replay from any point
- At-least-once delivery guaranteed

**Stream Configuration**:
```
Stream: ORDERS
├── Subjects: ["orders.>"]
├── Retention: Limits (max messages/bytes/age)
├── Storage: File or Memory
└── Replicas: 1 (staging), 3 (production)
```

**Test Cases**:
- `TestJetStream_BR003_MessagesPersistedToStream`
- `TestJetStream_BR003_ConsumerCanReplayFromSequence`
- `TestJetStream_BR003_AtLeastOnceDelivery`

---

### BR-004: Consumer Acknowledgment

**Description**: Consumers must acknowledge messages for reliable delivery.

**Given**: A consumer receives a message
**When**: Processing completes
**Then**:
- Ack: Message marked as delivered
- Nak: Message redelivered after delay
- InProgress: Extends ack deadline
- Term: Message will not be redelivered

**State Diagram**:
```
┌──────────────┐    Deliver    ┌──────────────┐
│   Pending    │ ────────────▶ │  Delivered   │
└──────────────┘               └──────┬───────┘
       ▲                              │
       │                    ┌─────────┼─────────┐
       │                    ▼         ▼         ▼
       │              ┌────────┐ ┌────────┐ ┌────────┐
       │              │  Ack   │ │  Nak   │ │  Term  │
       │              └───┬────┘ └───┬────┘ └───┬────┘
       │                  │          │          │
       │                  ▼          │          ▼
       │           ┌──────────┐      │   ┌──────────┐
       │           │ Complete │      │   │ Discarded│
       │           └──────────┘      │   └──────────┘
       └─────────────────────────────┘
              (redeliver after delay)
```

**Test Cases**:
- `TestConsumer_BR004_AckRemovesMessageFromPending`
- `TestConsumer_BR004_NakCausesRedelivery`
- `TestConsumer_BR004_TermPreventsRedelivery`

---

### BR-005: Key-Value Store

**Description**: NATS KV provides distributed key-value storage.

**Given**: A KV bucket exists
**When**: Put/Get/Delete operations are called
**Then**:
- Keys isolated by organization
- Revision tracking for optimistic concurrency
- Watch for real-time key changes

**Test Cases**:
- `TestKV_BR005_PutAndGetKey`
- `TestKV_BR005_RevisionIncrementedOnUpdate`
- `TestKV_BR005_WatchReceivesUpdates`
- `TestKV_BR005_KeysIsolatedByOrg`

---

### BR-006: Request-Reply Pattern

**Description**: Synchronous request-reply over NATS.

**Given**: A service is listening on a subject
**When**: Request is sent
**Then**:
- Responder receives request with reply subject
- Response sent to unique reply subject
- Timeout if no response

**Test Cases**:
- `TestRequest_BR006_ReceivesResponse`
- `TestRequest_BR006_TimeoutOnNoResponse`

---

## Edge Cases

### EC-001: Empty Subject

**Given**: User provides empty subject
**When**: Publish/Subscribe is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC001_EmptySubjectReturnsError`

---

### EC-002: Invalid Subject Characters

**Given**: Subject contains invalid characters (spaces, etc.)
**When**: Publish is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC002_InvalidSubjectReturnsError`

---

### EC-003: Message Too Large

**Given**: Message exceeds max size (default 1MB)
**When**: Publish is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPublish_EC003_OversizedMessageReturnsError`

---

### EC-004: Stream Does Not Exist

**Given**: JetStream stream not created
**When**: Publish to stream subject
**Then**: Returns NotFound error

**Test Cases**:
- `TestJetStream_EC004_NonExistentStreamReturnsError`

---

### EC-005: Consumer Does Not Exist

**Given**: Consumer name not found
**When**: Pull messages
**Then**: Returns NotFound error

**Test Cases**:
- `TestConsumer_EC005_NonExistentConsumerReturnsError`

---

### EC-006: KV Bucket Does Not Exist

**Given**: KV bucket not created
**When**: Get/Put is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestKV_EC006_NonExistentBucketReturnsError`

---

### EC-007: Duplicate Durable Consumer

**Given**: Durable consumer already exists with different config
**When**: Create consumer with same name
**Then**: Returns AlreadyExists error

**Test Cases**:
- `TestConsumer_EC007_DuplicateDurableReturnsError`

---

### EC-008: NATS Unavailable

**Given**: NATS server is down
**When**: Any operation is called
**Then**: Returns Unavailable error

**Test Cases**:
- `TestPublish_EC008_NatsUnavailableReturnsError`

---

## Error Handling Rules

### ER-001: Error Response Mapping

| NATS Error | gRPC Code | Message |
|------------|-----------|---------|
| Invalid subject | `InvalidArgument` | "invalid subject" |
| Stream not found | `NotFound` | "stream not found" |
| Consumer not found | `NotFound` | "consumer not found" |
| Bucket not found | `NotFound` | "bucket not found" |
| Message too large | `InvalidArgument` | "message exceeds max size" |
| Connection error | `Unavailable` | "nats unavailable" |
| Timeout | `DeadlineExceeded` | "request timeout" |

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| Publish (core) | < 1ms | No persistence |
| Publish (JetStream) | < 5ms | With ack |
| Subscribe setup | < 10ms | Initial subscription |
| Message delivery | < 2ms | After publish |
| KV Get | < 2ms | Single key |
| KV Put | < 5ms | Single key |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
