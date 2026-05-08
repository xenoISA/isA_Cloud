# kafka

Strimzi-managed Apache Kafka cluster (KRaft mode) for the isA platform's
big-data foundation. Tracking issue: [isA_Cloud#234](https://github.com/xenoISA/isA_Cloud/issues/234).

## What this chart does

Renders Strimzi custom resources only:

- `KafkaNodePool` — broker + controller dual-role pool (KRaft)
- `Kafka` — top-level cluster spec (listeners, replication, metrics)
- `ConfigMap` — JMX Prometheus Exporter rules
- `NetworkPolicy` — optional ingress allowlist on broker ports
- `ServiceMonitor` — optional Prometheus Operator scrape config

The Strimzi Operator (a separate install — chart not included here) is
what reconciles those CRs into the actual `StatefulSet`, `Service`s, PDB,
and TLS material.

## Prerequisites

1. Strimzi Operator installed in-cluster (any namespace; CRDs are cluster-scoped).
2. Target namespace exists (`namespace` in values; default `isa-bigdata`).
3. For `serviceMonitor.enabled=true`: prometheus-operator CRDs installed.

## Topology

| Profile | Brokers | Storage | TLS | NetworkPolicy |
|---|---|---|---|---|
| `kind-local` | 1 | local-path 20Gi | plain only | off |
| Default (this chart) | 3 | persistent-claim 100Gi | TLS internal | off |
| `customer-prod` | 3 | iSCSI 80Ti | mTLS | on, per allowlist |

## Verifying a kind install

```bash
helm template kafka deployments/charts/kafka \
  --values deployments/values/kind-local.yaml | kubectl apply --dry-run=client -f -
```

Once the operator + this chart are both applied:

```bash
kubectl -n isa-bigdata get kafka,kafkanodepool
kubectl -n isa-bigdata wait --for=condition=Ready kafka/kafka --timeout=10m
```

## Cross-repo context

- Topic + schema specs come from xenoISA/sn-commercial-tower (PR #235,
  `scripts/dataphin/export_kafka_apicurio_bundle.py`). Those are referenced
  by Dataphin task templates that consume this Kafka cluster.
- The Apicurio Schema Registry that pairs with this cluster lives in
  `deployments/charts/apicurio-registry/`.
- Both are aggregated by `deployments/umbrella/isa-bigdata/`.
