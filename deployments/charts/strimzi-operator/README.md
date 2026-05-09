# strimzi-operator

Strimzi Kafka Operator wrapper. Installs the Strimzi Operator
cluster-wide so the `Kafka` + `KafkaNodePool` CRs from the kafka chart
([#235](https://github.com/xenoISA/isA_Cloud/pull/235)) reconcile into
actual broker pods.

Tracking issue:
[xenoISA/isA_Cloud#256](https://github.com/xenoISA/isA_Cloud/issues/256).

## ⚠️ Install order is strict

This chart is a **prerequisite** for the `isa-bigdata` umbrella.
Install it **before** the umbrella, otherwise the umbrella's `kafka`
subchart fails on missing CRDs.

```bash
# Step 1: install Strimzi (cluster-wide CRDs + operator pod)
kubectl create namespace strimzi-system
helm install strimzi-operator deployments/charts/strimzi-operator \
  --namespace strimzi-system

# Step 2: install the big-data umbrella (kafka CRs reconcile)
helm install bigdata deployments/umbrella/isa-bigdata \
  --namespace isa-bigdata --create-namespace \
  --values deployments/values/kind-local.yaml
```

Reversing the order makes step 2 fail with `no matches for kind
"KafkaNodePool" in version "kafka.strimzi.io/v1beta2"`.

## Why a separate chart (not part of the umbrella)

CRDs must be installed in the cluster **before** any CR referencing
them is `helm template`-d server-side or `kubectl apply`-d. Helm 3
allows CRDs in a chart's `crds/` directory but those install once
and cannot be updated cleanly. Putting the operator in the umbrella
would force every `helm upgrade isa-bigdata` to grapple with CRD
ordering.

Decoupling lets the operator follow Strimzi's release cadence
independently of the application umbrella.

## What gets installed

The upstream `strimzi/strimzi-kafka-operator` chart ships:

- **Operator Deployment** in the install namespace (`strimzi-system` by default).
- **8 Cluster-scoped CRDs**: Kafka, KafkaNodePool, KafkaUser, KafkaTopic, KafkaConnect, KafkaConnector, KafkaMirrorMaker2, KafkaRebalance.
- **ClusterRole + ClusterRoleBinding** scoped to the operator's service account, allowing it to reconcile CRs in the watch namespaces.
- **Webhook** (validating) for the Kafka resource to catch bad specs at apply time.
- **Optional ServiceMonitor** (gated by `serviceMonitor.enabled`) for Prometheus operator.

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| Operator replicas | 1 | 1 | 1 (leader-elected; HA-by-restart) |
| `watchNamespaces` | `[isa-bigdata]` | `[isa-bigdata]` | `[isa-bigdata]` |
| ServiceMonitor | off | on | on |
| PriorityClass | (none) | (none) | `infra-critical` |
| Resources | `200m/384Mi` (chart default) | same | same |

No persistent storage. The operator is stateless; restart resumes from
CRD state in etcd.

## Version pinning

Strimzi version dictates the Kafka version range:

| Strimzi | Kafka versions |
|---|---|
| 0.45 | 3.7 / 3.8 |
| **0.46** | 3.7 / 3.8 / 3.9 ← matches kafka chart's `kafkaVersion: "3.7.0"` |
| 0.47 | 3.7 / 3.8 / 3.9 |
| 0.49 | 3.8 / 3.9 |
| 0.50+ | 3.9 / 4.0 |
| 1.0 | 4.0 only |

The chart is pinned to **Strimzi 0.46.1** to match the kafka chart's
Kafka 3.7.0 target (KRaft GA landed in 0.46). To bump the kafka chart
to a newer Kafka, bump this chart's `dependencies` version
correspondingly so the operator + Kafka versions stay aligned.

## Uninstall (full cleanup)

```bash
# 1. Delete Kafka resources first (operator handles graceful broker shutdown).
kubectl -n isa-bigdata delete kafka --all
kubectl -n isa-bigdata delete kafkanodepool --all

# 2. Uninstall the operator.
helm uninstall strimzi-operator -n strimzi-system

# 3. Manually clean up cluster-scoped CRDs (Helm intentionally
#    doesn't delete crds/ items on uninstall — risk of data loss).
kubectl delete crd kafkas.kafka.strimzi.io \
  kafkanodepools.kafka.strimzi.io \
  kafkausers.kafka.strimzi.io \
  kafkatopics.kafka.strimzi.io \
  kafkaconnects.kafka.strimzi.io \
  kafkaconnectors.kafka.strimzi.io \
  kafkamirrormaker2s.kafka.strimzi.io \
  kafkarebalances.kafka.strimzi.io
```

## Out of scope (separate stories)

- **KafkaUser CRs** for per-consumer auth — kicks in when `flink-cdc-jobs` has real producers
- **KafkaTopic CRs** auto-managed via Topic Operator — toggleable via the kafka chart's `entityOperator.enabled` (off by default)
- **MirrorMaker2 / Kafka Connect** — single-cluster only for V0.1
- **Multi-cluster federation** — not in scope

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235 — kafka chart (consumer)
- xenoISA/isA_Cloud#258 — flink-sql-runner image (sibling runtime story; together they unblock live V-2/V-3/V-5)
- xenoISA/isA_Cloud#257 — end-to-end V-1..V-9 verification (consumer of this operator)
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §6.1 (W2 kind smoke order)
