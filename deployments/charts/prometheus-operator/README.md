# prometheus-operator

Prometheus Operator wrapper. Installs the upstream
`prometheus-community/kube-prometheus-stack` (Prometheus + Grafana +
AlertManager + Operator + CRDs) cluster-wide so the **ServiceMonitor**
CRs from the big-data charts actually get scraped.

Tracking issue: [xenoISA/isA_Cloud#234](https://github.com/xenoISA/isA_Cloud/issues/234)
(closes the "🔴 prometheus-operator" gap from the deployment-readiness
audit).

## ⚠️ Install order is strict

This chart is a **prerequisite** for the `isa-bigdata` umbrella when
`customer-prod` (or any profile with `serviceMonitor.enabled: true`)
is in use. Install **before** the umbrella, otherwise the umbrella's
ServiceMonitor CRs fail to apply with `no matches for kind
"ServiceMonitor" in version "monitoring.coreos.com/v1"`.

```bash
# Step 1: install Prometheus Operator (cluster-wide CRDs + stack)
kubectl create namespace monitoring
helm install prometheus-operator deployments/charts/prometheus-operator \
  --namespace monitoring

# Step 2: install the big-data umbrella (ServiceMonitor CRs reconcile)
deployments/scripts/setup-datalake.sh -p customer-prod
```

Reversing the order produces silent monitoring loss — the umbrella
applies, ServiceMonitors fail, helm reports success on the
non-monitoring resources, and Grafana sees zero metrics from the
big-data services.

## ServiceMonitor selector convention

The big-data charts label their ServiceMonitor CRs with `release:
prometheus`. This chart configures the upstream stack to match:

```yaml
prometheus:
  prometheusSpec:
    serviceMonitorSelector:
      matchLabels:
        release: prometheus    # ← matches the chart-side labels
```

If you bring your own Prometheus, configure the same selector or add
`release: prometheus` to whichever label your Prometheus matches.

## Profile differential

The chart ships defaults that suit staging. Override per profile:

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| Prometheus replicas | 1 | 1 | 2 (HA via leader-election) |
| Prometheus retention | 7d | 30d | 90d |
| Prometheus storage | local-path 10Gi | default-class 50Gi | infortrend-iscsi 200Gi (HA: 200Gi × 2) |
| Grafana persistence | off | on, 5Gi | on, 50Gi infortrend-iscsi |
| AlertManager replicas | 1 | 1 | 3 (HA cluster) |
| `kube{ApiServer,ControllerManager,Scheduler,Proxy,Etcd}` ServiceMonitors | **off** (kind doesn't expose these) | on | on |
| PriorityClass | (none) | (none) | `infra-critical` |
| Grafana admin password | inline (`adminPassword`) | from `existingSecret` | from `existingSecret` (vault-provisioned) |

(Profile-specific overrides should land alongside the existing
`deployments/values/{kind-local,dev-shared,customer-prod}.yaml` files
once a sibling overlay file is added — out of scope for this initial
chart PR; the umbrella values default works for staging.)

## What gets installed

- 8 cluster-scoped CRDs (`AlertManager`, `AlertManagerConfig`,
  `PodMonitor`, `Probe`, `Prometheus`, `PrometheusRule`,
  `ServiceMonitor`, `ThanosRuler`)
- 1 Prometheus Operator Deployment
- 1 Prometheus StatefulSet (default 1 replica)
- 1 AlertManager StatefulSet (default 1 replica)
- 1 Grafana Deployment + sidecars for datasource / dashboard auto-discovery
- node-exporter DaemonSet (cluster metrics)
- kube-state-metrics Deployment (K8s-object metrics)
- ServiceMonitors targeting the kube-system control plane (toggleable)
- ConfigMaps for default Grafana datasources + dashboards

Total footprint: ~10 pods + ~1.5 GiB RAM + ~2 vCPU at staging defaults.
Customer-prod with HA + retention triples this.

## Why a separate chart, not part of the umbrella?

CRDs must be installed in the cluster **before** any CR referencing
them is `kubectl apply`-d. Same reasoning as the Strimzi Operator
chart: putting prometheus-operator in the umbrella would force every
`helm upgrade isa-bigdata` to grapple with CRD ordering, and any
non-bigdata workload (e.g. Commercial_Tower BFF) would need its own
prometheus-operator install anyway. Decoupling lets the operator
follow upstream's release cadence independently.

## Bumping kube-prometheus-stack

1. Pick a new chart version from
   <https://github.com/prometheus-community/helm-charts/releases>.
2. Update `dependencies.version` in `Chart.yaml` and re-run
   `helm dependency update`.
3. Re-vendor the `.tgz` for air-gap.
4. Confirm no upstream breaking changes (Grafana / Prometheus version
   compat with our existing dashboards + scraping config).

## Uninstall (cleanup)

```bash
# 1. Delete the big-data umbrella first (ServiceMonitor CRs go with it).
helm uninstall bigdata -n isa-bigdata

# 2. Uninstall the operator stack.
helm uninstall prometheus-operator -n monitoring

# 3. Manually clean up the CRDs (Helm intentionally doesn't delete
#    crds/ items — risk of monitoring-history loss).
kubectl delete crd \
  alertmanagerconfigs.monitoring.coreos.com \
  alertmanagers.monitoring.coreos.com \
  podmonitors.monitoring.coreos.com \
  probes.monitoring.coreos.com \
  prometheuses.monitoring.coreos.com \
  prometheusrules.monitoring.coreos.com \
  servicemonitors.monitoring.coreos.com \
  thanosrulers.monitoring.coreos.com
```

## Out of scope (separate stories)

- **Profile-specific overlay files** under `deployments/values/` — the
  customer-prod ServiceMonitor selectors are already aligned with this
  chart's default; tuning Prometheus retention / Grafana persistence
  per profile lands as a follow-up
- **OIDC SSO for Grafana** — separate auth story
- **Pre-loaded Grafana dashboards** for big-data charts (HMS / Kafka /
  StarRocks / Flink JMX) — separate `bigdata-dashboards` story
- **Thanos / cortex long-term storage** — separate story
- **Cross-cluster federation** — single-cluster only
- **Wiring `setup-datalake.sh`** to optionally install this chart
  pre-umbrella — clean opt-in flag follow-up

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#259 — Strimzi Operator chart (sibling cluster-wide prereq)
- xenoISA/isA_Cloud#266 — PriorityClass + ArgoCD `isa-bigdata.yaml` (sibling cluster prereqs)
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §5.3 — observability stack design (Prom 30/90 days + Loki + Tempo)
