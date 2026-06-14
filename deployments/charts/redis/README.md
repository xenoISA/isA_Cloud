# redis

Standalone Redis for the Dataphin data-middle-platform.
Optional on-prem-full component (`dataphin.enabled`, default off).

## Why this chart exists

Dataphin needs a Redis (cache / session / distributed-lock store). Nothing
else in the platform provides one that Dataphin may use:

- `isa-bigdata` has **no** Redis subchart.
- Dataphin must not reach into the shared cloud infrastructure.

So Dataphin gets its own, in the `dataphin` namespace.

## Why self-authored (not a bitnami wrapper)

A thin chart over the official `redis` image is fully offline-installable from
a private registry mirror (useful in air-gapped / bandwidth-constrained
deployments) and has no external chart dependency to vendor. The rest of the
bigdata foundation wraps bitnami, but for a single standalone Redis this is
simpler and air-gap-friendly.

## What it deploys

| Object | Notes |
|---|---|
| `StatefulSet` (1 replica) | standalone; HA/sentinel is a follow-up |
| `Service` + headless `Service` | ClusterIP `redis-dataphin:6379` |
| `ConfigMap` | `redis.conf` (appendonly + `extraConfig`) |
| `Secret` | only when `auth.enabled` and no `existingSecret` |
| `NetworkPolicy` | optional; prod allows ingress from `dataphin` only |

## Auth

`auth.enabled: true` by default. Production sets `auth.existingSecret`
(Vault-provisioned via External Secrets, key `redis-password`); the password
is passed to `redis-server --requirepass` from that Secret, never baked into
the ConfigMap. kind/dev may set `auth.password` inline.

## Dataphin wiring

Set in Dataphin's `values.yaml`:

```yaml
global:
  redis:
    host: redis-dataphin.dataphin.svc.cluster.local
    port: 6379
    password: <from postgres-dataphin-auth/redis secret>
```
