# flink-sql-runner

Custom Apache Flink session-cluster image with `flink-sql-runner.jar` and
the connector jars (Paimon, Kafka, Avro Confluent registry) needed to
execute the FlinkSessionJob CRs from the `flink-cdc-jobs` chart
([xenoISA/isA_Cloud#252](https://github.com/xenoISA/isA_Cloud/pull/252)).

Tracking issue:
[xenoISA/isA_Cloud#255](https://github.com/xenoISA/isA_Cloud/issues/255).

## Why this exists

The `flink` chart ([#249](https://github.com/xenoISA/isA_Cloud/pull/249))
deploys a Flink Kubernetes Operator + a session cluster, and the
`flink-cdc-jobs` chart ([#252](https://github.com/xenoISA/isA_Cloud/pull/252))
submits per-source FlinkSessionJob CRs to that cluster. The CRs reference
`local:///opt/flink/usrlib/flink-sql-runner.jar`, but the stock
`apache/flink:1.20-scala_2.12-java17` image **does not** ship that jar —
the runner is a separate artifact released by the Flink Operator project.

Without this image, FlinkSessionJob CRs reach `RECONCILED` but never
`RUNNING`. With this image, V-2 / V-3 / V-5 become **runnable** on a
real kind cluster.

## What's in the image

| Jar | Source | Why |
|---|---|---|
| `flink-sql-runner.jar` | Apache Flink Operator release-1.10.0 | Entry point for FlinkSessionJob CRs |
| `paimon-flink-1.20-1.0.0.jar` | Maven Central, `org.apache.paimon` | Paimon table read/write from Flink SQL |
| `flink-sql-connector-kafka-3.2.0-1.20.jar` | Maven Central, `org.apache.flink` | Kafka source/sink for streaming SQL |
| `flink-sql-avro-confluent-registry-1.20.0.jar` | Maven Central, `org.apache.flink` | Avro decode against Apicurio's `/apis/ccompat/v6` endpoint |

Versions are pinned in [`jars.txt`](./jars.txt). Each entry can carry a
SHA-256 checksum that the build verifies before copying the jar into the
final image (today the checksums are placeholders — `-` — pending the
checksum-pinning follow-up).

## Build

```bash
make help                              # show all targets
make build                             # local build
make verify                            # smoke: confirm the runner jar is present
make push REGISTRY=ghcr.io/xenoisa     # push to the org's GHCR
```

The image tag (`IMAGE_TAG` in the Makefile) encodes the version matrix:

```
1.20.0-runner-1.10.0-paimon-1.0.0
│      │      │      │      └─ Apache Paimon
│      │      │      └─ Paimon connector pinned in jars.txt
│      │      └─ Flink Kubernetes Operator
│      └─ Operator-version label (release-1.10.0)
└─ Apache Flink runtime (apache/flink:1.20.0-scala_2.12-java17 base)
```

Bump the tag whenever any of the four versions in `jars.txt` change.

## Use the image in the flink chart

The `flink` chart's default `session.image` points at the stock
`apache/flink:1.20.0-scala_2.12-java17` so `helm template` renders
cleanly without this image existing yet. To run real jobs, override
the image in your environment values:

### kind-local (after `make push REGISTRY=ghcr.io/xenoisa`)

```yaml
flink:
  session:
    image:
      repository: ghcr.io/xenoisa/flink-sql-runner
      tag: 1.20.0-runner-1.10.0-paimon-1.0.0
```

### customer-prod (after Harbor mirror sync)

```yaml
flink:
  session:
    image:
      repository: harbor.customer.local/isa-platform/flink-sql-runner
      tag: 1.20.0-runner-1.10.0-paimon-1.0.0
```

The customer's Harbor mirror is the air-gap-friendly path per
`xenoISA/sn-commercial-tower/docs/design/00-infra-architecture-overview.md`
§5.5.

## Connector matrix

When bumping versions, all four jars must stay compatible:

| Flink | Operator | Paimon | Kafka conn | Avro Confluent |
|---|---|---|---|---|
| 1.18 | 1.9 | 0.9 | 3.0-1.18 | 1.18 |
| 1.20 | 1.10 | 1.0 | 3.2-1.20 | 1.20 |

Cross-version skews fail with `ClassNotFoundException` on job submission
(no friendly error). Always change the four jars together; bump the
image tag accordingly.

## Checksum-pinning follow-up

Today every entry in `jars.txt` carries `-` as the checksum, which the
Dockerfile fetcher accepts with a `WARNING: skipping checksum
verification` log line. To pin checksums:

```bash
make checksums                         # emits jars.txt-formatted lines
# review the output, paste back into jars.txt manually
make build                             # now verifies sha256 strictly
```

A future PR will rewrite `jars.txt` in place automatically and gate the
build on it. Until then, every chart-author who bumps a version is on
the honor system to also re-pin the checksum.

## Out of scope (separate stories)

- **CI workflow** for auto-building the image on jar version bumps —
  separate `.github/workflows/flink-sql-runner.yml` story
- **Multi-arch (arm64)** — the customer cluster is x86_64 only per
  `00-infra-architecture-overview.md` §3.1
- **Image signing / cosign** — separate supply-chain hardening story
- **Per-CDC-connector image variants** (mysql-cdc, postgres-cdc) —
  those land with the W7+ Flink CDC connector wiring story

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#249 — flink chart (consumer)
- xenoISA/isA_Cloud#252 — flink-cdc-jobs chart (FlinkSessionJob CRs)
- xenoISA/isA_Cloud#256 — Strimzi Kafka Operator install (sibling runtime
  story; together with this image, unblocks live V-2 / V-3 / V-5)
- xenoISA/isA_Cloud#257 — end-to-end V-1..V-9 verification on a kind
  cluster (consumer of this image + #256's operator)
