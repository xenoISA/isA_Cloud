# Runbook: On-Prem Bigdata Backbone and Dataphin Prep

This runbook captures the reusable production lessons from the SN on-prem-full
deployment. Customer-specific evidence stays in the customer delivery repo; the
rules here belong in `isA_Cloud` because they apply to every on-prem-full
profile that deploys `isa-bigdata` and later attaches Dataphin.

For the full three-layer product boundary (cloud platform, bigdata platform,
and Dataphin/data middle-platform), see
`docs/runbooks/on-prem-full-layered-platform.md`.

## Scope

Use this runbook for:

- `isa-bigdata` production backbone: Kafka, Apicurio, Postgres, Hive Metastore,
  MinIO lake, Iceberg tools, StarRocks, Flink.
- `isa-dataphin-infra`: Dataphin-dedicated PostgreSQL and Redis.
- Dataphin package preparation before the vendor chart/bootloader install.

Do not use this runbook for core platform services such as APISIX, the platform
PostgreSQL/Redis/MinIO, or user microservices.

## Documentation Split

Keep two document layers:

| Layer | Repository | Contents |
|---|---|---|
| Product/runbook layer | `isA_Cloud` | Reusable on-prem-full architecture, component boundaries, chart order, capacity baseline, secret boundaries, known failure modes, and generic Dataphin success criteria. |
| Customer delivery layer | customer repo, for example `SN/sn_cloud` | Site-specific IPs, kubeconfig names, Harbor domain, storage classes, license path, actual values files, exact commands, evidence, screenshots, and incident timeline. |

Do not move customer evidence, license material, decoded secrets, or exact
customer host paths into `isA_Cloud`. Conversely, do not leave reusable product
rules only in a customer repo; promote them here once they are proven by a real
deployment.

## Deployment Model

On-prem-full uses the upstream `isA_Cloud` charts plus a customer profile. A
customer repo may keep values and delivery evidence, but the production chart
path remains:

```text
deployments/umbrella/isa-bigdata
```

The Dataphin product itself is a later attachment layer. Do not treat Dataphin
absence as a failed bigdata backbone if Kafka, HMS, MinIO, StarRocks, and Flink
are healthy.

CI should lint and render charts. It should not be the production installer for
stateful infra in air-gapped on-prem environments. Production changes are
applied by controlled Helm/ArgoCD operations using Vault/External Secrets for
credentials.

## Golden Path

1. Confirm the production API path and context.
2. Confirm Vault/External Secrets have created all production Secrets.
3. Render and inspect the exact customer values.
4. Run `helm dependency update deployments/umbrella/isa-bigdata`.
5. Apply with sanitized current values or `--reset-values`; avoid stale nested
   keys.
6. Verify resources in this order:
   Kafka -> MinIO -> Postgres/HMS -> Flink operator -> Flink session ->
   StarRocks operator -> StarRocks FE/BE.
7. Patch stateful PVs to `Retain` after PVCs are bound unless the storage class
   already enforces the same policy.
8. Record evidence in the customer repo.

When removing or renaming nested Helm values, do not use plain `--reuse-values`.
Helm merges old keys back into the release. Start from sanitized current values,
delete the old keys explicitly, and apply with `--reset-values -f sanitized -f
customer-values.yaml`.

## Capacity Baseline

For initial on-prem-full startup, use a deliberately small but expandable
footprint:

| Component | Startup capacity |
|---|---:|
| Kafka | `3 x 10Ti` |
| MinIO lake | `4 x 200Gi` |
| Postgres bigdata | `500Gi primary + 500Gi read` |
| StarRocks FE | `3 x (50Gi meta + 5Gi log)` |
| StarRocks BE | `3 x (200Gi data + 20Gi log)` |

Kafka is the short-term stream/replay layer. Long-term warehouse, checkpoint,
staging, and export data belongs in the MinIO lake. Expand MinIO separately
before real Dataphin data onboarding; do not compensate for lake capacity by
oversizing Kafka.

## Secrets and Storage Boundaries

Production secrets should come from Vault/External Secrets, not Helm values.
Expected secret boundaries:

| Area | Secret boundary |
|---|---|
| Bigdata Postgres | `postgres-bigdata-auth` |
| Apicurio | `apicurio-registry-db` |
| Hive Metastore | `hive-metastore-db` |
| Bigdata MinIO lake | `minio-credentials` |
| StarRocks | `starrocks-root-credentials` |
| Dataphin Postgres | `postgres-dataphin-auth` |
| Dataphin Redis | `redis-dataphin-auth` |

Keep the platform MinIO and the bigdata MinIO lake separate. The platform MinIO
serves isA application storage. The bigdata MinIO lake serves HMS/Iceberg,
Flink checkpoints, StarRocks external catalogs, and Dataphin staging/export.

## Known Failure Modes

### Flink S3 credentials

Symptom:

- Flink JobManager starts, then crashes with MinIO/S3A
  `InvalidAccessKeyId`.

Cause:

- `s3.access-key: ${AWS_ACCESS_KEY_ID}` and `s3.secret-key:
  ${AWS_SECRET_ACCESS_KEY}` were rendered into `flink-conf.yaml`. Flink 1.20 did
  not expand those placeholders before Hadoop S3A used them.

Fix:

- Inject `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from the Kubernetes
  Secret into JobManager and TaskManager pods.
- Do not render S3 secret placeholders into `flink-conf.yaml`.
- Set:

```yaml
fs.s3a.aws.credentials.provider: com.amazonaws.auth.EnvironmentVariableCredentialsProvider
```

Verification:

- `FlinkDeployment` status is `STABLE/READY/DEPLOYED`.
- JobManager logs show S3A creates the HA job-result-store path.
- No `InvalidAccessKeyId` or `UnsupportedFileSystemSchemeException: s3a`.

### Flink runtime image pull and S3 plugin

The Flink runtime image pull secret must be present on JobManager and
TaskManager pod templates, not only on the operator. Enable the S3 plugin with:

```yaml
extraEnv:
  - name: ENABLE_BUILT_IN_PLUGINS
    value: flink-s3-fs-hadoop-1.20.0.jar
```

### Kafka anti-affinity

Broker anti-affinity must match broker pods only:

```yaml
strimzi.io/cluster: kafka
strimzi.io/component-type: kafka
```

The Entity Operator shares the cluster label. If anti-affinity matches only the
cluster label on a three-node cluster, the Entity Operator may be unable to
co-locate with any broker. Keep Entity Operator disabled during initial
backbone stabilization and re-enable it in a controlled window.

### StarRocks FE local metadata

Symptom:

- One FE pod is `CrashLoopBackOff`; the other two FEs and all BEs are alive.
- FE log PVC contains: `current node is not added to the cluster, will exit`.

Cause:

- The failing FE bootstrapped bad local metadata and points its local helper to
  itself instead of syncing from the existing FE leader.

Fix:

1. Confirm healthy quorum from a live FE with `SHOW FRONTENDS` and
   `SHOW BACKENDS`.
2. Read the failing FE log PVC with a temporary read-only pod.
3. If the failed FE has no useful replicated image and healthy FE quorum exists,
   clear only that FE ordinal's local meta PVC.
4. Delete the failed pod so the StatefulSet recreates it and the entrypoint can
   rejoin it to the existing leader.

Do not clear FE0/FE2 metadata or BE data while recovering one failed follower.

### PV reclaim policy

Most dynamic storage classes default to `Delete`. After production PVCs are
bound, patch stateful PVs to `Retain` unless the platform storage policy already
does this. This protects against accidental PVC deletion while preserving the
ability to reclaim manually.

## Dataphin Prep

Dataphin has two distinct layers:

1. `isa-dataphin-infra`: dedicated PostgreSQL and Redis in namespace
   `dataphin`.
2. Vendor Dataphin package/chart/bootloader: installed later from the offline
   package and license.

`isa-dataphin-infra` is required because Dataphin needs a PostgreSQL superuser
for its own installer and a dedicated Redis. It must not reuse
`postgres-bigdata`, the platform PostgreSQL, or unrelated Redis instances.

Prerequisites before installing Dataphin itself:

- Bigdata backbone is healthy.
- Dataphin license is present and kept out of Git.
- Dataphin images are loaded from the offline `.imz` packages and pushed to the
  customer Harbor project.
- Dataphin values point to the customer Harbor registry, not the vendor public
  registry.
- `postgres-dataphin-auth` and `redis-dataphin-auth` exist via Vault/External
  Secrets.
- `isa-dataphin-infra` is deployed in namespace `dataphin`.
- The Dataphin values file points to the bigdata MinIO lake endpoint and bucket,
  not the platform MinIO.
- RWX storage is available for Dataphin file/shared volume needs. Block
  storage classes used by Kafka/StarRocks are usually RWO and are not a
  substitute for RWX.
- North-south exposure is decided: private DNS/VIP, ingress, APISIX, and TLS.
- `flink-cdc-jobs` remains disabled until real source onboarding is ready.

Suggested order:

```text
P0  Verify namespace, cert-manager, ingress/VIP, RWX storage class.
P1  Load Dataphin offline images and retag/push them to Harbor.
P2  Provision Vault secrets for Dataphin Postgres and Redis.
P3  Deploy isa-dataphin-infra into namespace dataphin.
P4  Render the vendor Dataphin values from the template.
P5  Install Dataphin bootloader/chart with the license.
P6  Wait for bootloader readiness, then service readiness.
P7  Validate real UI admin and ops accounts, including tenant selection and
    bootstrap context; clear sessions and roll Dataphin IDE/Security if cached
    user context persists.
P8  Attach HMS, MinIO lake, Kafka, Flink, StarRocks, and Apicurio as data and
    compute sources.
P9  Capture smoke evidence in the customer repo.
```

## Dataphin Success Criteria

Use precise language when reporting status:

| Term | Meaning | Gate |
|---|---|---|
| Deployed | The vendor bootloader is Ready, all enabled Dataphin runtime Deployments are Ready, schedule-pool agents are Ready, and the internal Web route returns the login page. | Kubernetes + HTTP smoke |
| Externally reachable | User workstation/browser can resolve the customer hostname and reach the ingress/VIP/TLS endpoint. | DNS/firewall/VIP/TLS smoke |
| Business usable | Admin can log in, tenant/bootstrap settings are valid, licensed modules are visible, and data-source connections to HMS/Iceberg, MinIO, Kafka, Apicurio, Flink, and StarRocks pass. | Functional smoke |
| Accepted | Customer owner signs off evidence and open risks. | Delivery acceptance |

Do not equate bootloader readiness with full business acceptance. A versioned
Deployment scaled to `0/0` by the Dataphin runtime is not a failure by itself;
judge only enabled/current runtime Deployments and schedule-pool workloads.

For on-prem-full licenses, enabled modules are license-dependent. The expected
runtime modules must be compared against the customer license/features and the
rendered vendor runtime package, not against every optional Dataphin SKU.

## Dataphin Install Lessons from SN 6.1.2

The SN production deployment exposed several reusable Dataphin 6.1.2 behaviors:

| Failure mode | Reusable fix |
|---|---|
| Harbor image pull fails when using a registry IP and the certificate has no IP SAN. | Use the registry DNS name in values and node resolver configuration. |
| Vendor `external` S3 provider generates virtual-host-style bucket URLs. | For Kubernetes-internal MinIO/path-style access, use a path-style external provider override if supported by the delivery package. |
| Dataphin startup exhausts PostgreSQL default `max_connections=100`. | Tune the dedicated Dataphin PostgreSQL before install; SN used `max_connections=800` and `shared_buffers=2GB`. |
| Bigdata metadata PostgreSQL exhausts default `max_connections=100` during HMS/Apicurio smoke. | Tune the shared bigdata metadata PostgreSQL separately from Dataphin's dedicated PostgreSQL; SN used `max_connections=400` and `shared_buffers=2GB`. |
| Dataphin DB init requires `gin_trgm_ops`. | Create `pg_trgm` in every Dataphin business database that the installer creates, not only the default `dataphin` DB. |
| StarRocks starts without the expected Iceberg external catalog. | Register and persist an `iceberg_hms` external catalog that points to HMS and the path-style MinIO lake before Dataphin functional smoke. |
| Apicurio rule API differs by version. | Verify schema evolution with the installed Registry API shape; SN's current API accepts artifact rule creation through `POST /rules`. |
| Default JVM sizing can be too close to a 4Gi memory limit. | Persist lower heap/metaspace ratios through a supported overlay or post-install operation before production traffic. |
| Ingress status publishes node IPs while VPN users must enter through a MetalLB/APISIX VIP. | Bind public Dataphin DNS to the actual ingress VIP; for external-dns, set a target annotation or equivalent customer DNS record. |
| Temporary debug pods block bootloader namespace readiness. | Delete debug pods after use; do not leave non-Ready pods in Dataphin namespaces during final bootloader checks. |
| A real ops/admin UI account fails tenant selection with `DPN.SSO.UNAUTHORIZED` or `DPN.Filter.UserInOtherTenants` after bootstrap. | Treat bootstrap `opsUserId` as an installer account, then validate real UI accounts separately. Ensure tenant member roles, user roles, tenant mapping, current tenant, and ops account type are aligned. Clear shadow/login sessions and roll Dataphin IDE/Security if old user context is cached. |

### Dataphin Bootstrap Account Validation

On-prem/full installs may bootstrap Dataphin with an installer account that is
not the final customer UI account. Do not delete or rename the bootstrap owner
unless the vendor procedure explicitly supports it. Instead:

1. Record the bootstrap owner/main account and real UI admin/ops account IDs in
   the customer repo.
2. Confirm the tenant has a valid owner, main account, and ops tenant marker.
3. Confirm real admin users have Dataphin tenant admin roles.
4. Confirm real ops users have tenant membership, ops/operate roles, a current
   tenant, and the expected ops account type.
5. Delete only the affected user's login/shadow sessions after DB repair.
6. Roll only Dataphin IDE/Security services if the browser still receives old
   tenant-context errors after DB state is correct.

Customer evidence should include trace IDs, redacted SQL result summaries, and
rollout status. It must not include passwords, decoded Secrets, license
contents, or raw session tokens.

## Verification Commands

Use customer-specific kubeconfig and namespace names. Do not print decoded
secrets.

```bash
helm -n sn-bigdata status bigdata
kubectl -n sn-bigdata get pods
kubectl -n sn-bigdata get kafka kafka -o jsonpath='{.status.conditions}'
kubectl -n sn-bigdata get flinkdeployment flink-session \
  -o jsonpath='{.status.lifecycleState},{.status.jobManagerDeploymentStatus},{.status.reconciliationStatus.state}'
kubectl -n sn-bigdata get starrockscluster starrocks \
  -o jsonpath='{.status.phase},{.status.starRocksFeStatus.phase},{.status.starRocksBeStatus.phase}'
kubectl -n sn-bigdata exec starrocks-fe-0 -- \
  mysql -uroot -h127.0.0.1 -P9030 -e 'SHOW FRONTENDS'
kubectl -n sn-bigdata exec starrocks-fe-0 -- \
  mysql -uroot -h127.0.0.1 -P9030 -e 'SHOW BACKENDS'
```

Healthy backbone gate:

```text
Helm release deployed
Kafka Ready=True
Flink STABLE/READY/DEPLOYED
StarRocks running/running/running
No pods in Pending, CrashLoopBackOff, or ImagePullBackOff
```
