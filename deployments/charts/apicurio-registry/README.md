# apicurio-registry

Apicurio Registry 2.6 with PostgreSQL backend, paired with the `kafka`
chart for the isA platform's big-data foundation. Tracking issue:
[isA_Cloud#234](https://github.com/xenoISA/isA_Cloud/issues/234).

## What this chart does

Standalone deployment of Apicurio Registry. No subcharts.

- `Deployment` — single image, env-driven config
- `Service` — ClusterIP on `:8080`
- `Secret` — DB creds (only when `db.auth.create=true`; kind only)
- `NetworkPolicy` — optional ingress allowlist
- `PodDisruptionBudget` — only when `replicas > 1`
- `ServiceMonitor` — optional Prometheus Operator scrape on `/q/metrics`

## Compatibility default

`registry.compatibilityLevel: BACKWARD` (matches the
`DEFAULT_COMPATIBILITY_MODE` constant in
`sn-commercial-tower/scripts/dataphin/export_kafka_apicurio_bundle.py`).
Override per artifact group at runtime through Apicurio's REST API.

## Cross-repo context

Topic + schema specs flow from sn-commercial-tower:

```
sn-commercial-tower/data_platform/sources/*.yaml
  └─ scripts/dataphin/export_kafka_apicurio_bundle.py (PR #235)
      └─ kafka_apicurio_bundle.json
          ├─ topics[]    → Kafka cluster (this repo, charts/kafka)
          └─ subjects[]  → Apicurio (this repo, charts/apicurio-registry)
```

Dataphin task templates reference subjects by name; Apicurio Registry
serves them.
