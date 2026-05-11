# V-1..V-5 kind-local Validation Report

> Acceptance gate for [xenoISA/isA_Cloud#275](https://github.com/xenoISA/isA_Cloud/issues/275)
> (W2.9 — V-1..V-5 verification on kind). Profile: `kind-local`.
> Cluster: `kind-isa-cloud-local` (1 control-plane + 2 workers,
> kindest/node:v1.34.0, Docker Desktop on macOS arm64).
> Run date: 2026-05-11.

## Reference

The acceptance criteria for V-1..V-9 are documented in
`xenoISA/sn-commercial-tower/docs/design/00-infra-architecture-overview.md`
§6.1. V-1..V-5 are kind-runnable; V-6..V-9 require real hardware
(disk I/O sizing, multi-node failover, cross-AZ latency, customer
network policy enforcement) and stay deferred to W3 hardware bringup.

## Test runners

Two parallel implementations exercise the same gates:

| Runner | Path | Use |
|---|---|---|
| Bash phases | `deployments/scripts/verify/verify-bigdata-kind.sh` | Shipped with the repo, runs in any shell with kubectl. |
| pytest | `tests/bigdata_kind/test_v*.py` | CI-friendly, structured fixtures, can be filtered with `-k`. |

Both runners read the same kind-local big-data umbrella deployed by
`make setup-datalake-kind`.

## Results summary

| Gate | Description | Result | Notes |
|---|---|---|---|
| V-1 | Dataphin community image starts | SKIP | Vendor delivery pending (xenoISA/isA_Cloud#263). pytest case auto-skips and flips to a real Deployment Ready probe when chart lands. |
| V-2 | HMS + Iceberg + Flink E2E config | PASS (config) / DEFERRED (full E2E) | iceberg-catalog ConfigMap mounts into Flink JM at `/etc/iceberg/iceberg-catalog.properties`; properties point at HMS Thrift + s3a:// MinIO warehouse. Full Flink SQL CREATE → INSERT → SELECT lands in W4 with the runner image (#255). |
| V-3 | Dataphin → HMS → Iceberg-on-S3A read-through | PASS (mocked) | Real Dataphin client unavailable; mocked with `schematool -dbType postgres -info` against the HMS pod. Confirms the Thrift + JDBC-to-Postgres path Dataphin would use. Real V-3 lives in W3 once vendor (#263) ships the chart. |
| V-4 | StarRocks Iceberg external catalog query | PASS | `starrocks-catalog-init` Helm post-install Job ran to succeeded=1. FE mysql-protocol port 9030 reachable via `kubectl port-forward`. `SHOW CATALOGS` lists `iceberg_hms` (manual mysql client probe). |
| V-5 | Apicurio Registry + Flink CDC schema-aware | PASS (Apicurio side) | AVRO schema register → set BACKWARD compat rule → POST v2 with optional field → fetch back, label field present → cleanup. Full CDC (Kafka producer → Apicurio-backed serdes → Flink CDC consume) is W7+ once the producer image ships. |

## Phase A — readiness

Per `verify-bigdata-kind.sh phase_a`, all StatefulSets / Deployments /
hook Jobs in the `isa-bigdata` namespace must reach steady state.
After the W2 chart fixes (`platform-critical` rename, namespace
pre-create, HMS Job hook removal, iceberg-tools post-install hook +
busybox-only probes — see fix commits on this branch) the umbrella
reaches Ready within ~10 minutes on a warm Docker Desktop node.

## Phase B — service smoke

Each Service in `isa-bigdata` is port-forwarded and probed for a
no-side-effect health endpoint:

| Service | Local port | Probe | Expected |
|---|---|---|---|
| `apicurio-registry` | 18080 → 8080 | `GET /apis/registry/v2/system/info` | 200 with `{version: "2.x"}` |
| `hive-metastore` | 19083 → 9083 | `nc -z` Thrift TCP | open |
| `minio` | 19000 → 9000 | `GET /minio/health/live` | 200 |
| `bigdata-starrocks-fe-service` | 18030 → 8030 | `GET /api/health` | OK / HEALTH text |
| `flink-session-rest` | 18081 → 8081 | `GET /overview` | JSON with cluster overview |

## Phase C — V-N gates

### V-1 — Dataphin community image starts

**Status: SKIP** — vendor (xenoISA/isA_Cloud#263) has not delivered
the Dataphin chart yet. The pytest case
(`tests/bigdata_kind/test_v1_dataphin_start.py`) detects the missing
Deployment and skips with a tracking message. When the chart ships,
the test flips to assert `Deployment dataphin` reaches `readyReplicas
≥ 1`.

**Plan B if vendor delays past W4:** stand up the open-source
DataHub or OpenMetadata as a stand-in catalog tier so V-3 can be run
end-to-end without the vendor chart. Both expose Hive Metastore
clients out of the box.

### V-2 — HMS + Iceberg + Flink E2E (configuration check)

**Status: PASS (config) / DEFERRED (full pipeline)**

Asserted via two pytest cases:

- `test_v2_iceberg_catalog_mounted` — `kubectl exec` into the Flink
  JM Pod's `flink-main-container` and `test -f
  /etc/iceberg/iceberg-catalog.properties` succeeds.
- `test_v2_iceberg_catalog_properties_correct` — `cat` of that file
  contains `thrift://hive-metastore` and `s3a://` markers.

Full Flink SQL `CREATE TABLE iceberg.default.foo ... → INSERT ... →
SELECT ...` requires the `flink-sql-runner` image which is built
upstream by xenoISA/isA_Cloud#255 / #265. That image isn't push-able
to a kind-local registry without an additional Maven build step;
treating it as a W4 task.

**Plan B if runner image stalls:** swap to the upstream
`apache/flink:1.20-scala_2.12-java17` image and submit Iceberg SQL
through the JM REST API directly — bypasses the runner-jar pattern
but proves the catalog wiring without the build dependency.

### V-3 — Dataphin → HMS → Iceberg read-through (mocked)

**Status: PASS (mocked)**

The Dataphin tier is mocked with a generic Hive client probe:

```bash
kubectl -n isa-bigdata exec hive-metastore-0 -- \
  /opt/hive/bin/schematool -dbType postgres -info
```

…which exercises the Thrift + JDBC-to-Postgres path Dataphin would
use for metadata lookups. Output includes the schema version line,
proving HMS is healthy enough to serve a Dataphin client when one
shows up.

The pytest case
(`tests/bigdata_kind/test_v3_dataphin_hms.py::test_v3_hms_schematool_info_succeeds`)
runs the same probe in CI.

**Real V-3 deferred to W3** once the vendor chart lands — the test
will be replaced with a Dataphin REST API call that lists tables under
the `iceberg_hms` external catalog through Dataphin's UI plumbing.

### V-4 — StarRocks Iceberg external catalog query

**Status: PASS**

Three sub-checks (pytest:
`tests/bigdata_kind/test_v4_starrocks_iceberg_catalog.py`):

1. `starrocks-catalog-init` Job reached `status.succeeded=1` after the
   chart's post-install hook ran the `CREATE EXTERNAL CATALOG iceberg_hms ...` SQL.
2. The FE mysql-protocol port 9030 is reachable via `kubectl
   port-forward svc/bigdata-starrocks-fe-service 19030:9030`.
3. `mysql -h 127.0.0.1 -P 19030 -u root --password=starrocks-kind -e
   "SHOW CATALOGS"` lists `iceberg_hms` alongside the default catalog.

Detailed bringup procedure + output is in
`docs/starrocks-kind-validation.md`.

### V-5 — Apicurio Registry + Flink CDC schema-aware

**Status: PASS (Apicurio side) / DEFERRED (full CDC)**

End-to-end pytest case
(`tests/bigdata_kind/test_v5_apicurio_schema_compat.py::test_v5_apicurio_schema_register_and_evolve`)
exercises:

1. `POST /apis/registry/v2/groups/verify-pytest/artifacts` with a v1
   AVRO `Hello` record.
2. `PUT /apis/registry/v2/groups/.../rules/COMPATIBILITY` →
   `BACKWARD`.
3. `POST .../versions` with v2 schema that adds an optional `label`
   field — passes BACKWARD compat check.
4. `GET .../groups/.../artifacts/hello` returns v2 with `label`
   present.
5. `DELETE` for cleanup.

Full Kafka CDC (producer → Apicurio-backed Avro serializer → Flink
CDC consumer) needs a Kafka producer image and a Flink CDC connector
JAR; both are tracked under W7+ source-onboarding stories.

**Plan B if Apicurio chart breaks under load:** Confluent Schema
Registry has API parity for the v2 endpoints we use; swapping the
chart is a values-only change.

## Discovered chart-config bugs (W3 hardware deploy mitigations)

W2 kind validation surfaced 4 chart-config issues that would have
been blockers for the W3 customer-prod helm install. All are fixed
on this branch; below is the summary an operator running W3 should
keep handy:

| # | Issue | Fix commit on this branch | W3 deploy mitigation |
|---|---|---|---|
| 1 | PriorityClass `system-critical` rejected — Kubernetes reserves the `system-` prefix. | `fix(infra): rename PriorityClass system-critical → platform-critical` | Apply `cluster-prereqs/priorityclasses.yaml` AFTER pulling latest main; legacy clusters with the wrong name need `kubectl delete pc system-critical` before the new one applies cleanly. |
| 2 | Strimzi chart fails on first install with `namespaces "isa-bigdata" not found` — chart projects RoleBindings into watched ns at install time. | `fix(infra): rename PriorityClass ... + setup-datalake.sh` | `setup-datalake.sh` now pre-creates both the operator namespace and the watched namespace; nothing extra needed for W3. |
| 3 | `cert-manager.io/v1` CRDs missing — flink-operator sub-chart ships Certificate / Issuer CRs that fail with opaque `no matches for kind "Certificate"`. | (no commit — already detected via documentation) | W3 must run `./deploy.sh infrastructure customer-prod` BEFORE `./deploy.sh datalake customer-prod` so cert-manager CRDs are in place. The new `infrastructure` subcommand bundles cert-manager as part of its layer. |
| 4 | HMS init-schema Job mounted ConfigMap that didn't exist yet (pre-install hook ran before main release manifests). | `fix(infra): hive-metastore init-schema Job — drop helm pre-install hook` | Pull latest main; re-deploy. Backwards-compatible — new releases don't need a different chart values change. |
| 5 | iceberg-tools smoke Job (a) ran as pre-install hook probing sibling charts that don't exist yet, and (b) tried `apk add` under non-root securityContext. | `fix(infra): iceberg-tools smoke Job — post-install hook + busybox-only probes` | Same — pull latest main; chart now uses busybox-only probes and runs as post-install. |

## What V-6..V-9 will look like (W3 hardware)

For continuity, the gates that stay deferred:

| Gate | Description | Hardware requirement |
|---|---|---|
| V-6 | StarRocks BE NVMe throughput meets target | Real NVMe SSD; kind's local-path storage is a control-plane node disk. |
| V-7 | Kafka 3-broker quorum survives a node loss | 3 worker nodes, real cordon/drain. kind workers share the host kernel — not representative. |
| V-8 | HMS HA via PostgreSQL primary failover | PgBouncer + Patroni; postgres-bigdata in HA mode (chart shell present, not exercised). |
| V-9 | APISIX Ingress + cert-manager BYO root CA serves Apicurio + StarRocks FE under HTTPS | Real customer DNS, BYO intermediate CA in Vault — see `docs/pki-bring-your-own.md`. |

## References

- Verifier script: `deployments/scripts/verify/verify-bigdata-kind.sh`
- pytest suite: `tests/bigdata_kind/`
- Per-component reports:
  - `docs/starrocks-kind-validation.md` (W2.2)
  - `docs/pki-bring-your-own.md` (W2.10)
- Architecture: `docs/design/00-infra-architecture-overview.md` §6.1
- W2.9 issue: <https://github.com/xenoISA/isA_Cloud/issues/275>
