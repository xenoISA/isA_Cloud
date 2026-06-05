# postgres-dataphin

Dedicated PostgreSQL instance for the Dataphin data-middle-platform.
Optional on-prem-full component (`dataphin.enabled`, default off).

## Why a dedicated instance (not postgres-bigdata)

`postgres-bigdata` pre-creates a single, non-privileged `dataphin` database
for "vendor metadata". That is **not** what the real Dataphin 6.1.2 package
needs. Dataphin's installer (`init/init-postgresql.sh`, shipped inside
`dataphin.tar.gz`) authenticates as the postgres **superuser** and:

- creates ~18 datasource databases/schemas (`rs`, `sop`, `oneid`, `quality`,
  `stream_meta`, `datasecurity`, `scheduleproxy`, `qd.dsoc/sysmgt/featurex`, …)
- creates roles with `ALTER ROLE ... LOGIN SUPERUSER`

Granting that on the shared instance that also backs `hive-metastore` and
`apicurio-registry` breaks tenant isolation (Dataphin must not be given direct
access to unrelated infrastructure databases). So Dataphin gets its own
instance here.

## What this chart does

Wraps the upstream `bitnami/postgresql` chart with profile-aware defaults,
identical in shape to `postgres-bigdata`. The bitnami subchart owns the
actual `StatefulSet`, `Service`, `Secret`, `NetworkPolicy`, and
`ServiceMonitor`. This chart only:

- Pins the bitnami chart version (18.6.3)
- Sets edition-profile defaults
- Provides the postgres **superuser** credential the Dataphin installer needs

It deliberately does **not** run consumer initdb scripts — Dataphin's own
installer provisions every database, schema, and role.

## Consumer contract

| Consumer | Connects as | Secret it reads | Notes |
|---|---|---|---|
| Dataphin `init-postgresql.sh` | `postgres` (superuser) | `postgres-dataphin-auth` (keys: `postgres-password`, `password`) | bootstraps all DBs/roles |
| Dataphin services (runtime) | roles created by the installer | n/a (set in Dataphin `values.yaml` `global.postgresql.*`) | |

## Deployment

Deployed as a subchart of the `isa-dataphin-infra` umbrella into the
`dataphin` namespace. Production uses the `on-prem-full` profile. The
`postgres-dataphin-auth` Secret is Vault-provisioned (External Secrets),
mirroring `postgres-bigdata-auth`.
