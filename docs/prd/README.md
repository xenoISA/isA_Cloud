# isA Cloud Platform - Product Requirements Document

> User Stories and Acceptance Criteria for Infrastructure Services

---

## Overview

This document defines the product requirements for isA Cloud's infrastructure services layer, provided through the **isa_common** Python SDK. Each service is accessed via native async clients connecting directly to backend services on their native ports.

---

## Epic 1: Redis Service (Cache & Key-Value Store)

### E1-US1: Key-Value Operations

**As a** backend developer
**I want** to store and retrieve key-value pairs via the async Redis client
**So that** I can cache data with automatic multi-tenant isolation

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Given valid credentials, when Set is called, then key-value is stored | Done |
| AC-1.2 | Given valid key, when Get is called, then value is returned | Done |
| AC-1.3 | Given TTL > 0, when Set is called, then key expires after TTL seconds | Done |
| AC-1.4 | Given non-existent key, when Get is called, then NotFound error returned | Done |
| AC-1.5 | Given invalid user_id, when any operation is called, then PermissionDenied | Done |

### E1-US2: Multi-Tenant Isolation

**As a** platform operator
**I want** each organization's data isolated
**So that** tenants cannot access each other's cached data

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Keys are prefixed with org_id:user_id automatically | Done |
| AC-2.2 | User A cannot read User B's keys (different org) | Done |
| AC-2.3 | Audit log records all access attempts | Done |

### E1-US3: Hash Operations

**As a** backend developer
**I want** to store structured data as Redis hashes
**So that** I can efficiently update individual fields

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | HSet stores field-value pairs in a hash | Done |
| AC-3.2 | HGet retrieves a single field from hash | Done |
| AC-3.3 | HGetAll retrieves all fields from hash | Done |
| AC-3.4 | HDel removes fields from hash | Done |

---

## Epic 2: PostgreSQL Service (Relational Database)

### E2-US1: Query Execution

**As a** backend developer
**I want** to execute SQL queries via the async PostgreSQL client
**So that** I can access the database with automatic connection pooling

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Execute SELECT queries and return rows as JSON | Done |
| AC-1.2 | Execute INSERT/UPDATE/DELETE and return affected rows | Done |
| AC-1.3 | Support parameterized queries to prevent SQL injection | Done |
| AC-1.4 | Return meaningful error messages for invalid SQL | Done |

### E2-US2: Transaction Support

**As a** backend developer
**I want** to execute multiple queries in a transaction
**So that** I can ensure data consistency

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | BeginTx starts a transaction and returns tx_id | Planned |
| AC-2.2 | ExecuteInTx runs query within transaction | Planned |
| AC-2.3 | Commit commits the transaction | Planned |
| AC-2.4 | Rollback aborts the transaction | Planned |
| AC-2.5 | Transactions timeout after configurable period | Planned |

---

## Epic 3: NATS Service (Event Streaming)

### E3-US1: Publish/Subscribe

**As a** microservice developer
**I want** to publish and subscribe to events
**So that** services can communicate asynchronously

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Publish sends message to subject | Done |
| AC-1.2 | Subscribe receives messages from subject | Done |
| AC-1.3 | Wildcards supported (orders.*, orders.>) | Done |
| AC-1.4 | Messages include metadata (timestamp, publisher) | Done |

### E3-US2: JetStream Persistence

**As a** microservice developer
**I want** messages persisted with delivery guarantees
**So that** no events are lost during service restarts

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Create/manage streams with retention policies | Done |
| AC-2.2 | Durable consumers for reliable delivery | Done |
| AC-2.3 | Ack/Nak for message acknowledgment | Done |
| AC-2.4 | Replay from specific sequence number | Done |

### E3-US3: Key-Value Store

**As a** microservice developer
**I want** a distributed key-value store
**So that** services can share configuration and state

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | Create/delete KV buckets | Done |
| AC-3.2 | Put/Get/Delete keys | Done |
| AC-3.3 | Watch for key changes | Done |
| AC-3.4 | TTL support for keys | Done |

---

## Epic 4: MinIO Service (Object Storage)

### E4-US1: Bucket Management

**As a** backend developer
**I want** to create and manage storage buckets
**So that** I can organize uploaded files

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Create bucket with specified name | Done |
| AC-1.2 | List all buckets for organization | Done |
| AC-1.3 | Delete empty bucket | Done |
| AC-1.4 | Bucket names scoped to organization | Done |

### E4-US2: Object Operations

**As a** backend developer
**I want** to upload and download files
**So that** I can store binary data in the platform

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Upload object with metadata | Done |
| AC-2.2 | Download object by key | Done |
| AC-2.3 | List objects in bucket with pagination | Done |
| AC-2.4 | Delete object | Done |
| AC-2.5 | Generate presigned URLs for direct access | Done |

---

## Epic 5: Qdrant Service (Vector Database)

### E5-US1: Collection Management

**As an** AI developer
**I want** to create vector collections
**So that** I can store embeddings for similarity search

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Create collection with dimension and distance metric | Done |
| AC-1.2 | List collections | Done |
| AC-1.3 | Delete collection | Done |
| AC-1.4 | Collections scoped to organization | Done |

### E5-US2: Vector Operations

**As an** AI developer
**I want** to upsert and search vectors
**So that** I can build semantic search features

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Upsert vectors with payload | Done |
| AC-2.2 | Search by vector similarity (top-k) | Done |
| AC-2.3 | Filter search by payload fields | Done |
| AC-2.4 | Delete vectors by ID or filter | Done |

---

## Epic 6: Loki Service (Logging)

### E6-US1: Log Ingestion

**As a** platform operator
**I want** services to send logs to centralized storage
**So that** I can monitor and debug the platform

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Push logs with labels and timestamp | Done |
| AC-1.2 | Batch log ingestion for efficiency | Done |
| AC-1.3 | Auto-add service metadata labels | Done |

### E6-US2: Log Queries

**As a** platform operator
**I want** to query logs using LogQL
**So that** I can investigate issues

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Query logs by label selectors | Done |
| AC-2.2 | Filter by time range | Done |
| AC-2.3 | Support regex and line filters | Done |
| AC-2.4 | Return results with pagination | Done |

---

## Epic 7: Cross-Cutting Concerns

### E7-US1: Service Discovery

**As a** platform operator
**I want** services to register with Consul
**So that** clients can discover healthy instances

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Services register on startup | Done |
| AC-1.2 | Health checks configured | Done |
| AC-1.3 | Deregister on shutdown | Done |

### E7-US2: Observability

**As a** platform operator
**I want** metrics and traces from all services
**So that** I can monitor performance

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Client metrics exported (latency, errors) | Partial |
| AC-2.2 | Distributed tracing with trace IDs | Planned |
| AC-2.3 | Dashboard in Grafana | Done |

---

## Epic 8: Unified Observability (Epic #92)

> Shared Prometheus metrics, OpenTelemetry tracing (Tempo), and unified observability clients in `isa_common`.

### E8-US1: Shared Observability Clients

**As a** backend developer
**I want** a single `setup_observability()` call to configure metrics, logging, and tracing
**So that** every service gets consistent observability without duplicating setup code

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | `isa_common.metrics` provides `setup_metrics()`, counter/histogram/gauge factories, FastAPI middleware, and `/metrics` endpoint | Done |
| AC-1.2 | `isa_common.tracing` provides `setup_tracing()`, `get_tracer()`, OTLP export to Tempo, and auto-instrumentation (FastAPI, aiohttp, asyncpg, redis, httpx) | Done |
| AC-1.3 | `isa_common.observability` provides unified `setup_observability()` wiring metrics + Loki + tracing | Done |
| AC-1.4 | All modules gracefully degrade to no-ops when optional dependencies are not installed | Done |
| AC-1.5 | L1 unit tests cover all three modules (metrics, tracing, observability) | Done |
| AC-1.6 | L2 component tests verify middleware with Starlette TestClient | Planned |
| AC-1.7 | L3 integration tests verify OTLP export to mock collector | Planned |

### E8-US2: Service Migration to Shared Clients

**As a** platform operator
**I want** all isA services using the shared observability clients
**So that** metrics and traces are consistent across the platform

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | isA_Trade migrated to `isa_common` metrics and observability | Done |
| AC-2.2 | isA_user migrated to `isa_common` metrics and observability | Done |
| AC-2.3 | isA_OS migrated to `isa_common` metrics (without global state mutation) | Partial |
| AC-2.4 | isA_Creative migrated to `isa_common` metrics (without global state mutation) | Partial |
| AC-2.5 | isA_MCP migrated — duplicate `core/tracing.py` and `PrometheusMiddleware` removed | Planned |
| AC-2.6 | isA_Model migrated from `prometheus-fastapi-instrumentator` to `isa_common.metrics` | Planned |
| AC-2.7 | isA_Mate migrated from raw `prometheus_client` to `isa_common.metrics` | Planned |

### E8-US3: Tracing Pipeline Active

**As a** platform operator
**I want** at least one service sending traces to Tempo
**So that** the distributed tracing pipeline is validated end-to-end

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | OTel SDK + OTLP exporter installed in at least one service | Planned |
| AC-3.2 | `TEMPO_HOST` / `OTEL_EXPORTER_OTLP_ENDPOINT` configured in deployment | Planned |
| AC-3.3 | Traces visible in Grafana Tempo datasource | Planned |

### E8-US4: Prometheus Scrape Coverage

**As a** platform operator
**I want** all metric-emitting services scraped by Prometheus
**So that** no service metrics are silently dropped

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-4.1 | Local `prometheus.yml` includes scrape targets for isA_Trade, isA_user, isA_Creative, isA_OS | Planned |
| AC-4.2 | Production ServiceMonitors cover all deployed services | Planned |

---

## Epic 9: Production K8s Deployment (Provider-Agnostic)

> Pluggable production deployment supporting any K8s infrastructure (bare-metal, on-prem cloud, managed). First target: Infotrend Enterprise Cloud (3-node cluster).

### E9-US1: Pluggable Storage Class Templates

**As a** cluster admin
**I want** provider-agnostic storage class templates with pluggable presets
**So that** I can deploy on any infrastructure without modifying Helm values

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Provider profile config maps logical names (block, fast, nfs, object) to provider-specific classes | Planned |
| AC-1.2 | Infotrend preset maps to infotrend-block, infotrend-block-fast, infotrend-nfs, infotrend-object | Planned |
| AC-1.3 | Generic preset uses standard/default storage class for cloud providers | Planned |
| AC-1.4 | All Helm value files reference logical storage names, resolved at deploy time | Planned |

### E9-US2: 3-Node Cluster Resource Profiles

**As a** platform operator
**I want** right-sized resource profiles for small clusters (3 nodes)
**So that** infrastructure fits within constrained node capacity

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | PostgreSQL HA downsized to 2 replicas with anti-affinity soft rules | Planned |
| AC-2.2 | Redis Cluster downsized to 3 masters + 0 replicas | Planned |
| AC-2.3 | Pod topology spread constraints distribute across all 3 nodes | Planned |
| AC-2.4 | Total resource requests fit within 3-node capacity (documented) | Planned |

### E9-US3: Pre-Flight Verification

**As a** SRE
**I want** automated pre-flight checks before deployment
**So that** issues are caught before any Helm install runs

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | Verify K8s version compatibility (≥1.27) | Planned |
| AC-3.2 | Verify storage classes exist and are provisionable | Planned |
| AC-3.3 | Verify node count and resource capacity meet minimum requirements | Planned |
| AC-3.4 | Verify network connectivity (inter-node, DNS, external registries) | Planned |
| AC-3.5 | Verify Vault is unsealed and ESO is syncing secrets | Planned |

### E9-US4: Provider-Parameterized Deployment

**As a** DevOps engineer
**I want** deploy.sh to accept a provider profile and cluster size
**So that** a single script handles any target environment

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-4.1 | deploy.sh accepts --provider and --nodes flags | Planned |
| AC-4.2 | Provider flag selects storage class preset and provider-specific config | Planned |
| AC-4.3 | Nodes flag selects resource profile (3-node, 5-node, 10-node) | Planned |
| AC-4.4 | Deployment order unchanged (secrets → etcd → databases → messaging → gateway → apps) | Planned |

### E9-US5: Production Deployment Guide

**As an** operator
**I want** a step-by-step deployment guide with provider-specific examples
**So that** I can deploy the full stack on any supported infrastructure

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-5.1 | Guide covers end-to-end from clean cluster to running platform | Planned |
| AC-5.2 | Infotrend example included as reference implementation | Planned |
| AC-5.3 | Verification steps after each deployment phase | Planned |

### E9-US6: Post-Deploy Health Verification

**As an** on-call engineer
**I want** a health check script that verifies full stack deployment
**So that** I can confirm the platform is production-ready

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-6.1 | All pods in Running/Ready state | Planned |
| AC-6.2 | All services registered in Consul | Planned |
| AC-6.3 | APISIX routes synced from Consul | Planned |
| AC-6.4 | PodDisruptionBudgets satisfied | Planned |
| AC-6.5 | Backup CronJobs configured and schedulable | Planned |

### E9-US7: Rollback Procedures

**As a** platform operator
**I want** documented rollback procedures for each deployment phase
**So that** I can recover from failed deployments

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-7.1 | Helm rollback commands documented per component | Planned |
| AC-7.2 | Data recovery steps for stateful services | Planned |
| AC-7.3 | Order of rollback (reverse of deployment) documented | Planned |

### E9-US8: Portable Backup/Restore

**As a** platform operator
**I want** backup and restore procedures that work across storage providers
**So that** data is protected regardless of infrastructure

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-8.1 | PostgreSQL backup via pg_dump CronJob (provider-independent) | Planned |
| AC-8.2 | MinIO backup via mc mirror to secondary target | Planned |
| AC-8.3 | NATS JetStream snapshot and restore documented | Planned |
| AC-8.4 | Backup targets configurable per provider profile | Planned |

---

## Epic 10: GPU Inference Platform (isA_Model on IEC)

> Deploy GPU inference infrastructure on IEC K8s — NVIDIA GPU Operator, model serving engines (vLLM, Triton), persistent model cache, GPU monitoring, and autoscaling.

### E10-US1: NVIDIA GPU Operator Deployment

**As a** cluster admin
**I want** the NVIDIA GPU Operator deployed with device plugin, DCGM exporter, and driver manager
**So that** K8s can schedule GPU workloads and monitor GPU health

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | GPU Operator Helm chart deployed with node-specific driver config | Planned |
| AC-1.2 | nvidia.com/gpu resource visible in kubectl describe node | Planned |
| AC-1.3 | DCGM exporter scraping GPU metrics (VRAM, utilization, temperature) | Planned |
| AC-1.4 | GPU nodes labeled with gpu-model and gpu-memory | Planned |

### E10-US2: Persistent Model Cache with Storage Tiers

**As a** ML engineer
**I want** models cached on persistent SSD volumes with pre-pull init containers
**So that** pod restarts don't require re-downloading multi-GB models

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | StatefulSet with PVC for model cache (fast storage class) | Planned |
| AC-2.2 | Init container pre-pulls configured models before inference starts | Planned |
| AC-2.3 | Model version pinning via ConfigMap (no implicit latest) | Planned |
| AC-2.4 | Cache survives pod restarts and node drains | Planned |

### E10-US3: vLLM Engine Production Deployment

**As a** platform operator
**I want** vLLM deployed with GPU topology constraints and speculative decoding
**So that** LLM inference runs at maximum throughput on local GPUs

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | vLLM StatefulSet with nvidia.com/gpu resource requests | Planned |
| AC-3.2 | Tensor parallelism constrained to same-node GPUs (topology affinity) | Planned |
| AC-3.3 | Prefix caching and speculative decoding enabled | Planned |
| AC-3.4 | GPU memory utilization target configurable (default 0.9) | Planned |

### E10-US4: Triton Inference Server Deployment

**As a** ML engineer
**I want** Triton deployed with TensorRT and ONNX backend support
**So that** non-LLM models (vision, embedding, TTS) run optimally

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-4.1 | Triton deployed with model repository on persistent storage | Planned |
| AC-4.2 | Dynamic model loading via model-control-mode=poll | Planned |
| AC-4.3 | gRPC and HTTP endpoints exposed via ClusterIP | Planned |

### E10-US5: GPU Monitoring and Autoscaling

**As a** SRE
**I want** GPU utilization dashboards and GPU-aware HPA
**So that** inference scales with demand and I can monitor GPU health

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-5.1 | DCGM Prometheus metrics scraped by cluster Prometheus | Planned |
| AC-5.2 | Grafana dashboard for VRAM %, GPU utilization, temperature | Planned |
| AC-5.3 | HPA scales vLLM replicas based on GPU queue depth or VRAM pressure | Planned |
| AC-5.4 | Alerts for GPU thermal throttling and OOM | Planned |

### E10-US6: Ray Cluster Deployment for Distributed Inference

**As a** platform operator
**I want** a KubeRay-managed Ray cluster with GPU worker nodes
**So that** the RAY_SERVE backend router can distribute inference across GPUs

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-6.1 | KubeRay Operator deployed (reuse from isA_Cloud ML platform) | Planned |
| AC-6.2 | RayCluster CR with GPU worker nodegroup | Planned |
| AC-6.3 | Ray Serve deployments for vLLM and SGLang backends | Planned |
| AC-6.4 | Ray autoscaler scales GPU workers 0→N based on pending tasks | Planned |

### E10-US7: GPU Deploy Script and 3-Node Profile

**As a** DevOps engineer
**I want** deploy.sh extended with a `gpu` command and 3-node GPU profiles
**So that** GPU infrastructure deploys alongside the general stack

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-7.1 | deploy.sh gpu command deploys GPU Operator + engines in order | Planned |
| AC-7.2 | 3-node GPU profile allocates GPUs across nodes (no oversubscription) | Planned |
| AC-7.3 | Preflight script validates GPU availability and driver version | Planned |
| AC-7.4 | Health check verifies GPU pods, DCGM metrics, model loaded | Planned |

---

## Epic 11: Big Data Platform (isA_Data on IEC)

> Deploy distributed data processing on IEC K8s — Ray/Dask for distributed Polars/DuckDB, DAG orchestrator, streaming ETL pipeline, and data lake management.

### E11-US1: Ray Cluster for Distributed Data Processing

**As a** data engineer
**I want** Ray deployed as a distributed compute backend for Polars and DuckDB
**So that** data processing scales horizontally across 3 nodes

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | RayCluster CR with CPU worker pools across all 3 nodes | Planned |
| AC-1.2 | Ray Data integration for distributed Polars DataFrames | Planned |
| AC-1.3 | DuckDB-on-Ray for distributed OLAP queries | Planned |
| AC-1.4 | Resource isolation between data and inference Ray workloads | Planned |

### E11-US2: DAG Orchestrator Deployment

**As a** data engineer
**I want** a DAG scheduler (Dagster or Airflow) for pipeline orchestration
**So that** ETL pipelines have dependency management, retries, and scheduling

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Orchestrator Helm chart deployed with PostgreSQL backend | Planned |
| AC-2.2 | K8s executor for running pipeline tasks as pods | Planned |
| AC-2.3 | Integration with MinIO for artifact storage | Planned |
| AC-2.4 | Scheduled and event-triggered pipeline runs | Planned |

### E11-US3: Streaming ETL Pipeline Deployment

**As a** data engineer
**I want** the NATS CDC → Delta Lake streaming pipeline deployed
**So that** data flows from source databases to the data lake in near-real-time

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | CDC listener deployed consuming NATS JetStream subjects | Planned |
| AC-3.2 | Micro-batch processor writing to Delta Lake on MinIO | Planned |
| AC-3.3 | SCD Type 1/2 support for upserts in curated zone | Planned |
| AC-3.4 | Incremental materialized view refresh for gold zone | Planned |

### E11-US4: Data Service Production Deployment

**As a** platform operator
**I want** isA_Data deployed as a Helm release with HA and proper resource sizing
**So that** the data platform is production-ready on 3 nodes

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-4.1 | Data service Helm chart with StatefulSet (2+ replicas) | Planned |
| AC-4.2 | Init container for DB schema migrations | Planned |
| AC-4.3 | PDB and network policies configured | Planned |
| AC-4.4 | 3-node resource profile with storage for local caching | Planned |

### E11-US5: Data Platform Monitoring

**As a** SRE
**I want** data pipeline dashboards and SLO alerts
**So that** I can monitor pipeline health, latency, and data freshness

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-5.1 | Prometheus metrics for pipeline throughput, latency, errors | Planned |
| AC-5.2 | Grafana dashboard for Delta Lake zone sizes, CDC lag, query perf | Planned |
| AC-5.3 | Alerts for stale materialized views and pipeline failures | Planned |

### E11-US6: Optional Flink/StarRocks Tier (Future)

**As a** platform architect
**I want** an optional Flink + StarRocks deployment for complex stream processing and real-time OLAP
**So that** the platform can serve advanced analytics workloads if needed

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-6.1 | Flink Operator Helm chart and session cluster values | Planned |
| AC-6.2 | StarRocks Helm chart with FE/BE/CN node config | Planned |
| AC-6.3 | Integration with MinIO (Iceberg catalog) and NATS (Flink source) | Planned |
| AC-6.4 | 3-node resource profile (co-located with existing infra) | Planned |

---

## Epic 12: Agent Runtime Platform (isA_OS on IEC)

> Deploy Firecracker-based agent runtime on IEC K8s — KVM/Ignite setup, container-service gRPC backend, VM image pipeline, pool manager HA, and sandboxed execution.

### E12-US1: KVM and Firecracker Prerequisites

**As a** cluster admin
**I want** KVM enabled and validated on all IEC nodes
**So that** Firecracker microVMs can run with hardware virtualization

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | KVM kernel modules loaded and verified on all nodes | Planned |
| AC-1.2 | /dev/kvm accessible to pods with appropriate security context | Planned |
| AC-1.3 | Ignite installed on each node (DaemonSet or node-level) | Planned |
| AC-1.4 | Preflight script validates KVM, nested virt, and Ignite readiness | Planned |

### E12-US2: Container Service gRPC Backend Deployment

**As a** platform operator
**I want** the Go container-service deployed as the Firecracker VM management backend
**So that** cloud_os can create/manage microVMs via gRPC

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | container-service Helm chart deployed with privileged security context | Planned |
| AC-2.2 | gRPC service reachable from cloud_os pods | Planned |
| AC-2.3 | VM lifecycle operations (create, start, stop, delete) functional | Planned |
| AC-2.4 | Health check verifies gRPC connectivity and Ignite backend | Planned |

### E12-US3: Cloud OS Production Deployment

**As a** platform operator
**I want** cloud_os deployed with HA, proper Helm chart, and Ignite backend
**So that** agents can request and manage sandboxed VMs

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | cloud_os Helm chart with Deployment (2+ replicas) | Planned |
| AC-3.2 | ConfigMap switches backend from Docker to Ignite in production | Planned |
| AC-3.3 | Compute tier quotas enforced per namespace | Planned |
| AC-3.4 | Network policies restrict VM egress to approved endpoints | Planned |

### E12-US4: Pool Manager HA Deployment

**As a** platform operator
**I want** pool_manager deployed with HA and auto-scaling
**So that** agent VM requests are handled reliably

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-4.1 | pool_manager Helm chart with 2+ replicas | Planned |
| AC-4.2 | Redis-backed state for VM pool allocation | Planned |
| AC-4.3 | NATS integration for async VM lifecycle events | Planned |
| AC-4.4 | Auto-scaler for VM pool based on demand | Planned |

### E12-US5: VM Image Build Pipeline

**As a** platform operator
**I want** automated VM image builds for Python REPL and Playwright runtimes
**So that** microVM rootfs images are versioned, cached, and deployable

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-5.1 | CI pipeline builds rootfs images from Dockerfiles in vm-images/ | Planned |
| AC-5.2 | Images pushed to Harbor registry with version tags | Planned |
| AC-5.3 | Ignite image pull from Harbor on VM creation | Planned |
| AC-5.4 | Image cache on each node to avoid repeated pulls | Planned |

### E12-US6: Agent Runtime Monitoring

**As a** SRE
**I want** VM lifecycle dashboards and resource utilization metrics
**So that** I can monitor agent sandbox health and capacity

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-6.1 | Prometheus metrics for active VMs, creation latency, failures | Planned |
| AC-6.2 | Grafana dashboard for VM pool utilization and compute tier usage | Planned |
| AC-6.3 | Alerts for VM pool exhaustion and creation failures | Planned |
| AC-6.4 | Resource quotas preventing VM sprawl | Planned |

### E12-US7: Agent Runtime Deploy Script and 3-Node Profile

**As a** DevOps engineer
**I want** deploy.sh extended with a `runtime` command
**So that** the agent runtime deploys alongside general infrastructure

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-7.1 | deploy.sh runtime command deploys container-service → cloud_os → pool_manager | Planned |
| AC-7.2 | 3-node profile allocates VM capacity across nodes | Planned |
| AC-7.3 | Preflight validates KVM/Ignite on target nodes | Planned |
| AC-7.4 | Health check verifies VM creation end-to-end | Planned |

---

## Priority Matrix

| Epic | Priority | Status | Notes |
|------|----------|--------|-------|
| E1: Redis | P0 | Done | Core caching |
| E2: PostgreSQL | P0 | Partial | Transactions planned |
| E3: NATS | P0 | Done | Event backbone |
| E4: MinIO | P1 | Done | File storage |
| E5: Qdrant | P1 | Done | AI features |
| E6: Loki | P1 | Done | Observability |
| E7: Cross-cutting | P0 | Partial | Tracing planned |
| E8: Unified Observability | P1 | Partial | Shared clients done, migrations + tracing remaining |
| E9: Production K8s Deployment | P0 | Done | Provider-agnostic, Infotrend 3-node |
| E10: GPU Inference Platform | P0 | Planned | NVIDIA GPU Operator, vLLM, Triton, model cache |
| E11: Big Data Platform | P1 | Planned | Ray distributed compute, DAG orchestrator, streaming ETL |
| E12: Agent Runtime Platform | P0 | Planned | Firecracker/KVM, container-service, VM pool management |

---

## Related Documents

- [Domain](../domain/README.md) - Business Context
- [Design](../design/README.md) - Technical Architecture
- [CDD Guide](../cdd_guide.md) - Contract-Driven Development

---

**Version**: 2.3.0
**Last Updated**: 2026-04-10
