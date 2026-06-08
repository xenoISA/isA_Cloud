# SN Edition — Deployment Status (on-prem-full)

> Living record of the SN-edition deployment to the customer SN air-gapped IDC
> (EonKube/Rancher RKE, ns `sn-cloud-production`). Updated 2026-06-08.
> Model: **profile replaces white-label fork** — edition-agnostic `isa/*` images
> deployed by config (ConfigMap swap), per the editions decision (isA_Cloud#313).
> Reproducible config lives in [`deployments/editions/sn/`](../../deployments/editions/sn/).

## Cluster / registry
- Cluster: EonKube/Rancher RKE, K8s v1.25.6, 3 nodes (`10.60.64.11/12/13`), air-gapped, over FortiGate VPN (flaps — retry).
- Kubeconfig: `~/.kube/sn-rancher.yaml` (CA pinned to live cert).
- Harbor: `core.harbor.domain` (`10.60.65.10`), project `isa` (private), self-signed cert.
- Image flow: GitHub Actions → GHCR → `skopeo` mirror to Harbor from a VPN host (GH runners can't reach Harbor).

## ✅ Done (all 1/1 Running)
**Infra (single-node, validation):** Vault(TLS)+ESO, postgresql, redis, minio, qdrant, nats, consul, etcd, apisix.
**Platform services (9):** isa-model, isa-mcp, isa-data, isa-agent, isa-os, isa-mate, isa-console, isa-admin, isa-docs.
**isA_user microservices (42/42):** all `user-*` services on ports 8201–8262.
- DB `isa_platform` in postgresql; 41 schemas / 178 tables migrated (alembic for 8 services + raw SQL for the rest).
- Functional smoke verified (not just `/health`): services serve real API routes (auth 39, product 27, billing/org 19, account 17 via `/openapi.json`); real DB INSERT→SELECT→DELETE round-trip in `account.users` works.

**Total app footprint: 51 services (9 platform + 42 user), all healthy.**

## Deploy method (GCP-portable)
Standard chart `deployments/charts/isa-service` + a base values overlay + per-service values:
- Platform: `editions/sn/isa-svc-base.yaml` (configMapRef `isa-platform-env`) + `editions/sn/services/<svc>.yaml`.
- isA_user: `editions/sn/isa-user-base.yaml` (configMapRef `isa-user-env`, secretRef `isa-platform-secrets`, **pullPolicy Always**) + `editions/sn/user-services/user-<short>.yaml`.
- For GCP/SaaS: swap ONLY the `isa-*-env` ConfigMap (managed endpoints + `ISA_EDITION=saas` + brand `isA`). Chart + per-service files unchanged.

## ⏳ Next (production-readiness)
1. **PgBouncer** — services connect direct to `postgresql:5432`; scale-out needs PgBouncer (6432) to avoid exhausting `max_connections` (`DB_POOL_BASE/GROWTH` envs are for this). **Prerequisite for HPA.**
2. **Data-layer HA** — postgresql/redis/nats are single-node.
3. **HPA / scale-out** — all services `replicas: 1`, autoscaling off.
4. **Integration / e2e / load testing** — only smoke done; inter-service (Consul discovery), auth-protected flows, NATS events, and load are untested.
5. **Edition portability** — isA SaaS edition on GCP (ns `isa-cloud-production`); Dataphin/bigdata track.

## Known repo debt surfaced & fixed during this deploy
See `isA_user` PRs #505–#513 (lowercase GHCR prefix, base migration tooling, missing base deps, URL-encoded DB creds + alembic `%%`, ship `tests/contracts`, SERVICE_PORT build-arg, order_service migration ordering). The 8 alembic services still carry conflicting legacy raw SQL (skipped at deploy; should be removed upstream).
