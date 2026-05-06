# KEDA HPA Custom Metrics Runbook

> Sibling docs:
> [`deployments/charts/isa-service/templates/scaledobject.yaml`](../../deployments/charts/isa-service/templates/scaledobject.yaml),
> [`deployments/charts/isa-service/templates/hpa.yaml`](../../deployments/charts/isa-service/templates/hpa.yaml),
> [`docs/adr/0002-keda-custom-hpa-metrics.md`](../adr/0002-keda-custom-hpa-metrics.md).
> Authorising issue: [xenoISA/isA_user#352](https://github.com/xenoISA/isA_user/issues/352) — Parent epic: [#345](https://github.com/xenoISA/isA_user/issues/345).

## What this covers

The `isa-service` chart autoscales each microservice via a
[KEDA `ScaledObject`][keda] rendered from
`templates/scaledobject.yaml` when `hpa.kedaEnabled=true` (opt-in).
Each `ScaledObject` declares one or more **triggers** that KEDA polls; a
single trigger crossing its threshold is enough to scale up. CPU and
memory triggers are kept on every object as fallback ceilings — a stuck
custom-metric collector still surfaces real load.

This runbook explains:

1. The per-service-tier metric mapping and why each tier exists.
2. How to install / verify the KEDA prerequisite.
3. How to inspect a running `ScaledObject` and its synthesised HPA.
4. How to tune a threshold safely.
5. How to opt a single service in or out without touching the chart.
6. Recovery when a trigger goes silent or starts oscillating.

[keda]: https://keda.sh/docs/latest/concepts/scaling-deployments/

## 1. Service tiers and metric choice

| Tier        | Services                                  | Primary signal                            | Polling | Why this signal                                                                                                  |
|-------------|-------------------------------------------|-------------------------------------------|---------|------------------------------------------------------------------------------------------------------------------|
| `event`     | `wallet`, `billing`, `payment`            | NATS JetStream consumer pending messages  | 15s     | Low CPU per message + bursty arrival rate — backlog is the only metric that reflects user-visible processing lag |
| `auth`      | `auth`, `account`, `authorization`        | Prometheus p95 request latency            | 60s     | Bottleneck is downstream Postgres/Redis fan-out, not local CPU; tail-latency degrades long before CPU saturates  |
| `telemetry` | `telemetry` (and any future WS streamer)  | Prometheus active WebSocket connections   | 30s     | Pods hold long-lived sockets at flat CPU/memory; connection count drives broadcast cost                          |
| `default`   | every other service                       | CPU 70% / memory 80% (fallback only)      | 30s     | Stateless request/response services are CPU-bound — the upstream HPA semantics are correct                       |

Per-service overrides live in each service's values file (e.g.
`xenoISA/isA_user`'s `deployment/helm/values-{staging,production}.yaml`)
under the `hpa.keda.tier` key. The chart-level defaults are in
`deployments/charts/isa-service/values.yaml`.

## 2. KEDA prerequisite

This Helm chart deliberately does **not** install KEDA — installing CRDs
under a service release is fragile. The cluster operator runs the install
once per cluster:

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda \
  --namespace keda \
  --create-namespace \
  --version 2.14.0     # pin to the version validated against this chart
```

Verify the install:

```bash
kubectl -n keda get pods
# NAME                                    READY   STATUS
# keda-operator-...                       1/1     Running
# keda-operator-metrics-apiserver-...     1/1     Running

kubectl get apiservice v1beta1.external.metrics.k8s.io -o yaml | grep -E 'available|reason'
# conditions: type: Available, status: "True"
```

If `external.metrics.k8s.io` is not available, every KEDA `ScaledObject`
will report `Fallback=True` and fall through to the CPU/memory triggers —
pods scale, but slower than intended. Treat a missing apiservice as a P1
alert.

## 3. Inspecting a running ScaledObject

After `helm upgrade --install` of an `isa-service` release with
`hpa.kedaEnabled=true`:

```bash
export NAMESPACE=isa-cloud-prod  # or isa-cloud-staging

# List all ScaledObjects rendered by this chart
kubectl get scaledobjects -n "$NAMESPACE" \
  -l app.kubernetes.io/component=autoscaler

# Detail a single one — note `status.conditions` and the trigger health table
kubectl describe scaledobject user-wallet-service -n "$NAMESPACE"

# The synthesised HPA (KEDA-managed; do NOT edit it directly)
kubectl get hpa user-wallet-service-keda -n "$NAMESPACE" -o yaml

# Live external-metric value (what the controller actually sees)
kubectl get --raw \
  "/apis/external.metrics.k8s.io/v1beta1/namespaces/$NAMESPACE/s0-nats-jetstream-billing-stream-billing-usage-recorded-all-consumer" \
  | jq
```

Key conditions in `kubectl describe`:

- `Active=True` — the `ScaledObject` is reconciling.
- `Fallback=True` — the custom trigger is unhealthy and KEDA dropped to
  the CPU/memory ceilings. Investigate the trigger before disabling.
- `Ready=False` — the controller could not parse the spec; the `Message`
  field names the bad field.

## 4. Tuning a threshold

Threshold tuning is a two-knob exercise: **threshold** (when to scale up)
and **cooldownPeriod** (how patiently to scale down).

### Event tier (`nats-jetstream`)

`metadata.lagThreshold` is the per-replica pending-message ceiling. KEDA
scales the deployment to `ceil(consumer_pending / lagThreshold)` replicas
(clamped to `[minReplicaCount, maxReplicaCount]`).

Verified consumer/stream names (xenoISA/isA_user):

| Service           | Stream(s)                                      | Consumer durable                                                            | Source                                                |
|-------------------|------------------------------------------------|-----------------------------------------------------------------------------|-------------------------------------------------------|
| `wallet_service`  | per subject prefix (`payment_service-stream`, `account_service-stream`, ...) | `wallet-<last-token-of-pattern>-consumer` (e.g. `wallet-balance_changed-consumer`) | `microservices/wallet_service/main.py:182`            |
| `billing_service` | `billing-stream`, `session-stream`, `user-stream` (per pattern)           | `billing-<pattern-dots-to-dashes>-consumer[-${BILLING_CONSUMER_SUFFIX}]`     | `microservices/billing_service/main.py:116-125`       |
| `payment_service` | per subject prefix (auto-derived)              | `payment_service-<subject-prefix>-consumer` (auto, no explicit durable)     | `microservices/payment_service/main.py:152` + `core/nats_client.py:407-409` |

| Symptom                                                 | Action                                                                            |
|---------------------------------------------------------|-----------------------------------------------------------------------------------|
| Backlog drains slowly under burst, replicas stay at min | Halve `lagThreshold` (e.g. 100 → 50)                                              |
| Pods churn — scale up then immediately drain to min     | Raise `cooldownPeriod` (300 → 600) and `scaleDownStabilization`                   |
| `consumer_pending` exists but trigger reports 0         | Check `account` and `consumer` names — JetStream is namespaced, typos are silent  |

### Auth tier (`prometheus` p95 latency)

`metadata.threshold` is the SLO trigger in seconds; `metadata.query` is
the PromQL evaluated each `pollingInterval`.

Verified metric source (`xenoISA/isA_Cloud/isA_common/isa_common/metrics.py`):

```text
isa_<service>_http_request_duration_seconds_bucket{method, path, le}
isa_<service>_http_requests_total{method, path, status_code}
```

The metric name already encodes the service (`isa_<service>_` prefix), so
a `service=` label selector is unnecessary and would match nothing.

| Symptom                                                  | Action                                                                                |
|----------------------------------------------------------|---------------------------------------------------------------------------------------|
| p95 climbs past SLA before replicas appear               | Lower `threshold` (e.g. 0.5s → 0.3s) and shorten `pollingInterval` (60s → 30s)        |
| Replicas pile on during normal traffic                   | The PromQL `[range]` is too tight — widen `[2m]` to `[5m]`                            |
| Trigger flatlines at 0 even under load                   | Run the PromQL against Prometheus directly; rule out missing labels or empty buckets  |

### Telemetry tier (`prometheus` WS gauge)

`metadata.threshold` is the per-replica connection ceiling. The default
500 matches the broadcast-fanout budget; raise it only after benchmarking
the event-bus consumer side.

`isa_user_websocket_active_connections` is currently aspirational — the
chart leaves it in place with a `TODO(#352)` comment. Confirm the metric
exists in the deployed pod's `/metrics` output before flipping
`kedaEnabled: true` in production.

## 5. Opt a single service in / out

In the consumer repo's values file (e.g. `deployment/helm/values.yaml`):

```yaml
hpa:
  kedaEnabled: true        # default false at chart level
  keda:
    tier: event             # event | auth | telemetry | default
    pollingInterval: 15     # override tier preset (optional)
    cooldownPeriod: 300
    scaleDownStabilization: 600
    fallback:
      failureThreshold: 3
      replicas: 2
    triggers:               # custom inline trigger list (replaces tier preset)
      - type: nats-jetstream
        metricType: AverageValue
        metadata:
          natsServerMonitoringEndpoint: "nats.isa-cloud-prod.svc.cluster.local:8222"
          account: "$G"
          stream: "billing-stream"
          consumer: "billing-usage-recorded-all-consumer"
          lagThreshold: "50"
          activationLagThreshold: "10"
          useHttps: "false"

# autoscaling block still drives min/max replicas and the CPU/memory
# fallback trigger values:
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 15
  targetCPUUtilization: 70
  targetMemoryUtilization: 80
```

Setting `hpa.kedaEnabled: false` returns the chart to the plain
`HorizontalPodAutoscaler`. Setting `autoscaling.enabled: false` disables
both.

## 6. Recovery

### Trigger going silent

Symptoms: `kubectl describe so <name>` shows `Fallback=True` or
`Active=False`; `kubectl get --raw .../external.metrics.k8s.io/...`
returns 404 or empty.

1. Check the source. NATS — is the consumer still bound? Prometheus —
   does the metric exist with the expected labels?
2. Check the KEDA operator logs:
   `kubectl logs -n keda deploy/keda-operator --tail=200 | grep <service>`.
3. While debugging, set `hpa.kedaEnabled: false` and re-deploy to drop the
   `ScaledObject` and restore the plain HPA. Pods continue serving on
   `Deployment.spec.replicas`.

### Replica oscillation

Symptoms: pods scale up and immediately drain, repeatedly.

1. Raise `scaleDownStabilization` to 300-600 seconds. KEDA defers
   scale-down until the metric stays below threshold for the whole
   window.
2. Raise `cooldownPeriod`. After the last trigger event, KEDA waits this
   long before scaling to `minReplicaCount`.
3. Validate the PromQL `[range]`. A 30s rate window on a sparse metric
   produces noisy step-changes; widen to `[2m]` and re-test.

### Missing exporter

If a tier's primary signal depends on a Prometheus metric that does not
yet exist (e.g. `isa_user_websocket_active_connections` for a brand-new
service), the trigger will report `Fallback=True`. **Do not** patch the
trigger to scrape an unrelated metric — file a follow-up issue against
the owning service to add the exporter, and leave the fallback CPU/memory
ceiling in place. Issue #352 explicitly excludes adding new exporters
from this workstream.

## 7. Quick reference

| Task                              | Command / file                                                                          |
|-----------------------------------|-----------------------------------------------------------------------------------------|
| Render rendered ScaledObjects     | `helm template deployments/charts/isa-service/ --set hpa.kedaEnabled=true`              |
| Lint chart                        | `helm lint deployments/charts/isa-service/ --strict`                                    |
| List ScaledObjects                | `kubectl get so -n isa-cloud-prod -l app.kubernetes.io/component=autoscaler`            |
| Tail KEDA operator logs           | `kubectl logs -n keda deploy/keda-operator --tail=200 -f`                               |
| Disable autoscaling globally      | `--set autoscaling.enabled=false`                                                       |
| Switch back to plain HPA          | `--set hpa.kedaEnabled=false`                                                           |
| Override threshold per service    | edit `hpa.keda.triggers` in the per-service values file                                 |

## 8. Out of scope

- **Vertical Pod Autoscaler (VPA).** Not enabled by this chart.
- **Cluster Autoscaler.** Node-level scaling is the cluster operator's
  concern, not this chart's.
- **New Prometheus exporters.** If a tier's signal needs a new metric,
  open a follow-up issue against the owning service.
