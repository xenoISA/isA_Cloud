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

## Telemetry credential (#374, ADR 0009 §3)

At issuance the vendor-side Fleet Console (ADR 0009; `fleet/`) mints a
**per-deployment telemetry HMAC credential** alongside the signed `license.json`:

- `deployment_secret_id` (e.g. `dep-sn-7f3a1c0b`) — a NON-secret pointer, also
  written onto the issuance-ledger row.
- a random HMAC `secret` — SENSITIVE; this deployment uses it to **sign** the usage
  bundles it pushes back to intake (#375/#376). Telemetry is metadata-only (ADR 0009
  §5) — no business data, no PII.

**This is a Secret, not a ConfigMap** — the opposite of `license.json`. The license
is a *signed* public artifact (integrity from the signature ⇒ read-only ConfigMap is
correct, see above). The telemetry secret is a *symmetric HMAC key*: whoever holds it
can sign telemetry as this deployment, so it must be confidential at rest.

**Delivery — rides the existing secret path, not a new mechanism.** The minted
`secret` ships in the **SN offline delivery bundle** (same canonical offline-bundle
path as the signed `license.json`, above) and is loaded into the cluster the same way
every other SN secret is — **Vault → ExternalSecret → env**, exactly like
`POSTGRES_PASSWORD` etc. in `externalsecret-isa-platform-secrets.yaml`. Concretely:

1. Store the minted secret in Vault under the SN path, e.g.
   `isa-cloud/production/telemetry` with properties `deployment-secret-id` and
   `secret`.
2. Add two keys to `externalsecret-isa-platform-secrets.yaml` (Vault→k8s mapping):
   `ISA_DEPLOYMENT_SECRET_ID` ← `…/telemetry#deployment-secret-id` and
   `ISA_TELEMETRY_SECRET` ← `…/telemetry#secret`. They land in the existing
   `isa-platform-secrets` Secret and reach pods via the same `envFrom`/`secretRef`
   the other platform secrets use.
3. The deployment's usage-bundle signer (#376) reads `ISA_TELEMETRY_SECRET` +
   `ISA_DEPLOYMENT_SECRET_ID` and HMAC-signs each bundle with the scheme defined in
   `fleet/fleet_console/telemetry_credential.py` (HMAC-SHA256, lowercase hex, over
   the raw bundle bytes); intake validates via `verify_telemetry_hmac`.

For fully air-gapped customers the secret simply rides the manual offline bundle the
operator already carries in; no new egress is introduced (FW-OUT-001 holds).

**Rotation.** Re-minted automatically on license **renewal** (the new ledger row
gets a fresh secret) — refresh the Vault entry from the new offline bundle and roll
the pods, same cadence as the license swap above. On a suspected **leak**, the vendor
rotates the secret out-of-band (`rotate_credential`) and ships a replacement; swap the
Vault value and roll. **A leaked telemetry secret can only forge this customer's
telemetry — never a license** (licenses need the offline ed25519 private key, which
never enters any customer namespace; see `license-key-custody.md`).

## Porting to another edition (e.g. isA SaaS on GCP)
Swap only the `configmap-isa-*-env.yaml` (managed endpoints + `ISA_EDITION=saas` + brand). The chart and per-service value files are edition-agnostic. **Do not** carry `ISA_LICENSE_ENFORCE` into a SaaS/lite env ConfigMap — those editions leave it unset (license stays UNLICENSED, enforcement off).
