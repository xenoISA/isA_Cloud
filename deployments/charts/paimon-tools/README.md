# paimon-tools

Apache Paimon catalog config + init Job for the isA platform's big-data
foundation. Tracking issue:
[isA_Cloud#243](https://github.com/xenoISA/isA_Cloud/issues/243).

## What this chart does

Self-written, deliberately small. Renders only:

- **`ConfigMap` `paimon-catalog`** — the catalog properties downstream
  compute charts (`flink-cdc-jobs`, `starrocks`) mount and pass to
  Paimon's `Catalog.create()`. Backed by hive-metastore Thrift + MinIO
  S3A endpoints already deployed in the umbrella.
- **`Job` `paimon-tools-smoke`** (optional, gated) — runs once on
  Helm `pre-install` / `pre-upgrade`, verifies DNS + TCP reach to
  hive-metastore + minio, and checks the `paimon` bucket exists.

**No StatefulSet, no Service, no PDB.** Paimon is a lakehouse table
format *library*, not a server — actual reads/writes happen on Flink
and StarRocks workers in their own charts.

## Why no JAR shipping?

The design's "jar 注入" cue could be read as this chart shipping
Paimon JARs. In practice modern Flink (1.18+) and StarRocks (3.2+)
images bundle the Paimon connector — pulling extra JARs through this
chart would just duplicate them. If a future consumer needs an explicit
JAR-injection InitContainer pattern, that responsibility belongs to the
*consumer chart* (so it can pin to a connector matching the runtime
version), not here.

## Consumer contract

Downstream charts that read Paimon tables consume the
`paimon-catalog` ConfigMap as follows:

1. **Mount** the ConfigMap as a file:
   ```yaml
   volumes:
     - name: paimon-catalog
       configMap:
         name: paimon-catalog
   volumeMounts:
     - name: paimon-catalog
       mountPath: /etc/paimon/paimon-catalog.properties
       subPath: paimon-catalog.properties
   ```
2. **Inject** S3A creds as env from `minio-credentials` Secret:
   ```yaml
   env:
     - name: AWS_ACCESS_KEY_ID
       valueFrom:
         secretKeyRef:
           name: minio-credentials
           key: access-key
     - name: AWS_SECRET_ACCESS_KEY
       valueFrom:
         secretKeyRef:
           name: minio-credentials
           key: secret-key
   ```
3. **Load** the catalog in Flink/StarRocks/Spark using the mounted file.

The ConfigMap also exposes a `consumer-credentials-secret` block as a
discovery hint so a consumer chart doesn't have to hardcode the Secret
name.

## Init Job intent

Connectivity smoke only:

1. `nslookup hive-metastore.isa-bigdata.svc.cluster.local`
2. `nc -zv hive-metastore.isa-bigdata.svc.cluster.local 9083`
3. `nc -zv minio.isa-bigdata.svc.cluster.local 9000`
4. `curl … http://minio:9000/paimon/?list-type=2` — accepts `200` (public list) or `403` (auth required); fails on `404` (missing bucket)

Real V-2 / V-3 read-through verification (catalog create → Paimon table
write → StarRocks query) needs a running Flink cluster and is tracked
as a separate story under epic #234.

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| ConfigMap | rendered | rendered | rendered |
| Init Job | runs once | runs once | **disabled** (operator runs combined V-2/V-3 smoke through a vault-driven Job once flink lands) |
| probeHosts override | (defaults) | (defaults) | may override for off-cluster validators |

## Bumping Paimon

1. Update `appVersion` in `Chart.yaml` and `paimonVersion` in `values.yaml`.
2. Verify the consumer charts (flink, starrocks) ship a Paimon connector
   compatible with the new version. Paimon is wire-compatible across
   minor versions but file-format breaks happen across majors.
3. Re-render the umbrella. The ConfigMap changes; consumers pick up the
   new catalog options on their next deploy.

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235 / #238 / #240 / #242 — kafka, postgres-bigdata, hive-metastore, minio (already merged)
- xenoISA/sn-commercial-tower ADR-0002 §2.5 — chart layout
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §6.1 (W2 kind: paimon-tools jar), §1.4 risk #1 (V-3 highest-risk)
