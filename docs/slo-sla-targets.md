# isA Cloud — SLO/SLA Targets

> Service Level Objectives and Agreements for all infrastructure components.
> Last updated: 2026-04-10

## Overview

SLOs define the reliability targets for each infrastructure component. These targets inform alerting thresholds, error budgets, and escalation decisions.

### Availability Tiers

| Tier | Availability | Monthly Downtime Budget | Use Case |
|------|-------------|----------------------|----------|
| Tier 1 | 99.99% | 4.3 minutes | Core data path (PostgreSQL, Redis, NATS) |
| Tier 2 | 99.95% | 21.9 minutes | Service mesh (Consul, APISIX, etcd) |
| Tier 3 | 99.9% | 43.8 minutes | Analytics & ML (Qdrant, Neo4j, MinIO) |

## Per-Component SLOs

### PostgreSQL HA

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.99% | Pgpool health endpoint up | < 99.95% over 5m |
| P50 query latency | < 5ms | Prometheus histogram | > 10ms for 5m |
| P99 query latency | < 50ms | Prometheus histogram | > 100ms for 5m |
| Replication lag | < 1s | pg_stat_replication | > 10s for 2m |
| Connection pool utilization | < 80% | Pgpool metrics | > 90% for 5m |
| Disk usage | < 80% | node_exporter | > 85% |

### Redis Cluster

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.99% | Cluster state OK | cluster_state != ok for 1m |
| P50 latency | < 1ms | redis_commands_duration | > 2ms for 5m |
| P99 latency | < 10ms | redis_commands_duration | > 20ms for 5m |
| Memory usage | < 80% of maxmemory | redis_memory_used | > 90% |
| Slot coverage | 16384/16384 | redis_cluster_slots_ok | < 16384 for 1m |
| Eviction rate | < 100/s | redis_evicted_keys | > 500/s for 5m |

### NATS JetStream

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.99% | JetStream health | jetstream unhealthy for 1m |
| P99 publish latency | < 5ms | nats_latency_histogram | > 20ms for 5m |
| Consumer lag | < 100 messages | nats_consumer_pending | > 1000 for 5m |
| Stream storage usage | < 80% | nats_jetstream_storage | > 85% |
| Message delivery rate | > 99.9% | ack/publish ratio | < 99% for 10m |

### etcd

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.95% | /health endpoint | unhealthy for 30s |
| P99 read latency | < 10ms | etcd_disk_wal_fsync | > 50ms for 5m |
| Leader elections | < 1/hour | etcd_server_leader_changes | > 3 in 1h |
| DB size | < 6GB (of 8GB quota) | etcd_debugging_mvcc_db_total_size | > 7GB |
| Proposal failures | 0 | etcd_server_proposals_failed | > 0 for 5m |

### Consul

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.95% | Leader elected | no leader for 30s |
| Service registration lag | < 5s | consul_catalog_register | > 15s |
| Health check pass rate | > 99% | consul_health_service_status | < 95% |
| KV read latency | < 10ms | consul_kvs_apply | > 50ms for 5m |

### APISIX Gateway

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.95% | /apisix/status | down for 30s |
| P50 proxy latency | < 5ms (overhead) | apisix_http_latency | > 20ms for 5m |
| P99 proxy latency | < 50ms (overhead) | apisix_http_latency | > 100ms for 5m |
| Error rate (5xx) | < 0.1% | apisix_http_status | > 1% for 5m |
| Route sync freshness | < 60s | consul-apisix-sync lag | > 120s |

### MinIO

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.9% | /minio/health/live | down for 1m |
| P99 GET latency | < 100ms | minio_s3_requests_duration | > 500ms for 5m |
| Disk usage | < 80% | minio_disk_storage_used | > 85% |
| Healing status | 0 objects | minio_heal_objects_total | > 0 for 30m |

### Qdrant

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.9% | /readyz | down for 1m |
| P99 search latency | < 100ms | qdrant_search_duration | > 500ms for 5m |
| Collection replication | factor ≥ 2 | qdrant_collection_info | factor < 2 |

### Neo4j

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.9% | Bolt connection | unreachable for 1m |
| P99 query latency | < 200ms | neo4j_bolt_messages | > 1s for 5m |
| Cluster quorum | 3/3 members | causal_clustering | < 3 for 1m |

### EMQX

| Metric | Target | Measurement | Alert Threshold |
|--------|--------|-------------|-----------------|
| Availability | 99.9% | Cluster status | node down for 1m |
| Connection capacity | < 80% of max | emqx_connections | > 90% |
| Message delivery | > 99.9% | delivered/published | < 99% for 10m |

## Error Budget Policy

### Calculation

```
Error Budget = 1 - SLO Target
Monthly Budget (minutes) = 43200 × (1 - SLO)
```

Example for 99.99%: `43200 × 0.0001 = 4.32 minutes/month`

### Escalation Thresholds

| Budget Consumed | Action |
|----------------|--------|
| 0-50% | Normal operations |
| 50-75% | Review recent changes, increase monitoring |
| 75-90% | Freeze non-critical deployments, incident review |
| 90-100% | All hands on reliability, no feature work |
| >100% | Post-incident review mandatory, remediation plan required |

### On-Call Routing

| Component | Primary | Escalation |
|-----------|---------|------------|
| PostgreSQL, Redis, NATS | @data-team | @platform-lead |
| Consul, APISIX, etcd | @platform-team | @infra-lead |
| MinIO, Qdrant, Neo4j | @data-team | @platform-lead |
| EMQX | @iot-team | @platform-lead |
| GPU (vLLM, Triton) | @ml-team | @infra-lead |
| Agent Runtime | @runtime-team | @infra-lead |

## Measurement

All SLO metrics are collected via Prometheus ServiceMonitors and evaluated using recording rules. Dashboards are in Grafana under the "SLO" folder.

SLO compliance is reported monthly via automated Prometheus queries.
