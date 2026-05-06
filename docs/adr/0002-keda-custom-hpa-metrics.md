# ADR 0002 — KEDA-based custom HPA metrics for the `isa-service` chart

- **Status**: Accepted
- **Date**: 2026-05-04
- **Author**: isA platform infra team
- **Issue**: [xenoISA/isA_user#352](https://github.com/xenoISA/isA_user/issues/352) — Parent epic: [#345](https://github.com/xenoISA/isA_user/issues/345)
- **Supersedes**: n/a (first ADR for the K8s HPA readiness workstream in `isA_Cloud`)
- **Replaces**: xenoISA/isA_user PR #363 (closed; chart belongs in `isA_Cloud`)

## Context

The `isa-service` Helm chart (`deployments/charts/isa-service/`) is the
single deployment template for every Python microservice across the isA
platform. Today its `templates/hpa.yaml` scales pods on CPU 70% / memory
80% only:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilization: 70
  targetMemoryUtilization: 80
```

That is generic and lags real load for our service mix:

- **Event consumers** (`wallet`, `billing`, `payment` in `xenoISA/isA_user`,
  plus several services in `xenoISA/isA_MCP` and `xenoISA/isA_Agent`) burn
  very little CPU per message but accumulate NATS JetStream backlog under
  burst — they need to scale on **queue depth**, not CPU.
- **Auth-heavy services** (`auth`, `account`, `authorization`) tail-latency
  spike long before CPU saturates because the bottleneck is downstream
  Postgres/Redis fan-out. They need to scale on **p95 request latency**.
- **Telemetry / streaming** (`telemetry`, `notification`) hold long-lived
  WebSocket connections; CPU/memory per pod is flat regardless of fan-out,
  so scaling has to track **connection count or message rate**.

Two viable options exist on a vanilla Kubernetes cluster:

1. **Prometheus Adapter** (`k8s-prometheus-adapter`) — registers a custom
   `external.metrics.k8s.io` API backed by PromQL queries. The `HPA` resource
   then references the metric directly.
2. **KEDA** (Kubernetes Event-Driven Autoscaler) — installs a controller
   that reconciles `ScaledObject` CRs into HPAs. Ships a built-in scaler
   library (NATS, Kafka, Prometheus, Redis Streams, RabbitMQ, AWS SQS, ...).

## Decision

**Adopt KEDA as the autoscaling controller for the `isa-service` chart.**

- Add `templates/scaledobject.yaml` rendered when `hpa.kedaEnabled=true`.
- Gate `templates/hpa.yaml` on `hpa.kedaEnabled=false` so the two
  controllers never race on `spec.replicas`.
- Keep CPU and memory triggers on every `ScaledObject` as fallback ceilings
  — a stuck custom-metric collector still scales on raw load. Hard
  acceptance criterion for #352.
- Default `hpa.kedaEnabled=false` so existing deployments are unchanged
  until consumers explicitly opt in.

## Alternatives considered

### Prometheus Adapter

- Pros: single dependency we already need in some form (we run Prometheus
  for SLOs), no new CRD surface, HPA is the native object.
- Cons:
  - **No native NATS scaler.** Queue depth would need to be exported to
    Prometheus first (extra exporter, extra scrape latency, extra failure
    mode). This is the load shape that *most* needs custom autoscaling for
    `wallet`/`billing`/`payment`, so degrading it is a non-starter.
  - PromQL strings live in a `ConfigMap` that the adapter parses on start —
    debugging a misnamed metric requires a controller restart.
  - One adapter Deployment is a single point of failure for *every* HPA on
    the cluster. KEDA controllers are stateless and scale horizontally.

### Stay on CPU/memory only

- Pros: zero new infra.
- Cons: doesn't satisfy issue #352 acceptance criteria; we already know
  that CPU saturates *after* SLA breach for both event consumers and auth
  services.

### Ship the chart from `xenoISA/isA_user` (PR #363)

- Pros: changes co-located with the consuming services.
- Cons: violates the chart-ownership model. `xenoISA/isA_Cloud` owns
  `isa-service`; placing chart templates in a consumer repo creates a
  copy-paste fork the next service has to keep in sync. PR #363 was closed
  in favour of this work item.

## Consequences

### Positive

- One controller covers all three load shapes:
  - NATS JetStream depth via the built-in `nats-jetstream` scaler.
  - Prometheus queries (p95 latency, WS connection gauge) via the
    `prometheus` scaler — same PromQL we'd write for the adapter, no
    `ConfigMap` indirection.
  - CPU/memory via `cpu` and `memory` triggers — KEDA delegates to the
    upstream HPA resource metrics so behaviour is identical to today.
- `ScaledObject`s declare `minReplicaCount`/`maxReplicaCount` and behaviour
  policies in one place.
- `advanced.horizontalPodAutoscalerConfig.behavior` lets us pin scale-down
  windows per service tier.
- Chart change is opt-in: `hpa.kedaEnabled=false` by default. Existing
  releases are unchanged on upgrade.

### Negative / cost

- KEDA controller and metrics-apiserver must be installed cluster-wide
  (`keda` namespace). **This chart does not install KEDA.** The cluster
  operator runs `helm install keda kedacore/keda -n keda --create-namespace`
  before the first `helm upgrade` of an `isa-service` release that has
  `hpa.kedaEnabled=true`. Documented in
  `docs/runbooks/keda-hpa-metrics.md`.
- New CRDs (`scaledobjects.keda.sh`, `triggerauthentications.keda.sh`) on
  the cluster. Backwards-compatible: removing KEDA returns services to
  manual replica counts.
- `prometheus` triggers depend on a reachable Prometheus endpoint
  (`http://prometheus.isa-cloud-{staging,prod}:9090`). If a Prometheus
  exporter for a required signal does not exist yet (e.g. WebSocket
  connection gauge for `telemetry_service`), the trigger will report
  `Fallback=True` and the CPU/memory ceiling kicks in — by design.

### Rollback

Setting `hpa.kedaEnabled=false` in the consumer's values file and running
`helm upgrade` causes the chart to skip rendering the `ScaledObject` and
re-render the plain HPA. KEDA deletes the underlying synthesised HPA and
the Deployment returns to plain HPA semantics. No data path change.

## Verified naming corrections (vs. xenoISA/isA_user PR #363)

PR #363 hard-coded several names that do not exist in the actual code.
This ADR records the verified replacements so future changes do not
re-introduce the mistake.

### NATS streams

Streams are derived from the subject prefix in
`xenoISA/isA_user/core/nats_client.py:_get_stream_name()`
(`f"{prefix}-stream"`, with special cases for `file`, `firmware`,
`campaign`, `update`, `rollback`, `alert`, `metric`). PR #363 used
`stream: isa-events` for every event-tier service — that stream does not
exist. Correct mappings:

| Subject prefix    | Stream             | Source                                       |
|-------------------|--------------------|----------------------------------------------|
| `billing.>`       | `billing-stream`   | `core/nats_client.py:204-235`                |
| `session.>`       | `session-stream`   | `core/nats_client.py:204-235`                |
| `user.>`          | `user-stream`      | `core/nats_client.py:204-235`                |
| `payment_service.>` | `payment_service-stream` (auto) | `core/nats_client.py:235` |
| `wallet_service.>`  | `wallet_service-stream` (auto)  | `core/nats_client.py:235` |
| `*.file.>`        | `storage-stream`   | `core/nats_client.py:226`                    |
| `alert.>`/`metric.>` | `telemetry-stream` | `core/nats_client.py:231-232`             |

### NATS consumer durables

| Service | Durable pattern | Source |
|---------|-----------------|--------|
| `wallet_service`  | `wallet-<last-token-of-pattern>-consumer` (e.g. `wallet-balance_changed-consumer`) | `microservices/wallet_service/main.py:182` |
| `billing_service` | `billing-<pattern-with-dots-replaced>-consumer[-${BILLING_CONSUMER_SUFFIX}]`         | `microservices/billing_service/main.py:116-125` |
| `payment_service` | Auto-derived: `payment_service-<subject-prefix>-consumer` (no explicit durable)       | `microservices/payment_service/main.py:152` + `core/nats_client.py:407-409` |

PR #363 used `consumer: user-payment-service` / `user-wallet-service` /
`user-billing-service` — none of those exist as JetStream durables.

### Prometheus metric names

`xenoISA/isA_Cloud/isA_common/isa_common/metrics.py` is the source of
truth. Metric names are prefixed `isa_<service>_`:

| Metric (verified)                                | Type      | Labels                          | Source line          |
|---------------------------------------------------|-----------|---------------------------------|----------------------|
| `isa_<svc>_http_requests_total`                  | Counter   | `method`, `path`, `status_code` | `metrics.py:244-248` |
| `isa_<svc>_http_request_duration_seconds`        | Histogram | `method`, `path`                | `metrics.py:249-254` |
| `isa_<svc>_http_request_size_bytes`              | Histogram | `method`, `path`                | `metrics.py:255-260` |
| `isa_<svc>_http_response_size_bytes`             | Histogram | `method`, `path`                | `metrics.py:261-266` |
| `isa_<svc>_http_requests_in_progress`            | Gauge     | `method`                        | `metrics.py:267-271` |

PR #363's proposed PromQL used `service="<svc>"` as a label selector. No
such label is emitted — the service is encoded in the metric name prefix.
The chart's `auth` tier preset queries
`isa_user_http_request_duration_seconds_bucket` directly without a
`service=` filter. Each consumer overrides `metricName` per service.

### Aspirational metric names

`isa_user_websocket_active_connections` does not exist in the codebase —
it appeared only in
`microservices/auth_service/docs/Issue/PERFORMANCE.md` as a planned
metric. The chart leaves it in the `telemetry` tier preset with a
`TODO(#352): verify metric exists in actual /metrics output` comment so
the ScaledObject renders, but it must be confirmed against the deployed
pods before flipping `kedaEnabled: true` in production.

## Validation

- `helm lint deployments/charts/isa-service/ --strict` — passes with
  `kedaEnabled` toggled on and off.
- `helm template deployments/charts/isa-service/ --set hpa.kedaEnabled=true`
  emits exactly one `ScaledObject` and zero `HorizontalPodAutoscaler`.
- `helm template deployments/charts/isa-service/ --set hpa.kedaEnabled=false`
  emits exactly one `HorizontalPodAutoscaler` and zero `ScaledObject`.
- The runbook `docs/runbooks/keda-hpa-metrics.md` documents per-service
  rationale and how to tune thresholds.

## References

- xenoISA/isA_user issue #352 (this ADR's authorising work item).
- xenoISA/isA_user epic #345 — K8s HPA readiness.
- xenoISA/isA_user PR #363 (closed; superseded by this work).
- KEDA scaler catalogue: <https://keda.sh/docs/latest/scalers/>
- Prometheus Adapter: <https://github.com/kubernetes-sigs/prometheus-adapter>
- Kubernetes HPA `behavior` field:
  <https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#configurable-scaling-behavior>
