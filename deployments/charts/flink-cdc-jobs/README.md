# flink-cdc-jobs (big-data foundation)

Per-source FlinkSessionJob templates for the isA platform's big-data
foundation. Tracking issue:
[isA_Cloud#250](https://github.com/xenoISA/isA_Cloud/issues/250).

## What this chart does

For each entry in `values.sources`, renders:

- One `ConfigMap` named `flink-cdc-<source>-sql` with the Flink SQL script
- One `FlinkSessionJob` CR named `flink-cdc-<source>` that submits the SQL
  to the long-running session cluster from the `flink` chart (#249)

No Deployments, no StatefulSets, no Services. The session cluster's
JM + TM pods are pre-wired with `iceberg-catalog` ConfigMap mounts and
`minio-credentials` env injection via the flink chart, so per-job
templates don't need to repeat any of that.

## V0.1 scope clarification

The "cdc" in `flink-cdc-jobs` refers to the **CDC-shaped pipeline** —
binlog/WAL/event-stream → Kafka → Flink → Iceberg → HMS — NOT the Apache
Flink CDC connector library specifically.

For W2 V-2/V-3 verification, the real DB binlog sources don't exist
yet (those land in W7+ when actual customer DBs connect). So this
chart's V0.1 scope is the **Kafka → Avro (via Apicurio) → Iceberg** path
only:

```
Kafka topic (landing.<source>)
  ─► Flink Avro decode via Apicurio schema (landing.<source>-value)
    ─► Flink Iceberg sink writing to s3a://lake/warehouse/<source>
      ─► HMS catalog entry visible to Dataphin + StarRocks
```

Real Flink CDC connector wiring (`mysql-cdc`, `postgres-cdc`,
`mongodb-cdc`) is **out of scope** for V0.1; opens as a follow-up
under #234 once W7+ source connections become real.

## Per-source values structure

```yaml
sources:
  - name: amazon_ads                                # required, alphanumeric+_
    enabled: true                                   # toggle without removing the entry
    parallelism: 2                                  # optional; defaults applied otherwise
    upgradeMode: stateless                          # optional
    state: running                                  # optional
    sql: |
      SET 'pipeline.name' = 'flink-cdc-amazon-ads';

      -- Kafka source (Avro decoded via Apicurio).
      CREATE TABLE kafka_amazon_ads (
        profile_id     STRING,
        campaign_id    STRING,
        report_date    DATE,
        impressions    BIGINT,
        clicks         BIGINT,
        spend          DECIMAL(18, 4),
        attributed_sales DECIMAL(18, 4),
        ingested_at    TIMESTAMP_LTZ(3) METADATA FROM 'timestamp'
      ) WITH (
        'connector' = 'kafka',
        'topic' = 'landing.raw_amazon_ads_campaign_performance',
        'properties.bootstrap.servers' = 'kafka-bootstrap.isa-bigdata.svc.cluster.local:9092',
        'properties.group.id' = 'flink-cdc-amazon-ads',
        'format' = 'avro-confluent',
        'avro-confluent.url' = 'http://apicurio-registry.isa-bigdata.svc.cluster.local:8080/apis/ccompat/v6',
        'avro-confluent.subject' = 'landing.raw_amazon_ads_campaign_performance-value',
        'scan.startup.mode' = 'earliest-offset'
      );

      -- Iceberg sink (catalog already loaded from /etc/iceberg/iceberg-catalog.properties).
      CREATE CATALOG iceberg WITH ('type' = 'iceberg', 'catalog-type' = 'hive', 'uri' = 'thrift://hive-metastore.isa-bigdata.svc.cluster.local:9083', 'warehouse' = 's3a://lake/warehouse/');
      USE CATALOG iceberg;

      CREATE TABLE IF NOT EXISTS `default`.`amazon_ads` (
        profile_id     STRING,
        campaign_id    STRING,
        report_date    DATE,
        impressions    BIGINT,
        clicks         BIGINT,
        spend          DECIMAL(18, 4),
        attributed_sales DECIMAL(18, 4),
        ingested_at    TIMESTAMP_LTZ(3),
        PRIMARY KEY (campaign_id, report_date) NOT ENFORCED
      ) WITH (
        'bucket' = '4',
        'changelog-producer' = 'input'
      );

      INSERT INTO `default`.`amazon_ads`
      SELECT * FROM default_catalog.default_database.kafka_amazon_ads;
```

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| Sources enabled | 3 P0 (amazon_ads, walmart_connect, shopify) — all stub SQL | 3 P0 — stub SQL | full 22 from `data_platform/sources/`; **all `enabled: false` by default** |
| Default parallelism | 1 | 2 | 4 |
| Default upgradeMode | stateless | stateless | last-state |
| Operators flip individual sources on as W7+ onboarding completes | n/a | n/a | yes |

## Stub SQL note (V0.1)

For the 3 P0 sources in kind/dev, the rendered SQL uses a `VALUES`
literal as a stand-in source so the FlinkSessionJob can be exercised
without real Kafka producers or per-source Avro schemas (those land in
W7+). Concretely:

```sql
SET 'pipeline.name' = 'flink-cdc-stub-amazon-ads';

CREATE CATALOG iceberg WITH ('type' = 'iceberg', 'catalog-type' = 'hive', 'uri' = 'thrift://hive-metastore.isa-bigdata.svc.cluster.local:9083', 'warehouse' = 's3a://lake/warehouse/');

CREATE TABLE IF NOT EXISTS iceberg.`default`.`stub_amazon_ads` (...);

-- VALUES literal stands in for the Kafka source until the real producer lands.
INSERT INTO iceberg.`default`.`stub_amazon_ads`
VALUES ('STUB-CAMPAIGN', DATE '1970-01-01', 0, 0, 0.00);
```

Replace each source's `sql` field with the real Kafka source DDL once
W7+ onboarding completes. The export bundle from
`sn-commercial-tower#235`'s
`scripts/dataphin/export_kafka_apicurio_bundle.py` produces the exact
topic + subject names; a future helper script can convert the bundle
into per-source `sql` field values automatically (separate story).

## Runner-jar contract

The chart's `runnerJar` value defaults to:

```
local:///opt/flink/usrlib/flink-sql-runner.jar
```

This requires the session cluster image (apache/flink:1.20.0…) to
include the `flink-sql-runner.jar` at that path. There are three ways
to satisfy this:

1. **Custom Dockerfile** — `FROM apache/flink:1.20-scala_2.12-java17 +
   COPY flink-sql-runner.jar /opt/flink/usrlib/`. Recommended for
   production; pin the runner version.
2. **Init container** — pull the jar from a remote URL into a shared
   volume that's mounted into the JM + TM pods.
3. **HTTP jarURI** — set `runnerJar:
   "https://github.com/apache/flink-kubernetes-operator/releases/.../flink-sql-runner.jar"`.
   Works for kind/dev with internet access; not air-gap-friendly.

Out of scope for this chart: building/distributing the runner image.
Track as a separate `flink-sql-runner-image` story.

## Schema evolution

Apicurio's BACKWARD compatibility (matches the export contract from
`sn-commercial-tower#235`) lets producers add fields without breaking
consumers. To survive a schema bump:

1. Producer registers v2 with Apicurio (`POST .../subjects/<subject>/versions`).
2. Apicurio enforces BACKWARD compatibility — the bump is rejected if
   it removes/renames fields.
3. The Flink job's `kafka_<source>` table reads the new schema on the
   next message; missing fields default to NULL on the consumer side.
4. The Iceberg sink schema can absorb the new fields by ALTER TABLE +
   chart re-deploy (`upgradeMode: last-state` keeps the checkpoint
   pointer).

## How to enable a customer-prod source

```yaml
# In your customer-prod overlay or Helm values:
flink-cdc-jobs:
  sources:
    - name: amazon_ads
      enabled: true        # was false
      parallelism: 4
      sql: |
        # ...real W7+ DDL...
```

Re-deploy with `helm upgrade`. The chart re-renders only the touched
source's ConfigMap + FlinkSessionJob; untouched sources stay as-is.

## Out of scope (follow-ups)

- **Flink CDC connector wiring** (`mysql-cdc`, `postgres-cdc`, etc.) — separate story; W7+ when real DB binlog sources land
- **flink-sql-runner image build pipeline** — separate story
- **Per-source schema generation from the export bundle** — automate the manual `sql` field; separate story
- **Live V-2 / V-3 / V-5 verification** — separate story; needs the runner jar baked AND a real Kafka producer for at least one source
- **Routine job restart / savepoint promotion ops** — separate `flink-job-ops` story
- **Per-source autoscaling / reactive scaling** — separate perf story
- **Dead letter Kafka topic + retry policy** — producer-side concern (ingest API), not this chart

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235 / #238 / #240 / #242 / #244 / #247 / #249 — kafka, postgres, hms, minio, iceberg-tools, starrocks, flink (already merged)
- xenoISA/sn-commercial-tower#235 — `scripts/dataphin/export_kafka_apicurio_bundle.py` produces the per-source topic + Apicurio subject contract this chart consumes
- xenoISA/sn-commercial-tower ADR-0002 §2.5 — chart layout
- xenoISA/sn-commercial-tower `docs/design/bigdata-architecture.md` §3.1 (4 ingestion paths)
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §6.4 (W7-W11 onboarding cadence)
