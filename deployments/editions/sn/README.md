# SN edition — deployment config (on-prem-full)

Reproducible config for the SN IDC deployment (ns `sn-cloud-production`).
Status + runbook: [`docs/saas-deployment/SN-DEPLOYMENT-STATUS.md`](../../../docs/saas-deployment/SN-DEPLOYMENT-STATUS.md).

## Layout
- `isa-svc-base.yaml` — base values for platform services (chart `isa-service`).
- `isa-user-base.yaml` — base values for isA_user microservices (configMapRef `isa-user-env`, pullPolicy Always).
- `services/<svc>.yaml` — per-platform-service overrides (name/image/port/health).
- `user-services/user-<short>.yaml` — per-isA_user-service (name/image/port/SERVICE_PORT env/health).
- `configmap-isa-platform-env.yaml`, `configmap-isa-user-env.yaml` — non-secret env (SN endpoints + edition + brand).
- `externalsecret-isa-platform-secrets.yaml` — Vault→k8s secret mapping (no values).
- `isa-user-migrate-job.yaml` — alembic pre-deploy migration Job template.

## Apply (KUBECONFIG=~/.kube/sn-rancher.yaml)
```sh
CHART=deployments/charts/isa-service
# platform service:
helm upgrade --install <svc> $CHART -n sn-cloud-production -f editions/sn/isa-svc-base.yaml -f editions/sn/services/<svc>.yaml
# isA_user service:
helm upgrade --install user-<short> $CHART -n sn-cloud-production -f editions/sn/isa-user-base.yaml -f editions/sn/user-services/user-<short>.yaml
```

## Porting to another edition (e.g. isA SaaS on GCP)
Swap only the `configmap-isa-*-env.yaml` (managed endpoints + `ISA_EDITION=saas` + brand). The chart and per-service value files are edition-agnostic.
