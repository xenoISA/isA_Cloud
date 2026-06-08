# SN edition — deployment config (on-prem-full)

Reproducible config for the SN IDC deployment (ns `sn-cloud-production`).
Status + runbook: [`docs/saas-deployment/SN-DEPLOYMENT-STATUS.md`](../../../docs/saas-deployment/SN-DEPLOYMENT-STATUS.md).

## Layout
- `isa-svc-base.yaml` — base values for platform services (chart `isa-service`).
- `isa-user-base.yaml` — base values for isA_user microservices (configMapRef `isa-user-env`, pullPolicy Always).
- `services/<svc>.yaml` — per-platform-service overrides (name/image/port/health).
- `user-services/user-<short>.yaml` — per-isA_user-service (name/image/port/SERVICE_PORT env/health).
- `configmap-isa-platform-env.yaml`, `configmap-isa-user-env.yaml` — non-secret env (SN endpoints + edition + brand). Platform env also sets the license contract (`ISA_LICENSE_ENFORCE=true`, `ISA_LICENSE_FILE`) — see "License & entitlement" below.
- `configmap-isa-license.yaml` — the signed `license.json`, mounted read-only at `/etc/isa-license/license.json` (ADR 0008 §6). **Placeholder body — replace from the offline bundle.**
- `configmap-isa-license-pubkey.yaml` — ed25519 **public** verification key (non-secret), injected as env `ISA_LICENSE_PUBKEY`. **Placeholder body — replace from the offline bundle.**
- `values-entitled-modules.yaml` — entitled-modules source-of-truth transcribed from the license (#369).
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

## License & entitlement (ADR 0008 §6, #370)

SN is **on-prem-full** and **enforces** the license. The wiring (only in this SN
edition — SaaS/lite never set `ISA_LICENSE_ENFORCE`):

| Piece | Where | How it reaches the pod |
|---|---|---|
| `ISA_LICENSE_ENFORCE: "true"` | `configmap-isa-platform-env.yaml` | `envFrom` (configMapRef in `isa-svc-base.yaml`) |
| `ISA_LICENSE_FILE: /etc/isa-license/license.json` | `configmap-isa-platform-env.yaml` | `envFrom` |
| `ISA_LICENSE_PUBKEY` (ed25519 public key PEM) | `configmap-isa-license-pubkey.yaml` (`ed25519.pub`) | env `valueFrom.configMapKeyRef` in `isa-svc-base.yaml` |
| signed `license.json` | `configmap-isa-license.yaml` (`license.json`) | volume → **read-only** mount at `/etc/isa-license` in `isa-svc-base.yaml` |

Consumed at runtime by `isa_common/license.py` (verify) + `isa_common/licensing.py`
(`setup_licensing` — refuse-to-start on EXPIRED/INVALID when enforce is on).
The license.json is **signed**, so a read-only ConfigMap (not a Secret) is correct
— tampering invalidates the signature. Enforcement is hard at startup but
fail-open at runtime (ADR 0008 §3).

> **isA_user microservices** (`isa-user-base.yaml`, configMapRef `isa-user-env`)
> do **not** get `ISA_LICENSE_ENFORCE` — their entitlement is gated at the
> **deployment boundary** via `values-entitled-modules.yaml` + the customer-modules
> ApplicationSet (#369, ADR 0008 §5), not per-service startup enforcement.

### Install
```sh
# 1. Drop the REAL signed license.json + matching ed25519 public key into the two
#    placeholder ConfigMaps (delivered in the SN offline bundle — see below).
kubectl apply -n sn-cloud-production -f editions/sn/configmap-isa-license-pubkey.yaml
kubectl apply -n sn-cloud-production -f editions/sn/configmap-isa-license.yaml
# 2. (Re)deploy the platform services — they pick up the env + mount from base.
```

### Renew / swap (runbook: [`docs/runbooks/license-operator.md`](../../../docs/runbooks/license-operator.md) §4)
1. isA re-issues a new signed `license.json` **offline** (`isa-license-sign`; key
   custody: [`docs/saas-deployment/license-key-custody.md`](../../../docs/saas-deployment/license-key-custody.md)).
2. Swap the `license.json` value in `configmap-isa-license.yaml`, `kubectl apply`,
   then roll the platform pods (`kubectl rollout restart`) so they re-read the mount.
3. If `entitled_modules` changed, transcribe the new set into
   `values-entitled-modules.yaml` (#369) in lock-step.
4. Public-key rotation (rare): swap `ed25519.pub` in `configmap-isa-license-pubkey.yaml`.

### Offline delivery (ADR 0007)
The license.json + public key ship in the **SN offline delivery bundle** alongside
the platform release. The placeholder ConfigMap manifests here (and
`values-entitled-modules.yaml`) are bundled by `deployments/release/package-charts.sh`
under `releases/charts/editions/sn/`. The **real per-customer signed content** is
NOT committed to this repo — it is delivered via the canonical offline bundle in the
`sn_cloud` fork (`docs/implementation-delivery/production/assets/offline-bundle/`,
the same `mirror-to-harbor.sh` + manifest path that seeds Harbor) and dropped into
these manifests before apply. The image-mirror CSV
(`platform-vX.Y.Z.offline-bundle.csv`) is digest-pinned **container images only**;
the license is per-namespace config that rides the editions overlay, not an image.

## Porting to another edition (e.g. isA SaaS on GCP)
Swap only the `configmap-isa-*-env.yaml` (managed endpoints + `ISA_EDITION=saas` + brand). The chart and per-service value files are edition-agnostic. **Do not** carry `ISA_LICENSE_ENFORCE` into a SaaS/lite env ConfigMap — those editions leave it unset (license stays UNLICENSED, enforcement off).
